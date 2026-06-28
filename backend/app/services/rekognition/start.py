"""Start Rekognition Video analysis jobs for an asset's H.264 MP4 proxy.

Guardrails (cost/correctness):
  - Analyze the proxy in place from its S3 bucket; refuse non-S3 / non-MP4-MOV input,
    and refuse a *known* non-H.264 codec (warn when codec is unknown).
  - One job per feature == one billable per-minute charge. We skip starting a feature that
    is already IN_PROGRESS or SUCCEEDED (checked before the Start* call) so a re-click never
    re-charges, and pass ClientRequestToken for AWS-side idempotency as a second layer.
  - Status comes only from SNS->SQS later; we never poll Get* here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from botocore.exceptions import ClientError

from app.config import settings
from app.models.media_asset import MediaAsset
from app.services.aws_clients import rekognition_client
from app.services.rekognition import ddb
from app.services.rekognition.constants import (
    ALLOWED_VIDEO_EXTENSIONS,
    H264_CODEC_HINTS,
    LABEL_MIN_CONFIDENCE,
    MODERATION_MIN_CONFIDENCE,
    SEGMENT_SHOT_MIN_CONFIDENCE,
    SEGMENT_TECHNICAL_CUE_MIN_CONFIDENCE,
    Feature,
    JobStatus,
)

if TYPE_CHECKING:
    from mypy_boto3_rekognition.client import RekognitionClient

logger = logging.getLogger(__name__)


class AnalysisInputError(ValueError):
    """Bad input (no S3 proxy, wrong container/codec) -> HTTP 400."""


class AnalysisConfigError(RuntimeError):
    """Missing AWS configuration -> HTTP 503."""


@dataclass
class FeatureResult:
    feature: Feature
    status: str
    aws_job_id: str | None = None
    started: bool = False
    message: str | None = None


@dataclass
class AnalysisResult:
    asset_id: int
    bucket: str
    key: str
    results: list[FeatureResult]
    warnings: list[str] = field(default_factory=list)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise AnalysisInputError(
            "Asset has no S3 proxy. Rekognition can only analyze an s3:// MP4/MOV proxy, "
            "not a non-S3 storage URI or a master in another store."
        )
    return parsed.netloc, parsed.path.lstrip("/")


def _resolve_proxy(asset: MediaAsset, s3_key_override: str | None) -> tuple[str, str]:
    analysis_bucket = (settings.s3_analysis_bucket or "").strip()
    if s3_key_override:
        if not analysis_bucket:
            raise AnalysisConfigError(
                "S3_ANALYSIS_BUCKET is not configured; cannot resolve an overridden S3 key."
            )
        return analysis_bucket, s3_key_override.lstrip("/")

    bucket, key = _parse_s3_uri(asset.storage_uri or "")
    # Defense-in-depth: even the default path must stay within the analysis bucket, so an
    # attacker-set storage_uri can't make Rekognition read an arbitrary bucket.
    if analysis_bucket and bucket != analysis_bucket:
        raise AnalysisInputError(
            f"Asset proxy is in bucket '{bucket}', not the configured analysis bucket "
            f"'{analysis_bucket}'. Only objects in the analysis bucket can be analyzed."
        )
    return bucket, key


def _guard_video(asset: MediaAsset, key: str, *, is_override: bool) -> list[str]:
    warnings: list[str] = []
    ext = os.path.splitext(key)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise AnalysisInputError(
            f"Rekognition Video requires an H.264 MP4/MOV proxy; '{key}' has extension "
            f"'{ext or '(none)'}'. Analyze the proxy, not the master."
        )
    codec = (asset.codec or "").strip().lower()
    if is_override:
        # We don't know the codec of an arbitrary picked object.
        warnings.append(
            "Codec of the selected S3 object is unknown; assuming H.264. "
            "Rekognition will reject the job if the input is not H.264."
        )
    elif codec:
        if not any(hint in codec for hint in H264_CODEC_HINTS):
            raise AnalysisInputError(
                f"Asset codec '{asset.codec}' is not H.264. Rekognition Video only accepts "
                "H.264 MP4/MOV. Analyze the H.264 proxy instead."
            )
    else:
        warnings.append(
            "Asset codec is unknown; assuming H.264. Rekognition will reject the job if the "
            "input is not H.264."
        )
    return warnings


def _client_request_token(asset_id: str, feature: Feature, attempt: int = 1) -> str:
    # AWS ClientRequestToken charset is [a-zA-Z0-9-_] (no ':'), so use '_' as the separator.
    # attempt 1 keeps the stable token (double-click dedupe); a FAILED re-run bumps attempt so
    # AWS starts a genuinely new job instead of returning the old failed JobId within its
    # 7-day idempotency window.
    base = f"{asset_id}_{feature.value}"
    return base if attempt <= 1 else f"{base}_{attempt}"


def _job_tag(asset_id: str, feature: Feature) -> str:
    # JobTag allows ':' and makes the completion message self-identifying.
    return f"{asset_id}:{feature.value}"


def _start_feature(
    rek: "RekognitionClient",
    feature: Feature,
    *,
    bucket: str,
    key: str,
    asset_id: str,
    token: str,
) -> str:
    video = {"S3Object": {"Bucket": bucket, "Name": key}}
    notification = {
        "SNSTopicArn": settings.rekognition_sns_topic_arn or "",
        "RoleArn": settings.rekognition_role_arn or "",
    }
    common = {
        "Video": video,
        "NotificationChannel": notification,
        "ClientRequestToken": token,
        "JobTag": _job_tag(asset_id, feature),
    }
    if feature is Feature.SEGMENT:
        resp = rek.start_segment_detection(
            SegmentTypes=["TECHNICAL_CUE", "SHOT"],
            Filters={
                "TechnicalCueFilter": {
                    "MinSegmentConfidence": SEGMENT_TECHNICAL_CUE_MIN_CONFIDENCE
                },
                "ShotFilter": {"MinSegmentConfidence": SEGMENT_SHOT_MIN_CONFIDENCE},
            },
            **common,  # type: ignore[arg-type]
        )
    elif feature is Feature.MODERATION:
        resp = rek.start_content_moderation(
            MinConfidence=MODERATION_MIN_CONFIDENCE,
            **common,  # type: ignore[arg-type]
        )
    else:  # Feature.LABELS
        resp = rek.start_label_detection(
            MinConfidence=LABEL_MIN_CONFIDENCE,
            Features=["GENERAL_LABELS"],
            **common,  # type: ignore[arg-type]
        )
    job_id = resp["JobId"]
    logger.info(
        "rekognition Start* dispatched",
        extra={"asset_id": asset_id, "feature": feature.value, "aws_job_id": job_id},
    )
    return job_id


def _explain_client_error(exc: ClientError) -> str:
    code = exc.response.get("Error", {}).get("Code", "")
    if code == "LimitExceededException":
        return (
            "Too many Rekognition jobs are running concurrently (LimitExceededException). "
            "Retry shortly — this feature was not started."
        )
    if code in ("AccessDeniedException", "AccessDenied"):
        return (
            "Access denied. Verify the app IAM credentials, the Rekognition service role, "
            "and that iam:PassRole allows passing the role to rekognition.amazonaws.com."
        )
    if code in ("InvalidS3ObjectException", "InvalidS3Object"):
        return (
            "Rekognition could not read the S3 object (missing, wrong region, or the service "
            "role lacks s3:GetObject on the bucket)."
        )
    return f"{code or 'Rekognition error'}: {exc.response.get('Error', {}).get('Message', str(exc))}"


def start_analysis(
    asset: MediaAsset,
    *,
    s3_key_override: str | None = None,
) -> AnalysisResult:
    if not settings.rekognition_configured:
        raise AnalysisConfigError(
            "Rekognition is not configured. Set REKOGNITION_ROLE_ARN and "
            "REKOGNITION_SNS_TOPIC_ARN (see docs/REKOGNITION_AWS_SETUP.md)."
        )

    bucket, key = _resolve_proxy(asset, s3_key_override)
    warnings = _guard_video(asset, key, is_override=bool(s3_key_override))

    rek = rekognition_client()
    asset_id = str(asset.id)
    results: list[FeatureResult] = []

    for feature in Feature:
        existing = ddb.get_job(asset_id=asset_id, feature=feature)
        if existing and existing.get("status") in (
            JobStatus.IN_PROGRESS.value,
            JobStatus.SUCCEEDED.value,
        ):
            results.append(
                FeatureResult(
                    feature=feature,
                    status=existing["status"],
                    aws_job_id=existing.get("aws_job_id"),
                    started=False,
                    message=f"Already {existing['status'].lower()}; skipped to avoid re-charge.",
                )
            )
            continue

        attempt = int(existing.get("attempt", 0)) + 1 if existing else 1
        token = _client_request_token(asset_id, feature, attempt)
        try:
            job_id = _start_feature(
                rek, feature, bucket=bucket, key=key, asset_id=asset_id, token=token
            )
        except ClientError as exc:
            message = _explain_client_error(exc)
            logger.warning(
                "rekognition Start* failed",
                extra={"asset_id": asset_id, "feature": feature.value, "error": message},
            )
            results.append(
                FeatureResult(
                    feature=feature, status="ERROR", started=False, message=message
                )
            )
            continue

        try:
            ddb.put_job(
                asset_id=asset_id,
                feature=feature,
                aws_job_id=job_id,
                client_request_token=token,
                attempt=attempt,
            )
            results.append(
                FeatureResult(
                    feature=feature,
                    status=JobStatus.IN_PROGRESS.value,
                    aws_job_id=job_id,
                    started=True,
                )
            )
        except ddb.JobConflictError as conflict:
            existing = conflict.existing or {}
            results.append(
                FeatureResult(
                    feature=feature,
                    status=existing.get("status", JobStatus.IN_PROGRESS.value),
                    aws_job_id=existing.get("aws_job_id", job_id),
                    started=False,
                    message="A job for this feature already exists; skipped.",
                )
            )

    return AnalysisResult(
        asset_id=asset.id, bucket=bucket, key=key, results=results, warnings=warnings
    )
