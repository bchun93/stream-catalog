import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin_token, require_db
from app.schemas.delivery_package import DeliveryPackageCreate, DeliveryPackageRead
from app.services import delivery_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/delivery/packages", tags=["delivery"])


@router.get("", response_model=list[DeliveryPackageRead])
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
        raise HTTPException(
            status_code=503,
            detail=(
                "Delivery database schema is out of date. Restart the API so migrations "
                "can run, then retry."
            ),
        ) from None


@router.post("", response_model=DeliveryPackageRead, status_code=201)
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
        raise HTTPException(
            status_code=503,
            detail=(
                "Delivery database schema is out of date. Restart the API so migrations "
                "can run, then retry."
            ),
        ) from None
