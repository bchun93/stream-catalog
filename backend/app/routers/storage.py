import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.deps import require_ingest_operator_token
from app.schemas.storage import (
    StorageBrowseRead,
    StorageConfigRead,
    StorageFolderRead,
    StorageObjectRead,
    StoragePresignDownloadRead,
    StoragePresignUploadRead,
    StoragePresignUploadRequest,
)
from app.services import s3_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/storage", tags=["storage"])


def _to_browse_read(result: s3_service.S3BrowseResult) -> StorageBrowseRead:
    return StorageBrowseRead(
        bucket=result.bucket,
        root_prefix=result.root_prefix,
        prefix=result.prefix,
        folders=[StorageFolderRead(name=f.name, prefix=f.prefix) for f in result.folders],
        objects=[
            StorageObjectRead(
                key=obj.key,
                name=obj.name,
                size_bytes=obj.size_bytes,
                last_modified=obj.last_modified,
                storage_uri=s3_service.storage_uri(obj.key),
            )
            for obj in result.objects
        ],
        truncated=result.truncated,
    )


@router.get("/config", response_model=StorageConfigRead)
def get_storage_config(_: None = Depends(require_ingest_operator_token)):
    try:
        bucket = s3_service.required_bucket()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StorageConfigRead(
        bucket=bucket,
        root_prefix=s3_service.settings_root_prefix(),
        token_required=bool((settings.ingest_operator_token or "").strip()),
    )


@router.get("/browse", response_model=StorageBrowseRead)
def browse_storage(
    prefix: str = Query("", description="Folder path under the configured ingest root"),
    max_keys: int = Query(500, ge=1, le=5000),
    _: None = Depends(require_ingest_operator_token),
):
    try:
        result = s3_service.browse_objects(prefix, max_keys=max_keys)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("browse_storage failed")
        raise HTTPException(status_code=503, detail=f"S3 browse failed: {exc}") from exc
    return _to_browse_read(result)


@router.post("/presign-upload", response_model=StoragePresignUploadRead)
def presign_upload(
    payload: StoragePresignUploadRequest,
    _: None = Depends(require_ingest_operator_token),
):
    try:
        result = s3_service.presign_upload(
            relative_prefix=payload.prefix,
            filename=payload.filename,
            content_type=payload.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("presign_upload failed")
        raise HTTPException(status_code=503, detail=f"S3 presign upload failed: {exc}") from exc
    return StoragePresignUploadRead(
        key=result.key,
        storage_uri=result.storage_uri,
        upload_url=result.upload_url,
        method=result.method,
        headers=result.headers,
    )


@router.get("/presign-download", response_model=StoragePresignDownloadRead)
def presign_download(
    key: str = Query(..., min_length=1),
    _: None = Depends(require_ingest_operator_token),
):
    try:
        url = s3_service.presign_download(key)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("presign_download failed")
        raise HTTPException(status_code=503, detail=f"S3 presign download failed: {exc}") from exc
    return StoragePresignDownloadRead(
        download_url=url,
        key=key,
        storage_uri=s3_service.storage_uri(key),
    )
