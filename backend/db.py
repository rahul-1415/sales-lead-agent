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
            logger.info("duplicate lead skipped", extra={"lead_id": lead.get("lead_id")})
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


def scan_leads(
    score_min: float = 0.0,
    limit: int = 200,
    last_evaluated_key: Optional[dict] = None,
) -> tuple[list[dict], Optional[dict]]:
    """
    Paginate through the leads table until we collect `limit` matching items.
    DynamoDB Limit applies to items examined (not returned), so we loop until
    we have enough results or exhaust the table.
    """
    table = _table(settings.dynamodb_leads_table)
    filter_expr = "confidence_score >= :min"
    expr_values = {":min": Decimal(str(score_min))}

    collected: list[dict] = []
    last_key = last_evaluated_key

    while len(collected) < limit:
        kwargs: dict[str, Any] = {
            "FilterExpression": filter_expr,
            "ExpressionAttributeValues": expr_values,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        response = table.scan(**kwargs)
        collected.extend(
            _decimals_to_floats(item) for item in response.get("Items", [])
        )
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    return collected[:limit], last_key


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
