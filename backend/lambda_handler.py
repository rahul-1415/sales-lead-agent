"""
Lambda entry points.

Two handlers in one file — both deployed as separate Lambda functions:

  lead_processor   — triggered by SQS, processes individual leads
  api_handler      — triggered by API Gateway, serves the FastAPI app via Mangum

Keeping them in one file means shared imports are loaded once per cold start,
reducing overall cold start time for the less-frequently-invoked processor.
"""

import json
import logging
import os
from typing import Any

from mangum import Mangum

import db
import storage
from agent.models import BatchJobStats, JobStatus, RawLead
from agent.orchestrator import process_batch
from api import app
from tools.embeddings import build_icp_index

# ---------------------------------------------------------------------------
# Logging — structured JSON in Lambda, human-readable locally
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Warm up the ICP embedding index on cold start.
# This runs once per container lifetime — subsequent invocations reuse it.
# ---------------------------------------------------------------------------

build_icp_index()

# ---------------------------------------------------------------------------
# API Gateway handler (FastAPI via Mangum)
# ---------------------------------------------------------------------------

api_handler = Mangum(app, lifespan="off")

# ---------------------------------------------------------------------------
# SQS Lead Processor
# ---------------------------------------------------------------------------


def lead_processor(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Triggered by SQS. Each SQS message contains one RawLead + batch/job metadata.

    SQS batch size is configured in CloudFormation (ReportBatchItemFailures enabled),
    so we return partial failures instead of failing the entire batch.
    This lets Lambda retry only the messages that actually failed.
    """
    batch_item_failures: list[dict] = []
    records = event.get("Records", [])

    logger.info("received SQS batch", extra={"record_count": len(records)})

    for record in records:
        message_id = record["messageId"]
        try:
            body = json.loads(record["body"])
            raw_lead = RawLead(**body["lead"])
            batch_id: str = body["batch_id"]
            job_id: str = body["job_id"]

            stats = BatchJobStats(total=1)
            results = process_batch(
                leads=[raw_lead],
                batch_id=batch_id,
                job_id=job_id,
                stats=stats,
            )

            # Persist enriched lead
            for enriched in results:
                db.put_lead(enriched.model_dump(mode="json"))

            # Increment job counters atomically
            _update_job_progress(job_id, stats)

        except Exception:
            logger.exception(
                "failed to process SQS record",
                extra={"message_id": message_id},
            )
            batch_item_failures.append({"itemIdentifier": message_id})

    # ReportBatchItemFailures: only failed messages are retried
    return {"batchItemFailures": batch_item_failures}


def _update_job_progress(job_id: str, stats: BatchJobStats) -> None:
    """
    Increments the job's stats counters in DynamoDB.
    Uses ADD (atomic increment) expressions to handle concurrent Lambda
    invocations updating the same job safely.
    """
    import boto3
    from config import get_settings
    cfg = get_settings()

    dynamodb = boto3.resource("dynamodb", region_name=cfg.aws_region)
    table = dynamodb.Table(cfg.dynamodb_jobs_table)

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=(
            "ADD #processed :p, #priority :pr, #standard :st, "
            "#research :re, #rejected :rj, #errors :er "
            "SET #updated = :now"
        ),
        ExpressionAttributeNames={
            "#processed": "stats.processed",
            "#priority": "stats.priority",
            "#standard": "stats.standard",
            "#research": "stats.research",
            "#rejected": "stats.rejected",
            "#errors": "stats.errors",
            "#updated": "updated_at",
        },
        ExpressionAttributeValues={
            ":p": stats.processed,
            ":pr": stats.priority,
            ":st": stats.standard,
            ":re": stats.research,
            ":rj": stats.rejected,
            ":er": stats.errors,
            ":now": _now_iso(),
        },
    )


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Batch orchestrator (separate Lambda — triggered by API Gateway upload)
# Splits a large S3 file into individual SQS messages.
# Kept here for completeness; extracted to its own function in CloudFormation.
# ---------------------------------------------------------------------------


def batch_orchestrator(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Triggered directly (not via SQS) when a file lands in the S3 input bucket.
    Downloads the file, parses it, and fans out one SQS message per lead.

    This separation means the API can return a job_id instantly — it only
    writes one S3 object and one DynamoDB record, then this function does
    the fan-out asynchronously.
    """
    import sqs as sqs_module

    for s3_record in event.get("Records", []):
        bucket = s3_record["s3"]["bucket"]["name"]
        key = s3_record["s3"]["object"]["key"]

        logger.info("orchestrating batch from S3", extra={"bucket": bucket, "key": key})

        try:
            # Derive job context from the S3 key path: input/{batch_id}/{filename}
            parts = key.split("/")
            batch_id = parts[1] if len(parts) >= 3 else key
            job_record = _find_job_by_batch(batch_id)
            if not job_record:
                logger.error("no job found for batch", extra={"batch_id": batch_id})
                continue

            job_id = job_record["job_id"]

            raw_bytes = storage.download_raw(key)
            filename = parts[-1]

            if filename.endswith(".csv"):
                from api import _parse_csv
                leads = _parse_csv(raw_bytes)
            else:
                from api import _parse_json
                leads = _parse_json(raw_bytes)

            sqs_module.enqueue_batch(
                leads=[lead.model_dump(mode="json") for lead in leads],
                batch_id=batch_id,
                job_id=job_id,
            )

            db.update_job_status(job_id, {"status": JobStatus.PROCESSING.value})
            logger.info(
                "batch fanned out",
                extra={"job_id": job_id, "lead_count": len(leads)},
            )

        except Exception:
            logger.exception("batch orchestration failed", extra={"key": key})

    return {"statusCode": 200}


def _find_job_by_batch(batch_id: str) -> dict | None:
    """Queries the jobs table batch_id-index GSI for a matching batch_id."""
    import boto3
    from boto3.dynamodb.conditions import Key
    from config import get_settings

    cfg = get_settings()
    table = boto3.resource("dynamodb", region_name=cfg.aws_region).Table(cfg.dynamodb_jobs_table)
    response = table.query(
        IndexName="batch_id-index",
        KeyConditionExpression=Key("batch_id").eq(batch_id),
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None
