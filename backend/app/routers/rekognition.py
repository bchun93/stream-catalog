import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin_token
from app.schemas.rekognition import (
    AnalyzeRequest,
    AnalyzeResponse,
    DetectionRead,
    FeatureResultRead,
    RekognitionJobRead,
)
from app.services import media_service
from app.services.rekognition import ddb
from app.services.rekognition.constants import Feature
from app.services.rekognition.start import (
    AnalysisConfigError,
    AnalysisInputError,
    start_analysis,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rekognition"])


def _parse_feature(value: str | None) -> Feature | None:
    if not value:
        return None
    try:
        return Feature(value.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown feature '{value}'.") from exc


@router.post("/assets/{asset_id}/rekognition/analyze", response_model=AnalyzeResponse)
def analyze_asset(
    asset_id: int,
    payload: AnalyzeRequest | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
):
    asset = media_service.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        result = start_analysis(
            asset, s3_key_override=(payload.s3_key if payload else None)
        )
    except AnalysisInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnalysisConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface AWS/DynamoDB failures clearly
        logger.exception("analyze_asset failed for asset %s", asset_id)
        raise HTTPException(status_code=503, detail=f"Rekognition analyze failed: {exc}") from exc

    return AnalyzeResponse(
        asset_id=result.asset_id,
        bucket=result.bucket,
        key=result.key,
        warnings=result.warnings,
        results=[
            FeatureResultRead(
                feature=r.feature.value,
                status=r.status,
                aws_job_id=r.aws_job_id,
                started=r.started,
                message=r.message,
            )
            for r in result.results
        ],
    )


@router.get(
    "/assets/{asset_id}/rekognition/jobs", response_model=list[RekognitionJobRead]
)
def list_jobs(asset_id: int):
    try:
        jobs = ddb.list_jobs_for_asset(str(asset_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("list_jobs failed for asset %s", asset_id)
        raise HTTPException(status_code=503, detail=f"Could not load jobs: {exc}") from exc
    return [RekognitionJobRead(**job) for job in jobs]


@router.get(
    "/assets/{asset_id}/rekognition/detections", response_model=list[DetectionRead]
)
def list_detections(
    asset_id: int,
    feature: str | None = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=5000),
):
    parsed = _parse_feature(feature)
    try:
        rows = ddb.query_detections(
            asset_id=str(asset_id), feature=parsed, limit=limit
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("list_detections failed for asset %s", asset_id)
        raise HTTPException(
            status_code=503, detail=f"Could not load detections: {exc}"
        ) from exc
    return [DetectionRead(**row) for row in rows]
