import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_admin_token, require_consumer_secret
from app.schemas.rekognition import (
    AnalyzeRequest,
    AnalyzeResponse,
    ConsumeResponse,
    DetectionRead,
    FeatureResultRead,
    RekognitionJobRead,
)
from app.services import media_service
from app.services.rekognition import ddb
from app.services.rekognition.constants import Feature
from app.services.rekognition.consumer import (
    ConsumerConfigError,
    DrainResult,
    drain_queue,
)
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
    # This endpoint incurs AWS cost, so refuse to run it wide-open: require ADMIN_API_KEY to
    # be configured (require_admin_token then enforces the header match).
    if not (settings.admin_api_key or "").strip():
        raise HTTPException(
            status_code=503,
            detail="Set ADMIN_API_KEY to enable Rekognition analyze (this endpoint incurs AWS cost).",
        )

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
    except Exception as exc:  # noqa: BLE001 - log full error, return generic message
        logger.exception("analyze_asset failed for asset %s", asset_id)
        raise HTTPException(
            status_code=503,
            detail="Rekognition analyze failed; check server logs for details.",
        ) from exc

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
        raise HTTPException(
            status_code=503, detail="Could not load Rekognition jobs; check server logs."
        ) from exc
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
            status_code=503, detail="Could not load detections; check server logs."
        ) from exc
    return [DetectionRead(**row) for row in rows]


def _drain_to_response(result: DrainResult) -> ConsumeResponse:
    return ConsumeResponse(
        received=result.received,
        processed=result.processed,
        deleted=result.deleted,
        failed=result.failed,
        messages=result.messages,
    )


@router.post("/rekognition/consume", response_model=ConsumeResponse)
def consume(_: None = Depends(require_consumer_secret)):
    """Scheduled SQS drain (GitHub Actions cron). Secret-protected, never publicly callable."""
    try:
        # Bounded so the cron's curl --max-time can't trip while the server keeps polling.
        result = drain_queue(max_batches=5, wait_time_seconds=5)
    except ConsumerConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("consume failed")
        raise HTTPException(
            status_code=503, detail="Consumer drain failed; check server logs."
        ) from exc
    return _drain_to_response(result)


@router.post("/rekognition/drain", response_model=ConsumeResponse)
def manual_drain(_: None = Depends(require_admin_token)):
    """Manual 'Drain now' for the UI — admin-token protected (not the cron secret)."""
    if not (settings.admin_api_key or "").strip():
        raise HTTPException(
            status_code=503,
            detail="Set ADMIN_API_KEY to enable the manual drain.",
        )
    try:
        result = drain_queue(max_batches=3)
    except ConsumerConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("manual drain failed")
        raise HTTPException(
            status_code=503, detail="Drain failed; check server logs."
        ) from exc
    return _drain_to_response(result)
