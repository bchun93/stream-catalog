"""SNS -> SQS completion consumer.

The processing logic is isolated in the pure ``process_completion(message_body)`` so it can be
driven by the scheduled HTTP consumer now, or an SQS-triggered Lambda later, unchanged.

Flow per message:
  1. Parse the SNS envelope -> inner Rekognition notification (JobId, Status, JobTag, ...).
  2. Identify (asset_id, feature) via the gsi_job_id lookup, falling back to JobTag.
  3. SUCCEEDED: call the matching Get* paginated, map -> detections, batch-write, mark SUCCEEDED.
     FAILED: mark FAILED with the status message.
  4. The caller deletes the SQS message only when ``ProcessOutcome.ok`` is True (delete after
     the DB write). Detection writes use deterministic sort keys, so reprocessing a redelivered
     message is idempotent.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.services.aws_clients import rekognition_client, sqs_client
from app.services.rekognition import ddb
from app.services.rekognition.constants import Feature, JobStatus

if TYPE_CHECKING:
    from mypy_boto3_rekognition.client import RekognitionClient

logger = logging.getLogger(__name__)

_PAGE_SIZE = 1000


class ConsumerConfigError(RuntimeError):
    """Missing SQS configuration -> HTTP 503."""


@dataclass
class ProcessOutcome:
    ok: bool  # True -> safe to delete the SQS message
    summary: str
    job_id: str | None = None


@dataclass
class DrainResult:
    received: int = 0
    processed: int = 0
    deleted: int = 0
    failed: int = 0
    messages: list[str] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_notification(message_body: str) -> dict[str, Any]:
    """Unwrap the SNS envelope (RawMessageDelivery=false) to the Rekognition notification."""
    outer = json.loads(message_body)
    msg_type = outer.get("Type")
    if msg_type == "SubscriptionConfirmation":
        # Shouldn't reach an SQS subscription, but ignore defensively.
        return {"_ignore": True}
    inner = outer.get("Message")
    if isinstance(inner, str):
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            return outer  # not JSON; treat envelope as the payload
    # RawMessageDelivery=true fallback: body IS the notification.
    return outer


def _identify(notification: dict[str, Any]) -> tuple[str, Feature] | None:
    job_id = notification.get("JobId")
    if job_id:
        job = ddb.get_job_by_aws_job_id(job_id)
        if job and job.get("asset_id") and job.get("feature"):
            try:
                return str(job["asset_id"]), Feature(job["feature"])
            except ValueError:
                pass
    # Fallback: JobTag we set == "{asset_id}:{FEATURE}".
    job_tag = notification.get("JobTag") or ""
    if ":" in job_tag:
        asset_id, _, feature_raw = job_tag.partition(":")
        try:
            return asset_id, Feature(feature_raw)
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------- mappers


def _collect_segments(
    rek: "RekognitionClient", job_id: str, asset_id: str
) -> list[ddb.DetectionItem]:
    items: list[ddb.DetectionItem] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"JobId": job_id, "MaxResults": _PAGE_SIZE}
        if token:
            kwargs["NextToken"] = token
        resp = rek.get_segment_detection(**kwargs)
        for seg in resp.get("Segments", []):
            seg_type = seg.get("Type")
            start_ms = seg.get("StartTimestampMillis")
            end_ms = seg.get("EndTimestampMillis")
            if seg_type == "TECHNICAL_CUE":
                cue = seg.get("TechnicalCueSegment") or {}
                kind = cue.get("Type") or "TechnicalCue"
                confidence = cue.get("Confidence")
            else:  # SHOT
                shot = seg.get("ShotSegment") or {}
                kind = "Shot"
                confidence = shot.get("Confidence")
            seed = f"{kind}|{start_ms}|{end_ms}"
            items.append(
                ddb.DetectionItem(
                    asset_id=asset_id,
                    sk=ddb.build_detection_sk(Feature.SEGMENT, start_ms, seed),
                    feature=Feature.SEGMENT.value,
                    kind=kind,
                    name=kind,
                    confidence=confidence,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    job_id=job_id,
                    created_at=_now_iso(),
                )
            )
        token = resp.get("NextToken")
        if not token:
            break
    return items


def _collect_moderation(
    rek: "RekognitionClient", job_id: str, asset_id: str
) -> list[ddb.DetectionItem]:
    items: list[ddb.DetectionItem] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"JobId": job_id, "MaxResults": _PAGE_SIZE}
        if token:
            kwargs["NextToken"] = token
        resp = rek.get_content_moderation(**kwargs)
        for entry in resp.get("ModerationLabels", []):
            ts = entry.get("Timestamp")
            label = entry.get("ModerationLabel") or {}
            name = label.get("Name") or "Unknown"
            parent = label.get("ParentName") or None
            seed = f"{name}|{parent}|{ts}"
            items.append(
                ddb.DetectionItem(
                    asset_id=asset_id,
                    sk=ddb.build_detection_sk(Feature.MODERATION, ts, seed),
                    feature=Feature.MODERATION.value,
                    kind=name,
                    name=parent or name,
                    confidence=label.get("Confidence"),
                    timestamp_ms=ts,
                    job_id=job_id,
                    created_at=_now_iso(),
                )
            )
        token = resp.get("NextToken")
        if not token:
            break
    return items


def _collect_labels(
    rek: "RekognitionClient", job_id: str, asset_id: str
) -> list[ddb.DetectionItem]:
    items: list[ddb.DetectionItem] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"JobId": job_id, "MaxResults": _PAGE_SIZE}
        if token:
            kwargs["NextToken"] = token
        resp = rek.get_label_detection(**kwargs)
        for entry in resp.get("Labels", []):
            ts = entry.get("Timestamp")
            label = entry.get("Label") or {}
            name = label.get("Name") or "Unknown"
            instances = label.get("Instances") or []
            bbox = instances[0].get("BoundingBox") if instances else None
            seed = f"{name}|{ts}"
            items.append(
                ddb.DetectionItem(
                    asset_id=asset_id,
                    sk=ddb.build_detection_sk(Feature.LABELS, ts, seed),
                    feature=Feature.LABELS.value,
                    kind=name,
                    name=name,
                    confidence=label.get("Confidence"),
                    timestamp_ms=ts,
                    bounding_box=bbox,
                    job_id=job_id,
                    created_at=_now_iso(),
                )
            )
        token = resp.get("NextToken")
        if not token:
            break
    return items


_COLLECTORS = {
    Feature.SEGMENT: _collect_segments,
    Feature.MODERATION: _collect_moderation,
    Feature.LABELS: _collect_labels,
}


def process_completion(message_body: str) -> ProcessOutcome:
    """Pure handler for one SQS message body. Raises nothing for expected paths; returns an
    outcome whose ``ok`` flag tells the caller whether to delete the message."""
    notification = _parse_notification(message_body)
    if notification.get("_ignore"):
        return ProcessOutcome(ok=True, summary="ignored non-notification message")

    job_id = notification.get("JobId")
    status = (notification.get("Status") or "").upper()
    if not job_id:
        return ProcessOutcome(ok=False, summary="message has no JobId")

    identity = _identify(notification)
    if not identity:
        # Can't map to an asset/feature -> leave for retry/DLQ rather than dropping silently.
        return ProcessOutcome(
            ok=False, summary=f"unidentifiable job {job_id} (no row/JobTag)", job_id=job_id
        )
    asset_id, feature = identity

    if status == "FAILED":
        reason = notification.get("StatusMessage") or "Rekognition reported FAILED"
        ddb.update_job_status(
            asset_id=asset_id, feature=feature, status=JobStatus.FAILED, error=reason
        )
        logger.info("rekognition job FAILED", extra={"aws_job_id": job_id, "asset_id": asset_id})
        return ProcessOutcome(ok=True, summary=f"{feature.value} job {job_id} FAILED", job_id=job_id)

    if status != "SUCCEEDED":
        logger.warning("unexpected Rekognition status %s for %s", status, job_id)
        return ProcessOutcome(ok=True, summary=f"ignored status {status} for {job_id}", job_id=job_id)

    rek = rekognition_client()
    detections = _COLLECTORS[feature](rek, job_id, asset_id)
    written = ddb.batch_put_detections(detections)
    ddb.update_job_status(asset_id=asset_id, feature=feature, status=JobStatus.SUCCEEDED)
    logger.info(
        "rekognition job SUCCEEDED",
        extra={"aws_job_id": job_id, "asset_id": asset_id, "feature": feature.value, "detections": written},
    )
    return ProcessOutcome(
        ok=True,
        summary=f"{feature.value} job {job_id} SUCCEEDED, {written} detections",
        job_id=job_id,
    )


def drain_queue(*, max_batches: int = 10, wait_time_seconds: int = 10) -> DrainResult:
    """Long-poll SQS and process up to ``max_batches`` batches of 10. Deletes a message only
    after its DB write succeeds (at-least-once)."""
    queue_url = (settings.rekognition_sqs_queue_url or "").strip()
    if not queue_url:
        raise ConsumerConfigError(
            "REKOGNITION_SQS_QUEUE_URL is not configured (see docs/REKOGNITION_AWS_SETUP.md)."
        )

    sqs = sqs_client()
    result = DrainResult()
    for _ in range(max_batches):
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=wait_time_seconds,
        )
        messages = resp.get("Messages", [])
        if not messages:
            break
        for message in messages:
            result.received += 1
            try:
                outcome = process_completion(message["Body"])
            except Exception as exc:  # noqa: BLE001 - one bad message shouldn't stop the drain
                result.failed += 1
                logger.exception("process_completion raised; leaving message for retry/DLQ")
                result.messages.append(f"error: {exc}")
                continue
            if outcome.ok:
                sqs.delete_message(
                    QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                )
                result.deleted += 1
                result.processed += 1
            else:
                result.failed += 1
            result.messages.append(outcome.summary)
    return result
