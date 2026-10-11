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
from app.services.rekognition.constants import EVALUATION_FEATURES, Feature, JobStatus
from app.services.rekognition.evaluate import Finding, evaluate

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
) -> tuple[list[ddb.DetectionItem], dict[str, Any] | None, dict[str, Any] | None]:
    items: list[ddb.DetectionItem] = []
    token: str | None = None
    video_metadata: dict[str, Any] | None = None
    audio_metadata: dict[str, Any] | None = None
    first_page = True
    while True:
        kwargs: dict[str, Any] = {"JobId": job_id, "MaxResults": _PAGE_SIZE}
        if token:
            kwargs["NextToken"] = token
        resp = rek.get_segment_detection(**kwargs)
        if first_page:
            video_metadata = _first_metadata(resp, "VideoMetadata")
            audio_metadata = _first_metadata(resp, "AudioMetadata")
            first_page = False
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
                    start_timecode=seg.get("StartTimecodeSMPTE"),
                    end_timecode=seg.get("EndTimecodeSMPTE"),
                    job_id=job_id,
                    created_at=_now_iso(),
                )
            )
        token = resp.get("NextToken")
        if not token:
            break
    return items, video_metadata, audio_metadata


def _first_metadata(resp: dict[str, Any], key: str) -> dict[str, Any] | None:
    values = resp.get(key) or []
    if values and isinstance(values[0], dict):
        return values[0]
    return None


def _collect_text(
    rek: "RekognitionClient", job_id: str, asset_id: str
) -> list[ddb.DetectionItem]:
    items: list[ddb.DetectionItem] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"JobId": job_id, "MaxResults": _PAGE_SIZE}
        if token:
            kwargs["NextToken"] = token
        resp = rek.get_text_detection(**kwargs)
        for entry in resp.get("TextDetections", []):
            ts = entry.get("Timestamp")
            det = entry.get("TextDetection") or {}
            text = det.get("DetectedText") or ""
            kind = det.get("Type") or "text"
            geometry = det.get("Geometry") or {}
            bbox = geometry.get("BoundingBox")
            seed = f"{kind}|{text}|{ts}"
            items.append(
                ddb.DetectionItem(
                    asset_id=asset_id,
                    sk=ddb.build_detection_sk(Feature.TEXT, ts, seed),
                    feature=Feature.TEXT.value,
                    kind=kind,
                    name=text,
                    confidence=det.get("Confidence"),
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
    Feature.MODERATION: _collect_moderation,
    Feature.LABELS: _collect_labels,
    Feature.TEXT: _collect_text,
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
    video_metadata = None
    audio_metadata = None
    if feature is Feature.SEGMENT:
        detections, video_metadata, audio_metadata = _collect_segments(rek, job_id, asset_id)
    else:
        collector = _COLLECTORS.get(feature)
        if collector is None:
            return ProcessOutcome(
                ok=True,
                summary=f"ignored unsupported feature {feature.value}",
                job_id=job_id,
            )
        detections = collector(rek, job_id, asset_id)
    written = ddb.batch_put_detections(detections)
    ddb.update_job_status(
        asset_id=asset_id,
        feature=feature,
        status=JobStatus.SUCCEEDED,
        video_metadata=video_metadata,
        audio_metadata=audio_metadata,
    )
    finding_count = _maybe_evaluate(asset_id)
    logger.info(
        "rekognition job SUCCEEDED",
        extra={
            "aws_job_id": job_id,
            "asset_id": asset_id,
            "feature": feature.value,
            "detections": written,
            "findings": finding_count,
        },
    )
    extra = f", {finding_count} findings" if finding_count is not None else ""
    return ProcessOutcome(
        ok=True,
        summary=f"{feature.value} job {job_id} SUCCEEDED, {written} detections{extra}",
        job_id=job_id,
    )


def _load_asset_qc_context(asset_id: str) -> tuple[float | None, str | None]:
    try:
        pk = int(asset_id)
    except ValueError:
        return None, None
    try:
        from app.database import SessionLocal
        from app.models.media_asset import MediaAsset
        from app.models.title import Title
    except Exception:
        logger.debug("asset QC context imports unavailable", exc_info=True)
        return None, None
    db = SessionLocal()
    try:
        asset = db.query(MediaAsset).filter(MediaAsset.id == pk).first()
        if not asset:
            return None, None
        rating = None
        if asset.title_id:
            title = db.query(Title).filter(Title.id == asset.title_id).first()
            rating = title.rating if title else None
        duration = asset.duration_seconds
        return (float(duration) if duration is not None else None), rating
    except Exception:
        logger.exception("asset QC context load failed for %s", asset_id)
        return None, None
    finally:
        db.close()


def _findings_to_items(asset_id: str, findings: list[Finding]) -> list[ddb.DetectionItem]:
    now = _now_iso()
    items: list[ddb.DetectionItem] = []
    for finding in findings:
        seed = f"{finding.rule_id}|{finding.start_ms}|{finding.message}"
        items.append(
            ddb.DetectionItem(
                asset_id=asset_id,
                sk=ddb.build_detection_sk(Feature.FINDING, finding.start_ms, seed),
                feature=Feature.FINDING.value,
                kind=finding.rule_id,
                name=finding.severity,
                rule_id=finding.rule_id,
                severity=finding.severity,
                message=finding.message,
                start_ms=finding.start_ms,
                end_ms=finding.end_ms,
                evidence=finding.evidence,
                created_at=now,
            )
        )
    return items


def _maybe_evaluate(asset_id: str) -> int | None:
    jobs = {job.get("feature"): job for job in ddb.list_jobs_for_asset(asset_id)}
    if any(
        (jobs.get(feature.value) or {}).get("status") != JobStatus.SUCCEEDED.value
        for feature in EVALUATION_FEATURES
    ):
        return None
    detections = ddb.query_detections(asset_id=asset_id)
    segment_job = jobs.get(Feature.SEGMENT.value) or {}
    duration, rating = _load_asset_qc_context(asset_id)
    findings = evaluate(
        detections,
        media_meta={
            "video": segment_job.get("video_metadata"),
            "audio": segment_job.get("audio_metadata"),
        },
        title_rating=rating,
        asset_duration_seconds=duration,
    )
    items = _findings_to_items(asset_id, findings)
    ddb.replace_feature_detections(
        asset_id=asset_id, feature=Feature.FINDING, items=items
    )
    return len(items)


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
            except Exception:  # noqa: BLE001 - one bad message shouldn't stop the drain
                result.failed += 1
                logger.exception("process_completion raised; leaving message for retry/DLQ")
                # Don't echo raw exception text to the caller/CI logs; full detail is logged.
                result.messages.append("error processing a message (see server logs)")
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
