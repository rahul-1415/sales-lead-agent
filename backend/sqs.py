import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _client():
    return boto3.client("sqs", region_name=settings.aws_region)


# ---------------------------------------------------------------------------
# Send messages
# ---------------------------------------------------------------------------


def enqueue_lead(lead: dict[str, Any], batch_id: str, job_id: str) -> str:
    """Send a single lead to the processing queue. Returns the SQS message ID."""
    body = json.dumps(
        {"lead": lead, "batch_id": batch_id, "job_id": job_id},
        default=str,
    )
    try:
        response = _client().send_message(
            QueueUrl=settings.sqs_queue_url,
            MessageBody=body,
            MessageAttributes={
                "batch_id": {"StringValue": batch_id, "DataType": "String"},
                "job_id": {"StringValue": job_id, "DataType": "String"},
            },
        )
        msg_id = response["MessageId"]
        logger.info(
            "enqueued lead",
            extra={"message_id": msg_id, "batch_id": batch_id, "job_id": job_id},
        )
        return msg_id
    except ClientError:
        logger.exception("failed to enqueue lead", extra={"batch_id": batch_id})
        raise


def enqueue_batch(leads: list[dict], batch_id: str, job_id: str) -> list[str]:
    """Send up to 10 leads at a time using SQS batch send (reduces API calls)."""
    message_ids: list[str] = []

    for chunk_start in range(0, len(leads), 10):
        chunk = leads[chunk_start : chunk_start + 10]
        entries = [
            {
                "Id": str(i),
                "MessageBody": json.dumps(
                    {"lead": lead, "batch_id": batch_id, "job_id": job_id},
                    default=str,
                ),
                "MessageAttributes": {
                    "batch_id": {"StringValue": batch_id, "DataType": "String"},
                    "job_id": {"StringValue": job_id, "DataType": "String"},
                },
            }
            for i, lead in enumerate(chunk)
        ]
        try:
            response = _client().send_message_batch(
                QueueUrl=settings.sqs_queue_url,
                Entries=entries,
            )
            ids = [m["MessageId"] for m in response.get("Successful", [])]
            message_ids.extend(ids)
            failed = response.get("Failed", [])
            if failed:
                logger.warning(
                    "some messages failed to enqueue",
                    extra={"failed_count": len(failed), "batch_id": batch_id},
                )
        except ClientError:
            logger.exception("batch enqueue failed", extra={"batch_id": batch_id})
            raise

    return message_ids


# ---------------------------------------------------------------------------
# Receive / delete (used by the Lambda processor)
# ---------------------------------------------------------------------------


def receive_messages(max_count: int = 10, wait_seconds: int = 5) -> list[dict]:
    response = _client().receive_message(
        QueueUrl=settings.sqs_queue_url,
        MaxNumberOfMessages=min(max_count, 10),
        WaitTimeSeconds=wait_seconds,
        MessageAttributeNames=["All"],
    )
    return response.get("Messages", [])


def delete_message(receipt_handle: str) -> None:
    _client().delete_message(
        QueueUrl=settings.sqs_queue_url,
        ReceiptHandle=receipt_handle,
    )


def get_queue_depth() -> int:
    """Approximate number of messages currently in the queue."""
    response = _client().get_queue_attributes(
        QueueUrl=settings.sqs_queue_url,
        AttributeNames=["ApproximateNumberOfMessages"],
    )
    return int(response["Attributes"].get("ApproximateNumberOfMessages", 0))
