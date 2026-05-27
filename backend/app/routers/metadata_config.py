from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_db
from app.schemas.metadata_config import MetadataConfigRead, MetadataConfigUpdate
from app.services import metadata_config_service

router = APIRouter(prefix="/metadata-config", tags=["metadata-config"])


@router.get("", response_model=MetadataConfigRead)
def get_metadata_config(
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    try:
        return metadata_config_service.get_config(db)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc


@router.put("", response_model=MetadataConfigRead)
def update_metadata_config(
    payload: MetadataConfigUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    try:
        return metadata_config_service.update_config(db, payload.settings)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc
