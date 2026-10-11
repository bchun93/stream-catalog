"""Assemble the picture-QC report from DynamoDB jobs and FINDING rows."""

from __future__ import annotations

from app.services.rekognition import ddb
from app.services.rekognition.constants import EVALUATION_FEATURES, Feature, JobStatus
from app.schemas.rekognition import DetectionRead, PictureQcReport, PictureQcSummary

_SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


def _job_status(jobs: dict[str, ddb.JobItem], feature: Feature) -> str | None:
    row = jobs.get(feature.value)
    if not row:
        return None
    return row.get("status")


def build_report(asset_id: int | str) -> PictureQcReport:
    key = str(asset_id)
    jobs = {job.get("feature", ""): job for job in ddb.list_jobs_for_asset(key)}
    pending = [
        feature.value
        for feature in EVALUATION_FEATURES
        if _job_status(jobs, feature) != JobStatus.SUCCEEDED.value
    ]
    segment = jobs.get(Feature.SEGMENT.value) or {}
    findings = ddb.query_detections(asset_id=key, feature=Feature.FINDING)
    error = sum(1 for row in findings if row.get("severity") == "error")
    warning = sum(1 for row in findings if row.get("severity") == "warning")
    info = sum(1 for row in findings if row.get("severity") == "info")
    ready = not pending
    if not ready:
        outcome = "pending"
    elif error:
        outcome = "error"
    elif warning:
        outcome = "warning"
    else:
        outcome = "pass"
    findings_sorted = sorted(
        findings,
        key=lambda row: (
            _SEV_ORDER.get(str(row.get("severity") or ""), 9),
            row.get("start_ms") or 0,
            row.get("rule_id") or "",
        ),
    )
    try:
        numeric_id = int(asset_id)
    except (TypeError, ValueError):
        numeric_id = 0
    return PictureQcReport(
        asset_id=numeric_id,
        ready=ready,
        pending_features=pending,
        summary=PictureQcSummary(
            error=error, warning=warning, info=info, outcome=outcome
        ),
        video_metadata=segment.get("video_metadata"),
        audio_metadata=segment.get("audio_metadata"),
        findings=[DetectionRead(**row) for row in findings_sorted],
    )
