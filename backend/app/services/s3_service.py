import logging
import mimetypes
import os
import re
import hmac
import sys
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class StaleObjectError(RuntimeError):
    """The object changed after it was listed in the browser."""


@dataclass
class S3ObjectRow:
    key: str
    name: str
    size_bytes: int | None
    last_modified: datetime | None
    etag: str | None


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


def validated_managed_object_key(key: str) -> str:
    if not key or key != key.strip() or key.startswith("/") or key.endswith("/"):
        raise ValueError("A file object key is required.")
    if any(part in {"", ".", ".."} for part in key.split("/")):
        raise ValueError("Object key contains an invalid path segment.")
    root = settings_root_prefix()
    if not root:
        raise RuntimeError("S3 object mutations require a configured ingest root prefix.")
    if not key.startswith(f"{root}/"):
        raise ValueError("Object key is outside the configured ingest root.")
    return key


def validated_object_name(name: str) -> str:
    value = (name or "").strip()
    if not value or value in {".", ".."}:
        raise ValueError("A valid object name is required.")
    if "/" in value or "\\" in value or any(ord(char) < 32 for char in value):
        raise ValueError("Object name cannot contain slashes or control characters.")
    return value


def _head_object(client: Any, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def sanitize_filename(filename: str) -> str:
    base = os.path.basename((filename or "upload").strip()) or "upload"
    cleaned = _FILENAME_SAFE.sub("_", base).strip("._")
    return cleaned or "upload"


def _refresh_darwin_resolver() -> None:
    """macOS libc can fail getaddrinfo in long-lived processes after sleep/VPN/Wi-Fi."""
    if sys.platform != "darwin":
        return
    try:
        import ctypes

        lib = ctypes.CDLL("libresolv.dylib")
        init = getattr(lib, "res_9_init", None) or getattr(lib, "res_init", None)
        if init is not None:
            init()
    except Exception:
        logger.debug("Skipped macOS DNS resolver refresh", exc_info=True)


def s3_client():
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError("boto3 is required for S3 integration.") from exc

    _refresh_darwin_resolver()

    access_key = (settings.aws_access_key_id or "").strip() or None
    secret_key = (settings.aws_secret_access_key or "").strip() or None
    profile = (settings.aws_profile or "").strip() or None

    session_kwargs: dict[str, str] = {"region_name": settings.aws_region}
    if profile:
        session_kwargs["profile_name"] = profile
    if access_key and secret_key:
        session_kwargs["aws_access_key_id"] = access_key
        session_kwargs["aws_secret_access_key"] = secret_key
    # Otherwise fall through to boto3's default chain (env, ~/.aws/credentials,
    # instance/task role) — same resolution order as aws_clients._session().
    client_kwargs: dict[str, str] = {}
    if settings.aws_endpoint_url:
        client_kwargs["endpoint_url"] = settings.aws_endpoint_url
    session = boto3.Session(**session_kwargs)
    if session.get_credentials() is None:
        raise RuntimeError(
            "AWS credentials are not configured for S3. On Render, set "
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the service Environment. "
            "Locally, set those in backend/.env, set AWS_PROFILE, or use the default "
            "AWS credential chain / instance role."
        )
    return session.client("s3", **client_kwargs)


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
                    etag=obj.get("ETag"),
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
                etag=obj.get("ETag"),
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


def put_bytes(
    *,
    relative_prefix: str,
    filename: str,
    body: bytes,
    content_type: str = "application/octet-stream",
) -> tuple[str, str]:
    """Upload bytes to the ingest bucket. Returns (key, storage_uri)."""
    safe_name = sanitize_filename(filename)
    base_prefix = joined_prefix(relative_prefix)
    key = f"{base_prefix}{safe_name}" if base_prefix else safe_name
    client = s3_client()
    client.put_object(
        Bucket=required_bucket(),
        Key=key,
        Body=body,
        ContentType=content_type,
    )
    return key, storage_uri(key)


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
    managed_key = validated_managed_object_key(key)
    client = s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": required_bucket(), "Key": managed_key},
        ExpiresIn=expires_in,
        HttpMethod="GET",
    )


_COPY_PART_SIZE = 512 * 1024 * 1024


def _delete_if_unchanged(client: Any, bucket: str, key: str, expected_etag: str) -> None:
    try:
        client.delete_object(Bucket=bucket, Key=key, IfMatch=expected_etag)
    except Exception as exc:
        try:
            source_after_error = _head_object(client, bucket, key)
        except Exception:
            raise exc
        if source_after_error is None:
            return
        current_etag = str(source_after_error.get("ETag", ""))
        code = (
            str(exc.response.get("Error", {}).get("Code", ""))
            if isinstance(exc, ClientError)
            else ""
        )
        if current_etag != expected_etag or code in {"412", "PreconditionFailed"}:
            raise StaleObjectError(
                "The S3 object changed. Refresh the browser and try again."
            ) from exc
        raise


def _rename_signature(
    *,
    bucket: str,
    source_key: str,
    destination_key: str,
    source_etag: str,
    source_size: int,
) -> str:
    secret = (settings.s3_mutation_secret or "").strip()
    if len(secret) < 32:
        raise RuntimeError(
            "S3_MUTATION_SECRET must be configured with at least 32 characters "
            "before rename operations are enabled."
        )
    message = "\0".join(
        (bucket, source_key, destination_key, source_etag, str(source_size))
    ).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, sha256).hexdigest()


def _multipart_copy_without_overwrite(
    client: Any,
    *,
    bucket: str,
    source_key: str,
    destination_key: str,
    source_etag: str,
    source_head: dict[str, Any],
    rename_metadata: dict[str, str],
) -> str:
    create_kwargs: dict[str, Any] = {
        "Bucket": bucket,
        "Key": destination_key,
        "Metadata": {**source_head.get("Metadata", {}), **rename_metadata},
    }
    for source_field, destination_field in (
        ("CacheControl", "CacheControl"),
        ("ContentDisposition", "ContentDisposition"),
        ("ContentEncoding", "ContentEncoding"),
        ("ContentLanguage", "ContentLanguage"),
        ("ContentType", "ContentType"),
        ("Expires", "Expires"),
        ("ServerSideEncryption", "ServerSideEncryption"),
        ("SSEKMSKeyId", "SSEKMSKeyId"),
        ("BucketKeyEnabled", "BucketKeyEnabled"),
        ("StorageClass", "StorageClass"),
    ):
        value = source_head.get(source_field)
        if value is not None:
            create_kwargs[destination_field] = value

    size = int(source_head.get("ContentLength", 0))
    if size == 0:
        try:
            response = client.put_object(
                **create_kwargs,
                Body=b"",
                IfNoneMatch="*",
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"409", "412", "ConditionalRequestConflict", "PreconditionFailed"}:
                raise FileExistsError("An S3 object with that name already exists.") from exc
            raise
        return str(response.get("ETag", ""))

    upload = client.create_multipart_upload(**create_kwargs)
    upload_id = upload["UploadId"]
    completed_parts: list[dict[str, Any]] = []
    try:
        part_number = 1
        for start in range(0, size, _COPY_PART_SIZE):
            end = min(start + _COPY_PART_SIZE, size) - 1
            try:
                response = client.upload_part_copy(
                    Bucket=bucket,
                    Key=destination_key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    CopySource={"Bucket": bucket, "Key": source_key},
                    CopySourceIfMatch=source_etag,
                    CopySourceRange=f"bytes={start}-{end}",
                )
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code in {"412", "PreconditionFailed"}:
                    raise StaleObjectError(
                        "The S3 object changed. Refresh the browser and try again."
                    ) from exc
                raise
            completed_parts.append(
                {
                    "ETag": response["CopyPartResult"]["ETag"],
                    "PartNumber": part_number,
                }
            )
            part_number += 1
        try:
            completed = client.complete_multipart_upload(
                Bucket=bucket,
                Key=destination_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": completed_parts},
                IfNoneMatch="*",
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"409", "412", "ConditionalRequestConflict", "PreconditionFailed"}:
                raise FileExistsError("An S3 object with that name already exists.") from exc
            raise
        return str(completed.get("ETag", ""))
    except Exception:
        try:
            client.abort_multipart_upload(
                Bucket=bucket,
                Key=destination_key,
                UploadId=upload_id,
            )
        except Exception:
            logger.exception("Failed to abort multipart rename for key %s", destination_key)
        raise


def rename_object(
    key: str,
    new_name: str,
    expected_etag: str,
    expected_size: int,
) -> tuple[str, str]:
    source_key = validated_managed_object_key(key)
    destination_name = validated_object_name(new_name)
    if not expected_etag:
        raise ValueError("The source ETag is required.")
    if expected_size < 0:
        raise ValueError("The source size is invalid.")
    parent = source_key.rsplit("/", 1)[0] if "/" in source_key else ""
    destination_key = f"{parent}/{destination_name}" if parent else destination_name
    destination_key = validated_managed_object_key(destination_key)
    if destination_key == source_key:
        raise ValueError("The new object name is unchanged.")

    bucket = required_bucket()
    client = s3_client()
    rename_metadata = {
        "relay-rename-signature": _rename_signature(
            bucket=bucket,
            source_key=source_key,
            destination_key=destination_key,
            source_etag=expected_etag,
            source_size=expected_size,
        ),
    }
    destination_head = _head_object(client, bucket, destination_key)
    if destination_head is not None:
        metadata = destination_head.get("Metadata", {})
        signature_matches = hmac.compare_digest(
            str(metadata.get("relay-rename-signature", "")),
            rename_metadata["relay-rename-signature"],
        )
        size_matches = int(destination_head.get("ContentLength", -1)) == expected_size
        if signature_matches and size_matches:
            source_head = _head_object(client, bucket, source_key)
            if source_head is None:
                return destination_key, storage_uri(destination_key)
            if (
                str(source_head.get("ETag", "")) != expected_etag
                or int(source_head.get("ContentLength", -1)) != expected_size
            ):
                raise StaleObjectError(
                    "Rename copy exists, but the source changed. Refresh before deleting it."
                )
            _delete_if_unchanged(client, bucket, source_key, expected_etag)
            return destination_key, storage_uri(destination_key)
        raise FileExistsError("An S3 object with that name already exists.")

    source_head = _head_object(client, bucket, source_key)
    if source_head is None:
        raise FileNotFoundError("S3 object not found.")
    current_etag = str(source_head.get("ETag", ""))
    current_size = int(source_head.get("ContentLength", -1))
    if current_etag != expected_etag or current_size != expected_size:
        raise StaleObjectError("The S3 object changed. Refresh the browser and try again.")
    _multipart_copy_without_overwrite(
        client,
        bucket=bucket,
        source_key=source_key,
        destination_key=destination_key,
        source_etag=expected_etag,
        source_head=source_head,
        rename_metadata=rename_metadata,
    )
    _delete_if_unchanged(client, bucket, source_key, expected_etag)
    return destination_key, storage_uri(destination_key)


def delete_object(key: str, expected_etag: str) -> None:
    managed_key = validated_managed_object_key(key)
    if not expected_etag:
        raise ValueError("The source ETag is required.")
    bucket = required_bucket()
    client = s3_client()
    source_head = _head_object(client, bucket, managed_key)
    if source_head is None:
        raise FileNotFoundError("S3 object not found.")
    if str(source_head.get("ETag", "")) != expected_etag:
        raise StaleObjectError("The S3 object changed. Refresh the browser and try again.")
    _delete_if_unchanged(client, bucket, managed_key, expected_etag)
