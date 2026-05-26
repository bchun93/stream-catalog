import fnmatch
import json
import logging
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.ingest_job import IngestItem, IngestItemStatus, IngestJob, IngestJobStatus
from app.models.ingest_manifest import IngestManifest
from app.models.media_asset import AssetStatus, MediaAsset
from app.schemas.ingest import (
    IngestItemPreview,
    IngestJobCreateRequest,
    IngestManifestRule,
    IngestManifestValidateRequest,
    IngestManifestValidateResponse,
)
from app.services.mediainfo_service import infer_resolution_from_name, summarize_media_info

logger = logging.getLogger(__name__)


@dataclass
class _S3Object:
    key: str
    size: int | None


@dataclass
class _MatchedObject:
    obj: _S3Object
    rule: IngestManifestRule
    matched_rule: str
    language: str | None
    resolution: str | None
    media_info: dict[str, Any] | None
    media_info_json: str | None
    warnings: list[str]


def list_manifests(db: Session, *, enabled_only: bool = False) -> list[IngestManifest]:
    query = db.query(IngestManifest).order_by(IngestManifest.name.asc(), IngestManifest.version.desc())
    if enabled_only:
        query = query.filter(IngestManifest.enabled.is_(True))
    return query.all()


def get_manifest(db: Session, manifest_id: int) -> IngestManifest | None:
    return db.query(IngestManifest).filter(IngestManifest.id == manifest_id).first()


def list_jobs(db: Session, *, title_id: int | None = None, limit: int = 50) -> list[IngestJob]:
    query = (
        db.query(IngestJob)
        .options(joinedload(IngestJob.items))
        .order_by(IngestJob.created_at.desc())
        .limit(limit)
    )
    if title_id is not None:
        query = query.filter(IngestJob.title_id == title_id)
    return query.all()


def get_job(db: Session, job_id: int) -> IngestJob | None:
    return (
        db.query(IngestJob)
        .options(joinedload(IngestJob.items))
        .filter(IngestJob.id == job_id)
        .first()
    )


def validate_manifest(
    db: Session, payload: IngestManifestValidateRequest
) -> IngestManifestValidateResponse:
    manifest = _require_manifest(db, payload.manifest_id)
    max_keys = payload.max_keys or settings.ingest_max_keys
    objs = _list_s3_objects(payload.source_prefix, max_keys=max_keys)
    sidecars = _build_sidecar_index(objs)

    previews: list[IngestItemPreview] = []
    matched_count = 0
    skipped_count = 0
    for obj in objs:
        if obj.key.endswith(".mediainfo.json"):
            continue
        matched = _match_object(manifest, obj, sidecars)
        if matched is None:
            skipped_count += 1
            previews.append(
                IngestItemPreview(
                    s3_key=obj.key,
                    filename=os.path.basename(obj.key),
                    warnings=["No manifest rule matched this file."],
                )
            )
            continue
        matched_count += 1
        previews.append(
            IngestItemPreview(
                s3_key=obj.key,
                filename=os.path.basename(obj.key),
                inferred_asset_type=matched.rule.asset_type,
                language=matched.language,
                resolution=matched.resolution,
                matched_rule=matched.matched_rule,
                media_info=matched.media_info,
                warnings=matched.warnings,
            )
        )

    return IngestManifestValidateResponse(
        manifest_id=manifest.id,
        source_prefix=payload.source_prefix,
        discovered_count=len([o for o in objs if not o.key.endswith(".mediainfo.json")]),
        matched_count=matched_count,
        skipped_count=skipped_count,
        items=previews,
    )


def create_job(db: Session, payload: IngestJobCreateRequest, *, request_id: str | None = None) -> IngestJob:
    manifest = _require_manifest(db, payload.manifest_id)
    max_keys = payload.max_keys or settings.ingest_max_keys
    objs = _list_s3_objects(payload.source_prefix, max_keys=max_keys)
    sidecars = _build_sidecar_index(objs)

    job = IngestJob(
        title_id=payload.title_id,
        manifest_id=manifest.id,
        source_prefix=payload.source_prefix,
        status=IngestJobStatus.RUNNING,
        dry_run=payload.dry_run,
        created_by=payload.created_by,
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()

    logger.info(
        "ingest job started",
        extra={
            "job_id": job.id,
            "title_id": payload.title_id,
            "manifest_id": payload.manifest_id,
            "source_prefix": payload.source_prefix,
            "request_id": request_id,
            "dry_run": payload.dry_run,
        },
    )

    candidates = [o for o in objs if not o.key.endswith(".mediainfo.json")]
    job.discovered_count = len(candidates)
    existing_by_uri = {
        asset.storage_uri: asset
        for asset in db.query(MediaAsset).filter(MediaAsset.title_id == payload.title_id).all()
    }

    for obj in candidates:
        matched = _match_object(manifest, obj, sidecars)
        if matched is None:
            job.skipped_count += 1
            db.add(
                IngestItem(
                    job_id=job.id,
                    s3_key=obj.key,
                    filename=os.path.basename(obj.key),
                    status=IngestItemStatus.SKIPPED,
                    error_message="No manifest rule matched this file.",
                )
            )
            continue

        storage_uri = f"s3://{_required_bucket()}/{obj.key}"
        existing = existing_by_uri.get(storage_uri)
        if existing:
            job.skipped_count += 1
            db.add(
                IngestItem(
                    job_id=job.id,
                    s3_key=obj.key,
                    filename=os.path.basename(obj.key),
                    inferred_asset_type=matched.rule.asset_type,
                    status=IngestItemStatus.SKIPPED,
                    resulting_asset_id=existing.id,
                    media_info_json=matched.media_info_json,
                    error_message="Asset already exists for this title and URI.",
                )
            )
            continue

        if payload.dry_run:
            job.ingested_count += 1
            db.add(
                IngestItem(
                    job_id=job.id,
                    s3_key=obj.key,
                    filename=os.path.basename(obj.key),
                    inferred_asset_type=matched.rule.asset_type,
                    status=IngestItemStatus.DISCOVERED,
                    media_info_json=matched.media_info_json,
                )
            )
            continue

        try:
            asset = MediaAsset(
                title_id=payload.title_id,
                asset_type=matched.rule.asset_type,
                status=_coerce_asset_status(matched.rule.status),
                filename=os.path.basename(obj.key),
                mime_type=matched.rule.mime_type or mimetypes.guess_type(obj.key)[0] or "application/octet-stream",
                storage_uri=storage_uri,
                size_bytes=obj.size,
                language=matched.language,
                resolution=matched.resolution,
                duration_seconds=_media_info_duration(matched.media_info),
                codec=_media_info_codec(matched.media_info),
                notes=matched.rule.notes,
                metadata_json=_asset_metadata_json(
                    manifest=manifest,
                    s3_key=obj.key,
                    matched_rule=matched.matched_rule,
                    media_info=matched.media_info,
                    warnings=matched.warnings,
                ),
            )
            db.add(asset)
            db.flush()
            existing_by_uri[storage_uri] = asset
            job.ingested_count += 1
            db.add(
                IngestItem(
                    job_id=job.id,
                    s3_key=obj.key,
                    filename=os.path.basename(obj.key),
                    inferred_asset_type=matched.rule.asset_type,
                    status=IngestItemStatus.INGESTED,
                    media_info_json=matched.media_info_json,
                    resulting_asset_id=asset.id,
                )
            )
        except Exception as exc:
            job.failed_count += 1
            db.add(
                IngestItem(
                    job_id=job.id,
                    s3_key=obj.key,
                    filename=os.path.basename(obj.key),
                    inferred_asset_type=matched.rule.asset_type,
                    status=IngestItemStatus.FAILED,
                    media_info_json=matched.media_info_json,
                    error_message=str(exc)[:500],
                )
            )

    job.status = IngestJobStatus.FAILED if job.failed_count else IngestJobStatus.COMPLETED
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    logger.info(
        "ingest job finished",
        extra={
            "job_id": job.id,
            "status": job.status.value,
            "discovered": job.discovered_count,
            "ingested": job.ingested_count,
            "skipped": job.skipped_count,
            "failed": job.failed_count,
            "request_id": request_id,
        },
    )
    return get_job(db, job.id) or job


def _coerce_asset_status(value: str) -> AssetStatus:
    try:
        return AssetStatus(value)
    except Exception:
        return AssetStatus.UPLOADED


def _match_object(
    manifest: IngestManifest, obj: _S3Object, sidecars: dict[str, _S3Object]
) -> _MatchedObject | None:
    filename = os.path.basename(obj.key)
    for raw_rule in manifest.rules:
        try:
            rule = IngestManifestRule.model_validate(raw_rule)
        except Exception:
            continue
        if not _rule_matches(rule, key=obj.key, filename=filename):
            continue

        warnings: list[str] = []
        media_info = _load_media_info_for_object(obj, sidecars, warnings)
        summary = summarize_media_info(media_info)
        resolution = rule.resolution or summary.resolution or infer_resolution_from_name(filename)
        return _MatchedObject(
            obj=obj,
            rule=rule,
            matched_rule=rule.name or rule.pattern,
            language=rule.language,
            resolution=resolution,
            media_info=media_info,
            media_info_json=summary.raw_json,
            warnings=warnings,
        )
    return None


def _rule_matches(rule: IngestManifestRule, *, key: str, filename: str) -> bool:
    if rule.use_regex:
        return bool(re.search(rule.pattern, key) or re.search(rule.pattern, filename))
    patterns = _expand_brace_glob(rule.pattern)
    return any(fnmatch.fnmatch(filename, p) or fnmatch.fnmatch(key, p) for p in patterns)


def _expand_brace_glob(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]+)\}", pattern)
    if not match:
        return [pattern]
    variants = []
    for value in match.group(1).split(","):
        variants.append(pattern[: match.start()] + value.strip() + pattern[match.end() :])
    return variants or [pattern]


def _build_sidecar_index(objs: list[_S3Object]) -> dict[str, _S3Object]:
    sidecars: dict[str, _S3Object] = {}
    for obj in objs:
        if obj.key.endswith(".mediainfo.json"):
            sidecars[obj.key[: -len(".mediainfo.json")]] = obj
    return sidecars


def _load_media_info_for_object(
    obj: _S3Object, sidecars: dict[str, _S3Object], warnings: list[str]
) -> dict[str, Any] | None:
    sidecar = sidecars.get(obj.key)
    if not sidecar:
        return None
    try:
        body = _get_s3_object_bytes(sidecar.key)
        return json.loads(body.decode("utf-8"))
    except Exception as exc:
        warnings.append(f"Failed to parse MediaInfo sidecar: {exc}")
        return None


def _media_info_duration(media_info: dict[str, Any] | None) -> int | None:
    return summarize_media_info(media_info).duration_seconds


def _media_info_codec(media_info: dict[str, Any] | None) -> str | None:
    return summarize_media_info(media_info).codec


def _asset_metadata_json(
    *,
    manifest: IngestManifest,
    s3_key: str,
    matched_rule: str,
    media_info: dict[str, Any] | None,
    warnings: list[str],
) -> str:
    payload: dict[str, Any] = {
        "ingest": {
            "manifest_name": manifest.name,
            "manifest_version": manifest.version,
            "s3_key": s3_key,
            "matched_rule": matched_rule,
            "warnings": warnings,
        }
    }
    if media_info is not None:
        payload["media_info"] = media_info
    return json.dumps(payload, separators=(",", ":"))


def _list_s3_objects(source_prefix: str, *, max_keys: int) -> list[_S3Object]:
    bucket = _required_bucket()
    key_prefix = _joined_prefix(source_prefix)
    client = _s3_client()

    listed: list[_S3Object] = []
    token: str | None = None
    while len(listed) < max_keys:
        kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Prefix": key_prefix,
            "MaxKeys": min(1000, max_keys - len(listed)),
        }
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            key = obj.get("Key")
            if not isinstance(key, str):
                continue
            listed.append(_S3Object(key=key, size=obj.get("Size")))
            if len(listed) >= max_keys:
                break
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
        if not token:
            break
    return listed


def _get_s3_object_bytes(key: str) -> bytes:
    client = _s3_client()
    resp = client.get_object(Bucket=_required_bucket(), Key=key)
    body = resp["Body"].read()
    return body if isinstance(body, bytes) else bytes(body)


def _required_bucket() -> str:
    bucket = (settings.ingest_s3_bucket or "").strip()
    if not bucket:
        raise ValueError("INGEST_S3_BUCKET is not configured.")
    return bucket


def _joined_prefix(source_prefix: str) -> str:
    parts = []
    for value in (settings.ingest_s3_prefix, settings.aspera_drop_prefix, source_prefix):
        v = (value or "").strip().strip("/")
        if v:
            parts.append(v)
    joined = "/".join(parts)
    return f"{joined}/" if joined else ""


def _require_manifest(db: Session, manifest_id: int) -> IngestManifest:
    manifest = get_manifest(db, manifest_id)
    if not manifest:
        raise ValueError("Ingest manifest not found.")
    if not manifest.enabled:
        raise ValueError("Selected ingest manifest is disabled.")
    return manifest


def _s3_client():
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError("boto3 is required for S3 ingest integration.") from exc
    return boto3.client("s3")
