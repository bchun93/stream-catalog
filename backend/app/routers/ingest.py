import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_ingest_operator_token
from app.models.title import Title
from app.schemas.ingest import (
    IngestJobCreateRequest,
    IngestJobRead,
    IngestManifestRead,
    IngestManifestValidateRequest,
    IngestManifestValidateResponse,
)
from app.services import ingest_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


def _as_manifest_read(manifest) -> IngestManifestRead:
    return IngestManifestRead(
        id=manifest.id,
        name=manifest.name,
        version=manifest.version,
        description=manifest.description,
        enabled=manifest.enabled,
        rules=manifest.rules,
        created_at=manifest.created_at,
        updated_at=manifest.updated_at,
    )


@router.get("/manifests", response_model=list[IngestManifestRead])
def list_manifests(
    enabled_only: bool = Query(False),
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_operator_token),
):
    manifests = ingest_service.list_manifests(db, enabled_only=enabled_only)
    return [_as_manifest_read(m) for m in manifests]


@router.post("/manifests/validate", response_model=IngestManifestValidateResponse)
def validate_manifest(
    payload: IngestManifestValidateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_operator_token),
):
    try:
        return ingest_service.validate_manifest(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/jobs", response_model=IngestJobRead, status_code=201)
def create_ingest_job(
    payload: IngestJobCreateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_operator_token),
):
    title = db.query(Title).filter(Title.id == payload.title_id).first()
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    request_id = uuid4().hex[:12]
    logger.info("ingest request accepted", extra={"request_id": request_id})
    try:
        return ingest_service.create_job(db, payload, request_id=request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/jobs", response_model=list[IngestJobRead])
def list_ingest_jobs(
    title_id: int | None = None,
    limit: int = Query(50, ge=1, le=300),
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_operator_token),
):
    return ingest_service.list_jobs(db, title_id=title_id, limit=limit)


@router.get("/jobs/{job_id}", response_model=IngestJobRead)
def get_ingest_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_operator_token),
):
    job = ingest_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingest job not found")
    return job
