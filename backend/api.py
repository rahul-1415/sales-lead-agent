"""
FastAPI application — runs locally via uvicorn and in Lambda via Mangum.

Endpoints:
  POST /leads/upload      — upload CSV or JSON file; async (AWS) or sync (local)
  POST /leads/process     — synchronous JSON processing (small batches)
  GET  /leads             — paginated list of processed leads
  GET  /leads/{lead_id}   — single lead detail
  GET  /jobs/{job_id}     — batch job status
  GET  /jobs/{job_id}/download — presigned S3 URL for result file
  GET  /health            — load balancer / Route53 health check
"""

import csv
import io
import json
import logging
import uuid
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import db
import sqs
import storage
from agent.models import (
    BatchJob,
    BatchJobStats,
    EnrichedLead,
    JobStatus,
    JobStatusResponse,
    LeadBatch,
    LeadListResponse,
    RawLead,
    UploadResponse,
    compute_dedup_key,
)
from agent.orchestrator import process_batch
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="Sales Lead Agent API",
    description="AI-powered lead enrichment and scoring pipeline",
    version="1.0.0",
)

_LOCAL_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

_PROD_ORIGINS = [
    "https://sales-lead-agent.vercel.app",        # update to your actual Vercel URL
    "https://sales-lead-agent-*.vercel.app",      # preview deployments
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_LOCAL_ORIGINS if settings.is_local else _PROD_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory store for local dev (replaces DynamoDB + S3 when ENVIRONMENT=local)
# ---------------------------------------------------------------------------

_local_leads: dict[str, dict] = {}   # lead_id  → EnrichedLead dict
_local_jobs:  dict[str, dict] = {}   # job_id   → BatchJob dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_csv(content: bytes) -> list[RawLead]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    leads: list[RawLead] = []
    for row in reader:
        leads.append(
            RawLead(
                company=row.get("company") or row.get("Company") or row.get("company_name", ""),
                contact_name=row.get("contact_name") or row.get("name"),
                contact_email=row.get("email") or row.get("contact_email"),
                website=row.get("website"),
                industry=row.get("industry"),
                employee_count=int(row["employee_count"]) if row.get("employee_count") else None,
                location=row.get("location") or row.get("headquarters"),
                notes=row.get("notes"),
            )
        )
    return leads


def _parse_json(content: bytes) -> list[RawLead]:
    data = json.loads(content)
    items = data if isinstance(data, list) else data.get("leads", [])
    return [RawLead(**item) for item in items]


def _parse_file(content: bytes, filename: str) -> list[RawLead]:
    try:
        if filename.endswith(".csv"):
            return _parse_csv(content)
        elif filename.endswith(".json"):
            return _parse_json(content)
        else:
            raise HTTPException(status_code=415, detail="Only .csv and .json files are supported")
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {exc}") from exc


def _lead_not_found(lead_id: str):
    raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")


def _job_not_found(job_id: str):
    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}


@app.post("/leads/upload", response_model=UploadResponse, status_code=202)
async def upload_leads(file: UploadFile = File(...)):
    """
    In LOCAL mode: parses the file, runs the full agent pipeline synchronously,
    stores results in memory, and returns immediately — no AWS required.

    In PRODUCTION mode: uploads to S3, writes a DynamoDB job record, fans
    out one SQS message per lead for async Lambda processing.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or "upload.json"
    leads = _parse_file(content, filename)

    if not leads:
        raise HTTPException(status_code=422, detail="No leads found in file")

    batch_id = str(uuid.uuid4())
    job_id   = str(uuid.uuid4())

    if settings.is_local:
        return await _upload_local(leads, batch_id, job_id)
    else:
        return await _upload_aws(content, leads, filename, batch_id, job_id, file.content_type)


async def _upload_local(
    leads: list[RawLead],
    batch_id: str,
    job_id: str,
) -> UploadResponse:
    """Process synchronously and store results in the in-memory store."""
    # Build the set of dedup keys already stored (guard against pre-feature records)
    existing_keys: set[str] = {
        v["dedup_key"] for v in _local_leads.values() if v.get("dedup_key")
    }

    # Intra-batch + cross-batch dedup — filter before any LLM calls
    seen_this_batch: set[str] = set()
    unique_leads: list[RawLead] = []
    duplicate_count = 0

    for lead in leads:
        key = compute_dedup_key(lead.company, lead.contact_email, lead.website)
        if key in existing_keys or key in seen_this_batch:
            duplicate_count += 1
            logger.info("duplicate skipped", extra={"company": lead.company, "key": key})
        else:
            seen_this_batch.add(key)
            unique_leads.append(lead)

    job = BatchJob(
        job_id=job_id,
        batch_id=batch_id,
        status=JobStatus.PROCESSING,
        stats=BatchJobStats(total=len(unique_leads), duplicates=duplicate_count),
    )
    _local_jobs[job_id] = job.model_dump(mode="json")

    stats = BatchJobStats(total=len(unique_leads), duplicates=duplicate_count)
    results = process_batch(leads=unique_leads, batch_id=batch_id, job_id=job_id, stats=stats)

    for lead in results:
        _local_leads[lead.lead_id] = lead.model_dump(mode="json")

    job.stats = stats
    job.mark_completed()
    _local_jobs[job_id] = job.model_dump(mode="json")

    processed = len(results)
    skipped_msg = (
        f", {duplicate_count} duplicate{'s' if duplicate_count != 1 else ''} skipped"
        if duplicate_count else ""
    )
    logger.info("local batch processed", extra={"job_id": job_id, "count": processed, "duplicates": duplicate_count})
    return UploadResponse(
        job_id=job_id,
        batch_id=batch_id,
        lead_count=len(leads),
        duplicate_count=duplicate_count,
        message=f"{processed} lead{'s' if processed != 1 else ''} processed{skipped_msg}.",
    )


async def _upload_aws(
    content: bytes,
    leads: list[RawLead],
    filename: str,
    batch_id: str,
    job_id: str,
    content_type: Optional[str],
) -> UploadResponse:
    """Production path — S3 + DynamoDB + SQS.

    TODO: dedup not implemented for the AWS path.
    Production fix: add a GSI on `dedup_key` in the DynamoDB leads table,
    then query per-lead before enqueue to skip already-stored leads.
    """
    s3_key = f"input/{batch_id}/{filename}"
    storage.upload_raw(content, s3_key, content_type=content_type or "text/csv")

    job = BatchJob(
        job_id=job_id,
        batch_id=batch_id,
        status=JobStatus.PENDING,
        stats=BatchJobStats(total=len(leads)),
        s3_input_key=s3_key,
    )
    db.put_job(job.model_dump(mode="json"))

    sqs.enqueue_batch(
        leads=[lead.model_dump(mode="json") for lead in leads],
        batch_id=batch_id,
        job_id=job_id,
    )

    logger.info("batch enqueued", extra={"job_id": job_id, "lead_count": len(leads)})
    return UploadResponse(
        job_id=job_id,
        batch_id=batch_id,
        lead_count=len(leads),
        message=f"Batch of {len(leads)} leads queued for processing.",
    )


@app.post("/leads/process", response_model=list[EnrichedLead])
async def process_leads_sync(payload: LeadBatch):
    """Synchronous JSON processing — no file upload, returns results directly."""
    if len(payload.leads) > 50:
        raise HTTPException(
            status_code=400,
            detail="Synchronous endpoint limited to 50 leads. Use /leads/upload for larger batches.",
        )
    stats = BatchJobStats(total=len(payload.leads))
    results = process_batch(
        leads=payload.leads,
        batch_id=payload.batch_id,
        job_id="sync",
        stats=stats,
    )
    for lead in results:
        _local_leads[lead.lead_id] = lead.model_dump(mode="json")
    return results


@app.get("/leads", response_model=LeadListResponse)
def list_leads(
    score_min: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
):
    if settings.is_local:
        items = [
            v for v in _local_leads.values()
            if v.get("confidence_score", 0) >= score_min
        ]
        items.sort(key=lambda x: x.get("confidence_score", 0), reverse=True)
        return LeadListResponse(
            leads=[EnrichedLead(**item) for item in items[:limit]],
            total=len(items),
            page=1,
            page_size=limit,
        )

    last_key = json.loads(cursor) if cursor else None
    items, _ = db.scan_leads(score_min=score_min, limit=limit, last_evaluated_key=last_key)
    return LeadListResponse(
        leads=[EnrichedLead(**item) for item in items],
        total=len(items),
        page=1,
        page_size=limit,
    )


@app.get("/leads/export")
def export_leads(score_min: float = Query(0.0, ge=0.0, le=1.0)):
    """Download all current leads as NDJSON — must be defined before /leads/{lead_id}."""
    import json
    from fastapi.responses import StreamingResponse

    if settings.is_local:
        items = [
            v for v in _local_leads.values()
            if v.get("confidence_score", 0) >= score_min
        ]
        items.sort(key=lambda x: x.get("confidence_score", 0), reverse=True)
    else:
        items, _ = db.scan_leads(score_min=score_min, limit=1000)

    ndjson = "\n".join(json.dumps(item, default=str) for item in items)

    return StreamingResponse(
        iter([ndjson]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=leads_export.ndjson"},
    )


@app.get("/leads/{lead_id}", response_model=EnrichedLead)
def get_lead(lead_id: str):
    if settings.is_local:
        item = _local_leads.get(lead_id)
    else:
        item = db.get_lead(lead_id)
    if not item:
        _lead_not_found(lead_id)
    return EnrichedLead(**item)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    if settings.is_local:
        item = _local_jobs.get(job_id)
    else:
        item = db.get_job(job_id)
    if not item:
        _job_not_found(job_id)
    job = BatchJob(**item)
    return JobStatusResponse(
        job_id=job.job_id,
        batch_id=job.batch_id,
        status=job.status,
        stats=job.stats,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


@app.get("/jobs/{job_id}/download")
def get_download_url(job_id: str):
    if settings.is_local:
        raise HTTPException(status_code=501, detail="Download not available in local mode.")
    item = db.get_job(job_id)
    if not item:
        _job_not_found(job_id)
    job = BatchJob(**item)
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Job has not completed yet")
    if not job.s3_output_key:
        raise HTTPException(status_code=404, detail="No output file found for this job")
    return {"download_url": storage.presigned_download_url(job.s3_output_key), "expires_in": 3600}


@app.delete("/leads", status_code=200)
def clear_leads():
    """Clear all leads from the in-memory store (local mode only)."""
    if not settings.is_local:
        raise HTTPException(status_code=403, detail="Clear not available in production.")
    count = len(_local_leads)
    _local_leads.clear()
    logger.info("leads cleared", extra={"count": count})
    return {"cleared": count}


@app.get("/queue/depth")
def queue_depth():
    if settings.is_local:
        return {"depth": 0}
    try:
        return {"depth": sqs.get_queue_depth()}
    except Exception:
        logger.warning("could not fetch queue depth", exc_info=True)
        return {"depth": None, "error": "unavailable"}
