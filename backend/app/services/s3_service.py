import logging
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class S3ObjectRow:
    key: str
    name: str
    size_bytes: int | None
    last_modified: datetime | None


@dataclass
class S3FolderRow:
    name: str
    prefix: str


@dataclass
class S3BrowseResult:
    bucket: str
    root_prefix: str
    prefix: str
    folders: list[S3FolderRow]
    objects: list[S3ObjectRow]
    truncated: bool


@dataclass
class S3PresignUpload:
    key: str
    storage_uri: str
    upload_url: str
    method: str
    headers: dict[str, str]


def required_bucket() -> str:
    bucket = (settings.ingest_s3_bucket or "").strip()
    if not bucket:
        raise ValueError("INGEST_S3_BUCKET is not configured.")
    return bucket


def settings_root_prefix() -> str:
    parts: list[str] = []
    for value in (settings.ingest_s3_prefix, settings.aspera_drop_prefix):
        v = (value or "").strip().strip("/")
        if v:
            parts.append(v)
    return "/".join(parts)


def joined_prefix(relative_prefix: str) -> str:
    parts: list[str] = []
    for value in (settings.ingest_s3_prefix, settings.aspera_drop_prefix, relative_prefix):
        v = (value or "").strip().strip("/")
        if v:
            parts.append(v)
    joined = "/".join(parts)
    return f"{joined}/" if joined else ""


def relative_prefix_from_key(key: str) -> str:
    root = settings_root_prefix()
    normalized = key.strip().strip("/")
    if not root:
        return normalized
    if normalized == root:
        return ""
    if normalized.startswith(f"{root}/"):
        return normalized[len(root) + 1 :]
    return normalized


def storage_uri(key: str) -> str:
    return f"s3://{required_bucket()}/{key.lstrip('/')}"


def sanitize_filename(filename: str) -> str:
    base = os.path.basename((filename or "upload").strip()) or "upload"
    cleaned = _FILENAME_SAFE.sub("_", base).strip("._")
    return cleaned or "upload"


def s3_client():
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError("boto3 is required for S3 integration.") from exc

    session_kwargs: dict[str, str] = {"region_name": settings.aws_region}
    if settings.aws_profile:
        session_kwargs["profile_name"] = settings.aws_profile
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    client_kwargs: dict[str, str] = {}
    if settings.aws_endpoint_url:
        client_kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.Session(**session_kwargs).client("s3", **client_kwargs)


def list_all_objects(relative_prefix: str, *, max_keys: int) -> list[S3ObjectRow]:
    bucket = required_bucket()
    key_prefix = joined_prefix(relative_prefix)
    client = s3_client()

    listed: list[S3ObjectRow] = []
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
            listed.append(
                S3ObjectRow(
                    key=key,
                    name=os.path.basename(key),
                    size_bytes=obj.get("Size"),
                    last_modified=obj.get("LastModified"),
                )
            )
            if len(listed) >= max_keys:
                break
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
        if not token:
            break
    return listed


def browse_objects(
    relative_prefix: str = "",
    *,
    max_keys: int = 500,
) -> S3BrowseResult:
    bucket = required_bucket()
    full_prefix = joined_prefix(relative_prefix)
    if full_prefix and not full_prefix.endswith("/"):
        full_prefix += "/"

    client = s3_client()
    resp = client.list_objects_v2(
        Bucket=bucket,
        Prefix=full_prefix,
        Delimiter="/",
        MaxKeys=max_keys,
    )

    folders: list[S3FolderRow] = []
    for entry in resp.get("CommonPrefixes", []):
        folder_key = entry.get("Prefix")
        if not isinstance(folder_key, str):
            continue
        name = folder_key.rstrip("/").split("/")[-1]
        folders.append(
            S3FolderRow(
                name=name,
                prefix=relative_prefix_from_key(folder_key.rstrip("/")),
            )
        )

    objects: list[S3ObjectRow] = []
    for obj in resp.get("Contents", []):
        key = obj.get("Key")
        if not isinstance(key, str) or key == full_prefix or key.endswith("/"):
            continue
        objects.append(
            S3ObjectRow(
                key=key,
                name=os.path.basename(key),
                size_bytes=obj.get("Size"),
                last_modified=obj.get("LastModified"),
            )
        )

    return S3BrowseResult(
        bucket=bucket,
        root_prefix=settings_root_prefix(),
        prefix=(relative_prefix or "").strip().strip("/"),
        folders=sorted(folders, key=lambda row: row.name.lower()),
        objects=sorted(objects, key=lambda row: row.name.lower()),
        truncated=bool(resp.get("IsTruncated")),
    )


def get_object_bytes(key: str) -> bytes:
    client = s3_client()
    resp = client.get_object(Bucket=required_bucket(), Key=key)
    body = resp["Body"].read()
    return body if isinstance(body, bytes) else bytes(body)


def presign_upload(
    *,
    relative_prefix: str,
    filename: str,
    content_type: str | None = None,
    expires_in: int = 3600,
) -> S3PresignUpload:
    safe_name = sanitize_filename(filename)
    base_prefix = joined_prefix(relative_prefix)
    key = f"{base_prefix}{safe_name}" if base_prefix else safe_name
    mime = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    client = s3_client()
    upload_url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": required_bucket(),
            "Key": key,
            "ContentType": mime,
        },
        ExpiresIn=expires_in,
        HttpMethod="PUT",
    )
    return S3PresignUpload(
        key=key,
        storage_uri=storage_uri(key),
        upload_url=upload_url,
        method="PUT",
        headers={"Content-Type": mime},
    )


def presign_download(key: str, *, expires_in: int = 3600) -> str:
    client = s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": required_bucket(), "Key": key},
        ExpiresIn=expires_in,
        HttpMethod="GET",
    )
