"""Typed DynamoDB access layer for Rekognition jobs and detections.

Access patterns served:
  (a) consumer looks up a job by JobId          -> get_job_by_aws_job_id (GSI)
  (b) list jobs for an asset                    -> list_jobs_for_asset (Query PK)
  (c) detections for an asset, by feature, time-ordered -> query_detections (begins_with sk)
  (d) idempotent job creation per (asset, feature)      -> put_job (conditional PutItem)

DynamoDB constraints respected: BatchWriteItem chunked to 25 with UnprocessedItems retry;
Query paginated on LastEvaluatedKey; numbers stored as Decimal; items kept small.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Iterator, TypedDict

from boto3.dynamodb.conditions import Key

from app.config import settings
from app.services.aws_clients import detections_table, dynamodb_resource, jobs_table
from app.services.rekognition.constants import (
    SK_TIME_PAD_WIDTH,
    Feature,
    JobStatus,
)

logger = logging.getLogger(__name__)

_GSI_JOB_ID = "gsi_job_id"
_MAX_BATCH = 25
_BATCH_RETRY_ATTEMPTS = 6
# Safety cap so an unbounded read can't fan out to thousands of items / RCU.
_DEFAULT_MAX_DETECTIONS = 5000


class JobItem(TypedDict, total=False):
    asset_id: str
    feature: str
    aws_job_id: str
    client_request_token: str
    status: str
    error: str | None
    created_at: str
    updated_at: str


class DetectionItem(TypedDict, total=False):
    asset_id: str
    sk: str
    feature: str
    kind: str
    name: str | None
    confidence: float | None
    timestamp_ms: int | None
    start_ms: int | None
    end_ms: int | None
    bounding_box: dict[str, Any] | None
    job_id: str
    created_at: str


class JobConflictError(RuntimeError):
    """Raised when a job for (asset_id, feature) already exists and is not retryable."""

    def __init__(self, asset_id: str, feature: str, existing: JobItem | None) -> None:
        self.asset_id = asset_id
        self.feature = feature
        self.existing = existing
        super().__init__(
            f"A Rekognition {feature} job already exists for asset {asset_id}."
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_ddb(value: Any) -> Any:
    """Recursively convert Python values to DynamoDB-safe types (float -> Decimal)."""
    return json.loads(json.dumps(value, default=str), parse_float=Decimal)


def _from_ddb(value: Any) -> Any:
    """Recursively convert DynamoDB types back to JSON-friendly Python (Decimal -> int/float)."""
    if isinstance(value, list):
        return [_from_ddb(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_ddb(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        as_int = int(value)
        return as_int if value == as_int else float(value)
    return value


def _is_conditional_failure(exc: Exception) -> bool:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    return code == "ConditionalCheckFailedException"


# --------------------------------------------------------------------------- jobs


def put_job(
    *,
    asset_id: str,
    feature: Feature,
    aws_job_id: str,
    client_request_token: str,
) -> JobItem:
    """Idempotently create an IN_PROGRESS job row.

    Conditional on the (asset_id, feature) key not existing, OR a prior row in FAILED state
    (so a failed feature can be re-run, but an IN_PROGRESS/SUCCEEDED one cannot be duplicated).
    Raises ``JobConflictError`` if a non-retryable row already exists.
    """
    now = _now_iso()
    item: JobItem = {
        "asset_id": asset_id,
        "feature": feature.value,
        "aws_job_id": aws_job_id,
        "client_request_token": client_request_token,
        "status": JobStatus.IN_PROGRESS.value,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        jobs_table().put_item(
            Item=_to_ddb(item),
            ConditionExpression="attribute_not_exists(asset_id) OR #st = :failed",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues=_to_ddb({":failed": JobStatus.FAILED.value}),
        )
    except Exception as exc:  # noqa: BLE001 - inspect botocore error code
        if _is_conditional_failure(exc):
            existing = get_job(asset_id=asset_id, feature=feature)
            raise JobConflictError(asset_id, feature.value, existing) from exc
        raise
    logger.info(
        "rekognition job created",
        extra={"asset_id": asset_id, "feature": feature.value, "aws_job_id": aws_job_id},
    )
    return item


def get_job(*, asset_id: str, feature: Feature) -> JobItem | None:
    resp = jobs_table().get_item(Key={"asset_id": asset_id, "feature": feature.value})
    item = resp.get("Item")
    return _from_ddb(item) if item else None  # type: ignore[return-value]


def get_job_by_aws_job_id(aws_job_id: str) -> JobItem | None:
    """Consumer lookup-by-JobId via the gsi_job_id GSI.

    NOTE: the GSI projects only ``asset_id``, ``feature``, ``status`` (+ the ``aws_job_id``
    key). Callers needing the full row (e.g. ``client_request_token``, ``created_at``) must
    re-fetch with ``get_job(asset_id, feature)``. The consumer only needs asset_id+feature,
    which are projected.
    """
    resp = jobs_table().query(
        IndexName=_GSI_JOB_ID,
        KeyConditionExpression=Key("aws_job_id").eq(aws_job_id),
        Limit=1,
    )
    items = resp.get("Items") or []
    return _from_ddb(items[0]) if items else None  # type: ignore[return-value]


def list_jobs_for_asset(asset_id: str) -> list[JobItem]:
    resp = jobs_table().query(KeyConditionExpression=Key("asset_id").eq(asset_id))
    return [_from_ddb(i) for i in resp.get("Items", [])]  # type: ignore[misc]


def update_job_status(
    *,
    asset_id: str,
    feature: Feature,
    status: JobStatus,
    error: str | None = None,
) -> None:
    jobs_table().update_item(
        Key={"asset_id": asset_id, "feature": feature.value},
        UpdateExpression="SET #st = :s, #e = :e, updated_at = :u",
        ExpressionAttributeNames={"#st": "status", "#e": "error"},
        ExpressionAttributeValues=_to_ddb(
            {":s": status.value, ":e": error, ":u": _now_iso()}
        ),
    )
    logger.info(
        "rekognition job status updated",
        extra={"asset_id": asset_id, "feature": feature.value, "status": status.value},
    )


# ---------------------------------------------------------------------- detections


def build_detection_sk(feature: Feature, time_ms: int | None, dedupe_seed: str) -> str:
    """Deterministic sort key: ``FEATURE#<zero-padded time>#<short stable hash>``.

    Zero-padding makes lexicographic order chronological. The hash of ``dedupe_seed`` makes
    the sk deterministic so reprocessing a redelivered SQS message upserts the same row
    instead of duplicating it.
    """
    padded = str(max(0, time_ms or 0)).zfill(SK_TIME_PAD_WIDTH)
    short = hashlib.sha1(
        dedupe_seed.encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:10]
    return f"{feature.value}#{padded}#{short}"


def _chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def batch_put_detections(items: Iterable[DetectionItem]) -> int:
    """Bulk-write detections in chunks of 25, retrying UnprocessedItems with backoff.

    Returns the number of items written. Idempotent when callers use deterministic ``sk``.
    """
    table_name = settings.ddb_detections_table
    ddb = dynamodb_resource()
    materialized = list(items)
    written = 0

    for chunk in _chunks(materialized, _MAX_BATCH):
        request_items: dict[str, Any] = {
            table_name: [{"PutRequest": {"Item": _to_ddb(it)}} for it in chunk]
        }
        backoff = 0.2
        for attempt in range(_BATCH_RETRY_ATTEMPTS):
            resp = ddb.batch_write_item(RequestItems=request_items)
            unprocessed = resp.get("UnprocessedItems") or {}
            if not unprocessed:
                break
            request_items = unprocessed
            if attempt == _BATCH_RETRY_ATTEMPTS - 1:
                remaining = sum(len(v) for v in unprocessed.values())
                raise RuntimeError(
                    f"DynamoDB batch write left {remaining} unprocessed item(s) "
                    f"after {_BATCH_RETRY_ATTEMPTS} attempts."
                )
            time.sleep(backoff)
            backoff *= 2
        written += len(chunk)

    if written:
        logger.info("rekognition detections written", extra={"count": written})
    return written


def query_detections(
    *,
    asset_id: str,
    feature: Feature | None = None,
    limit: int | None = None,
) -> list[DetectionItem]:
    """Time-ordered detections for an asset, optionally filtered by feature.

    Paginates over LastEvaluatedKey (each Query page returns <= 1 MB) and pushes the bound
    server-side via ``Limit``. An unbounded call is capped at ``_DEFAULT_MAX_DETECTIONS`` to
    protect memory/RCU.
    """
    table = detections_table()
    key_cond = Key("asset_id").eq(asset_id)
    if feature is not None:
        key_cond = key_cond & Key("sk").begins_with(f"{feature.value}#")

    cap = limit if limit is not None else _DEFAULT_MAX_DETECTIONS
    items: list[dict[str, Any]] = []
    last_key: dict[str, Any] | None = None
    while len(items) < cap:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": key_cond,
            "Limit": cap - len(items),
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")  # type: ignore[assignment]
        if not last_key:
            break

    return [_from_ddb(i) for i in items[:cap]]  # type: ignore[return-value]
