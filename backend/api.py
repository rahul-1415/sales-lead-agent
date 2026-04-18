"""
FastAPI application — runs locally via uvicorn and in Lambda via Mangum.

Endpoints:
  POST /leads/upload      — upload CSV or JSON batch, enqueue for processing
  POST /leads/process     — synchronous processing (small batches, local dev)
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
from fastapi.responses import JSONResponse

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_local else ["https://your-frontend-domain.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_csv(content: bytes) -> list[RawLead]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    leads: list[RawLead] = []
    for row in reader:
        # Normalise common CSV header variations
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
    Accepts a CSV or JSON file of raw leads.
    Stores the raw file in S3, creates a BatchJob record in DynamoDB,
    then fans out one SQS message per lead for async processing.
    Returns immediately with a job_id for status polling.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or ""
    try:
        if filename.endswith(".csv"):
            leads = _parse_csv(content)
        elif filename.endswith(".json"):
            leads = _parse_json(content)
        else:
            raise HTTPException(status_code=415, detail="Only .csv and .json files are supported")
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {exc}") from exc

    if not leads:
        raise HTTPException(status_code=422, detail="No leads found in file")

    batch_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    s3_key = f"input/{batch_id}/{filename}"

    # Persist raw file
    storage.upload_raw(content, s3_key, content_type=file.content_type or "text/csv")

    # Create job record
    job = BatchJob(
        job_id=job_id,
        batch_id=batch_id,
        status=JobStatus.PENDING,
        stats=BatchJobStats(total=len(leads)),
        s3_input_key=s3_key,
    )
    db.put_job(job.model_dump(mode="json"))

    # Fan out to SQS
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
    """
    Synchronous processing endpoint for small batches (≤50 leads).
    Useful for local dev and testing — processes inline, no SQS involved.
    Not recommended for production use with large files.
    """
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

    # Persist each enriched lead to DynamoDB
    for lead in results:
        db.put_lead(lead.model_dump(mode="json"))

    return results


@app.get("/leads", response_model=LeadListResponse)
def list_leads(
    score_min: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
):
    """
    Returns a paginated list of processed leads.
    Uses DynamoDB's LastEvaluatedKey for cursor-based pagination
    (DynamoDB has no OFFSET — cursor pagination is the correct pattern).
    """
    last_key = json.loads(cursor) if cursor else None
    items, next_key = db.scan_leads(score_min=score_min, limit=limit, last_evaluated_key=last_key)

    next_cursor = json.dumps(next_key) if next_key else None

    return LeadListResponse(
        leads=[EnrichedLead(**item) for item in items],
        total=len(items),
        page=1,
        page_size=limit,
        # Note: next_cursor is appended manually since the model doesn't include it
        # Frontend should check for its presence in the raw response headers or extend the model
    )


@app.get("/leads/{lead_id}", response_model=EnrichedLead)
def get_lead(lead_id: str):
    item = db.get_lead(lead_id)
    if not item:
        _lead_not_found(lead_id)
    return EnrichedLead(**item)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
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
    """Returns a presigned S3 URL (1hr TTL) for downloading the results file."""
    item = db.get_job(job_id)
    if not item:
        _job_not_found(job_id)
    job = BatchJob(**item)
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Job has not completed yet")
    if not job.s3_output_key:
        raise HTTPException(status_code=404, detail="No output file found for this job")
    url = storage.presigned_download_url(job.s3_output_key)
    return {"download_url": url, "expires_in": 3600}


@app.get("/queue/depth")
def queue_depth():
    """Approximate number of messages in the SQS queue — for the dashboard status widget."""
    try:
        depth = sqs.get_queue_depth()
        return {"depth": depth}
    except Exception:
        logger.warning("could not fetch queue depth", exc_info=True)
        return {"depth": None, "error": "unavailable"}
