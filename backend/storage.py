import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _client():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
    )


# ---------------------------------------------------------------------------
# Upload / download raw files
# ---------------------------------------------------------------------------


def upload_raw(file_bytes: bytes, key: str, content_type: str = "text/csv") -> str:
    """Upload a raw lead file to the input bucket. Returns the S3 key."""
    try:
        _client().put_object(
            Bucket=settings.s3_input_bucket,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
        logger.info("uploaded raw file", extra={"bucket": settings.s3_input_bucket, "key": key})
        return key
    except ClientError:
        logger.exception("failed to upload raw file", extra={"key": key})
        raise


def download_raw(key: str) -> bytes:
    """Download a raw lead file from the input bucket."""
    response = _client().get_object(Bucket=settings.s3_input_bucket, Key=key)
    return response["Body"].read()


# ---------------------------------------------------------------------------
# Save / load processed results
# ---------------------------------------------------------------------------


def save_results(leads: list[dict[str, Any]], key: str) -> str:
    """Serialise enriched leads as newline-delimited JSON and write to output bucket."""
    body = "\n".join(json.dumps(lead, default=str) for lead in leads)
    try:
        _client().put_object(
            Bucket=settings.s3_output_bucket,
            Key=key,
            Body=body.encode(),
            ContentType="application/x-ndjson",
        )
        logger.info(
            "saved results",
            extra={"bucket": settings.s3_output_bucket, "key": key, "count": len(leads)},
        )
        return key
    except ClientError:
        logger.exception("failed to save results", extra={"key": key})
        raise


def load_results(key: str) -> list[dict[str, Any]]:
    response = _client().get_object(Bucket=settings.s3_output_bucket, Key=key)
    lines = response["Body"].read().decode().strip().splitlines()
    return [json.loads(line) for line in lines if line]


# ---------------------------------------------------------------------------
# Presigned URLs (for dashboard downloads)
# ---------------------------------------------------------------------------


def presigned_download_url(key: str, expires_in: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_output_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
