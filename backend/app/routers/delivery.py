import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin_token, require_db
from app.schemas.delivery_package import DeliveryPackageCreate, DeliveryPackageRead
from app.schemas.delivery_profile import (
    DeliveryProfileRead,
    DeliveryProfileSummary,
    PackageValidationResponse,
)
from app.services import delivery_profile_service, delivery_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/delivery", tags=["delivery"])


def _schema_outdated() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Delivery database schema is out of date. Restart the API so migrations "
            "can run, then retry."
        ),
    )


@router.get("/profiles", response_model=list[DeliveryProfileSummary])
def list_delivery_profiles(
    enabled_only: bool = Query(True),
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    try:
        return delivery_profile_service.list_profiles(db, enabled_only=enabled_only)
    except SQLAlchemyError:
        logger.exception("list_delivery_profiles failed")
        raise _schema_outdated() from None


@router.get("/profiles/{profile_id}", response_model=DeliveryProfileRead)
def get_delivery_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    try:
        profile = delivery_profile_service.get_profile(db, profile_id)
    except SQLAlchemyError:
        logger.exception("get_delivery_profile failed")
        raise _schema_outdated() from None
    if not profile:
        raise HTTPException(status_code=404, detail="Delivery profile not found")
    return profile


@router.get("/packages", response_model=list[DeliveryPackageRead])
def list_delivery_packages(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
):
    try:
        return delivery_service.list_packages(db, skip=skip, limit=limit)
    except SQLAlchemyError:
        logger.exception("list_delivery_packages failed")
        raise _schema_outdated() from None


@router.post("/packages", response_model=DeliveryPackageRead, status_code=201)
def create_delivery_package(
    payload: DeliveryPackageCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
    __: None = Depends(require_admin_token),
):
    try:
        return delivery_service.create_package(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Package slug already exists") from exc
    except SQLAlchemyError:
        logger.exception("create_delivery_package failed")
        raise _schema_outdated() from None


@router.post(
    "/packages/{package_id}/validate",
    response_model=PackageValidationResponse,
)
def validate_delivery_package(
    package_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_db),
    __: None = Depends(require_admin_token),
):
    try:
        return delivery_profile_service.validate_package(db, package_id)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    except SQLAlchemyError:
        logger.exception("validate_delivery_package failed")
        raise _schema_outdated() from None
