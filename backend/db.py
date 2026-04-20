import json
import logging
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_resource():
    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.is_local:
        kwargs["endpoint_url"] = "http://localhost:8000"  # DynamoDB local
    return boto3.resource("dynamodb", **kwargs)


def _table(name: str):
    return _get_resource().Table(name)


# ---------------------------------------------------------------------------
# Leads table
# ---------------------------------------------------------------------------


def _floats_to_decimals(obj: Any) -> Any:
    """DynamoDB SDK rejects float — round-trip through JSON to convert to Decimal."""
    return json.loads(json.dumps(obj), parse_float=Decimal)


def _decimals_to_floats(obj: Any) -> Any:
    """DynamoDB returns Decimal — convert back to float for Pydantic."""
    return json.loads(json.dumps(obj, default=str))


def put_lead(lead: dict) -> bool:
    """
    Write lead to DynamoDB. Returns True if written, False if already exists.
    Conditional write prevents duplicate SQS retries from double-counting stats.
    """
    try:
        _table(settings.dynamodb_leads_table).put_item(
            Item=_floats_to_decimals(lead),
            ConditionExpression="attribute_not_exists(lead_id)",
        )
        logger.info("stored lead", extra={"lead_id": lead.get("lead_id")})
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info(
                "duplicate lead skipped", extra={"lead_id": lead.get("lead_id")}
            )
            return False
        logger.exception("failed to store lead", extra={"lead_id": lead.get("lead_id")})
        raise


def get_lead(lead_id: str) -> Optional[dict]:
    response = _table(settings.dynamodb_leads_table).get_item(Key={"lead_id": lead_id})
    item = response.get("Item")
    return _decimals_to_floats(item) if item else None


def query_leads_by_batch(batch_id: str) -> list[dict]:
    response = _table(settings.dynamodb_leads_table).query(
        IndexName="batch_id-index",
        KeyConditionExpression=Key("batch_id").eq(batch_id),
    )
    return response.get("Items", [])


def lead_exists_by_dedup_key(dedup_key: str) -> bool:
    """Query the dedup_key GSI — O(1) check without a full table scan."""
    response = _table(settings.dynamodb_leads_table).query(
        IndexName="dedup_key-index",
        KeyConditionExpression=Key("dedup_key").eq(dedup_key),
        Select="COUNT",
    )
    return response["Count"] > 0


def count_leads(score_min: float = 0.0) -> int:
    """Full table scan returning only the count — no item data transferred."""
    kwargs: dict[str, Any] = {
        "Select": "COUNT",
        "FilterExpression": "confidence_score >= :min",
        "ExpressionAttributeValues": {":min": Decimal(str(score_min))},
    }
    total = 0
    while True:
        response = _table(settings.dynamodb_leads_table).scan(**kwargs)
        total += response["Count"]
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return total


def scan_leads(
    score_min: float = 0.0,
    limit: int = 20,
    last_evaluated_key: Optional[dict] = None,
) -> tuple[list[dict], Optional[dict]]:
    """
    Single DynamoDB scan page. Limit is passed directly so DynamoDB stops
    after examining `limit` items and returns a LastEvaluatedKey cursor for
    the next page. FilterExpression is applied server-side.
    """
    kwargs: dict[str, Any] = {
        "Limit": limit,
        "FilterExpression": "confidence_score >= :min",
        "ExpressionAttributeValues": {":min": Decimal(str(score_min))},
    }
    if last_evaluated_key:
        kwargs["ExclusiveStartKey"] = last_evaluated_key

    response = _table(settings.dynamodb_leads_table).scan(**kwargs)
    items = [_decimals_to_floats(item) for item in response.get("Items", [])]
    return items, response.get("LastEvaluatedKey")


# ---------------------------------------------------------------------------
# Batch jobs table
# ---------------------------------------------------------------------------


def put_job(job: dict) -> None:
    try:
        _table(settings.dynamodb_jobs_table).put_item(Item=_floats_to_decimals(job))
        logger.info("stored job", extra={"job_id": job.get("job_id")})
    except ClientError:
        logger.exception("failed to store job", extra={"job_id": job.get("job_id")})
        raise


def get_job(job_id: str) -> Optional[dict]:
    response = _table(settings.dynamodb_jobs_table).get_item(Key={"job_id": job_id})
    item = response.get("Item")
    return _decimals_to_floats(item) if item else None


def update_job_status(job_id: str, updates: dict) -> None:
    """Partial update — pass only the fields that changed."""
    set_expr = ", ".join(f"#f_{k} = :{k}" for k in updates)
    attr_names = {f"#f_{k}": k for k in updates}
    attr_values = {f":{k}": v for k, v in updates.items()}

    _table(settings.dynamodb_jobs_table).update_item(
        Key={"job_id": job_id},
        UpdateExpression=f"SET {set_expr}",
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )
