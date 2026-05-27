"""Trainable artwork role classifier for TMDB candidates."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from app.models.artwork_ai import (
    ArtworkClassification,
    ArtworkRole,
    ArtworkTrainingDecision,
    ArtworkTrainingExample,
)
from app.models.media_asset import AssetType, MediaAsset
from app.models.title import Title
from app.schemas.artwork import ArtworkItem, ArtworkSpecs
from app.schemas.artwork_ai import (
    ArtworkAutoAssignResponse,
    ArtworkPrediction,
    ArtworkTrainingExampleRead,
)
from app.services.artwork_metadata import enrich_asset_read
from app.services.artwork_service import save_artwork_selection
from app.services.tmdb_service import collect_artwork_from_tmdb, parse_external_id

MODEL_VERSION = "trainable-baseline-v1"
DEFAULT_AUTO_ASSIGN_THRESHOLD = 0.9

_ROLE_LABELS = {
    ArtworkRole.VERTICAL_POSTER: "Vertical poster",
    ArtworkRole.BOX_ART: "Box art",
    ArtworkRole.HERO_IMAGE: "Hero image",
    ArtworkRole.HORIZONTAL_POSTER: "Horizontal poster",
    ArtworkRole.STILL_FRAME: "Still frame",
    ArtworkRole.LOGO: "Logo",
    ArtworkRole.SEASON_POSTER: "Season poster",
    ArtworkRole.CAST_PHOTO: "Cast photo",
    ArtworkRole.UNKNOWN: "Artwork",
}

_BASELINE_BY_ASSET_TYPE = {
    AssetType.POSTER: ArtworkRole.VERTICAL_POSTER,
    AssetType.BACKDROP: ArtworkRole.HERO_IMAGE,
    AssetType.LOGO: ArtworkRole.LOGO,
    AssetType.STILL: ArtworkRole.STILL_FRAME,
    AssetType.SEASON_POSTER: ArtworkRole.SEASON_POSTER,
    AssetType.CAST_PHOTO: ArtworkRole.CAST_PHOTO,
}

_BASELINE_CONFIDENCE = {
    AssetType.POSTER: 0.72,
    AssetType.BACKDROP: 0.74,
    AssetType.LOGO: 0.82,
    AssetType.STILL: 0.76,
    AssetType.SEASON_POSTER: 0.86,
    AssetType.CAST_PHOTO: 0.88,
}


def role_label(role: ArtworkRole) -> str:
    return _ROLE_LABELS.get(role, role.value.replace("_", " ").title())


def _source_type(item: ArtworkItem) -> str:
    return item.asset_type.value if hasattr(item.asset_type, "value") else str(item.asset_type)


def _feature_dict(item: ArtworkItem, title: Title | None = None) -> dict[str, object]:
    specs = item.specs or ArtworkSpecs()
    width = specs.width
    height = specs.height
    aspect = specs.aspect_ratio
    if aspect is None and width and height:
        aspect = width / height
    return {
        "source_asset_type": _source_type(item),
        "aspect_ratio": aspect,
        "width": width,
        "height": height,
        "language": item.language or specs.language,
        "vote_average": specs.vote_average,
        "vote_count": specs.vote_count,
        "title_type": title.title_type.value if title else None,
    }


def _feature_json(item: ArtworkItem, title: Title | None = None) -> str:
    return json.dumps(_feature_dict(item, title), sort_keys=True)


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _distance(left: dict[str, object], right: dict[str, object]) -> float:
    distance = 0.0
    distance += abs(_safe_float(left.get("aspect_ratio")) - _safe_float(right.get("aspect_ratio")))
    distance += abs(_safe_float(left.get("width")) - _safe_float(right.get("width"))) / 4000
    distance += abs(_safe_float(left.get("height")) - _safe_float(right.get("height"))) / 4000
    if left.get("source_asset_type") != right.get("source_asset_type"):
        distance += 1.0
    if left.get("title_type") != right.get("title_type"):
        distance += 0.25
    return distance


def _baseline_role(item: ArtworkItem) -> tuple[ArtworkRole, float, str]:
    aspect = item.specs.aspect_ratio if item.specs else None
    role = _BASELINE_BY_ASSET_TYPE.get(item.asset_type, ArtworkRole.UNKNOWN)
    if aspect is not None:
        if aspect >= 1.6 and item.asset_type in (AssetType.BACKDROP, AssetType.STILL):
            role = ArtworkRole.HERO_IMAGE if item.asset_type == AssetType.BACKDROP else ArtworkRole.STILL_FRAME
        elif aspect < 1.0 and item.asset_type in (AssetType.POSTER, AssetType.SEASON_POSTER):
            role = ArtworkRole.VERTICAL_POSTER if item.asset_type == AssetType.POSTER else ArtworkRole.SEASON_POSTER
    confidence = _BASELINE_CONFIDENCE.get(item.asset_type, 0.45)
    return role, confidence, "baseline source bucket and aspect ratio"


def _training_examples(db: Session) -> list[ArtworkTrainingExample]:
    return (
        db.query(ArtworkTrainingExample)
        .filter(ArtworkTrainingExample.decision != ArtworkTrainingDecision.REJECTED)
        .order_by(ArtworkTrainingExample.updated_at.desc())
        .limit(500)
        .all()
    )


def _learned_role(
    item: ArtworkItem, title: Title, examples: list[ArtworkTrainingExample]
) -> tuple[ArtworkRole, float, str] | None:
    features = _feature_dict(item, title)
    scored: list[tuple[float, ArtworkTrainingExample]] = []
    for example in examples:
        if not example.feature_json:
            continue
        try:
            example_features = json.loads(example.feature_json)
        except json.JSONDecodeError:
            continue
        scored.append((_distance(features, example_features), example))
    if not scored:
        return None

    nearest = sorted(scored, key=lambda row: row[0])[:5]
    role_votes: Counter[ArtworkRole] = Counter(example.assigned_role for _, example in nearest)
    role, vote_count = role_votes.most_common(1)[0]
    best_distance = nearest[0][0]
    confidence = min(0.96, max(0.55, 0.98 - (best_distance * 0.28)))
    if vote_count > 1:
        confidence = min(0.98, confidence + 0.04 * (vote_count - 1))
    rationale = (
        f"learned from {len(examples)} labeled example"
        f"{'' if len(examples) == 1 else 's'}; nearest distance {best_distance:.2f}"
    )
    return role, confidence, rationale


def _classified_item(item: ArtworkItem, role: ArtworkRole, confidence: float) -> ArtworkItem:
    label = role_label(role)
    specs = item.specs or ArtworkSpecs()
    specs = specs.model_copy(
        update={
            "label": label,
        }
    )
    note = f"source:tmdb; AI assigned {label}; confidence:{confidence:.2f}"
    if item.language and item.language != "en":
        note = f"{note}; lang:{item.language}"
    return item.model_copy(update={"notes": note, "specs": specs})


def classify_candidates(
    db: Session,
    title: Title,
    items: list[ArtworkItem],
    *,
    threshold: float = DEFAULT_AUTO_ASSIGN_THRESHOLD,
    persist: bool = True,
) -> list[ArtworkPrediction]:
    examples = _training_examples(db)
    predictions: list[ArtworkPrediction] = []
    for item in items:
        learned = _learned_role(item, title, examples)
        if learned:
            role, confidence, rationale = learned
        else:
            role, confidence, rationale = _baseline_role(item)
        classified = _classified_item(item, role, confidence)
        predictions.append(
            ArtworkPrediction(
                item=classified,
                predicted_role=role,
                confidence=round(confidence, 3),
                model_version=MODEL_VERSION,
                auto_apply=confidence >= threshold,
                rationale=rationale,
            )
        )
        if persist:
            db.add(
                ArtworkClassification(
                    title_id=title.id,
                    candidate_uri=item.storage_uri,
                    filename=item.filename,
                    source_asset_type=item.asset_type,
                    predicted_role=role,
                    confidence=confidence,
                    model_version=MODEL_VERSION,
                    auto_applied=False,
                    reviewed=False,
                    feature_json=_feature_json(item, title),
                    rationale=rationale,
                )
            )
    if persist and items:
        db.commit()
    return predictions


async def classify_title_artwork(
    db: Session, title: Title, *, threshold: float = DEFAULT_AUTO_ASSIGN_THRESHOLD
) -> list[ArtworkPrediction]:
    if not title.external_id:
        return []
    media_type, tmdb_id = parse_external_id(title.external_id)
    items = await collect_artwork_from_tmdb(media_type, tmdb_id)
    return classify_candidates(db, title, items, threshold=threshold)


async def auto_assign_title_artwork(
    db: Session, title: Title, *, threshold: float = DEFAULT_AUTO_ASSIGN_THRESHOLD
) -> ArtworkAutoAssignResponse:
    predictions = await classify_title_artwork(db, title, threshold=threshold)
    to_save = [prediction.item for prediction in predictions if prediction.auto_apply]
    assets = save_artwork_selection(db, title.id, to_save) if to_save else []
    saved_uris = {item.storage_uri for item in to_save}
    if saved_uris:
        db.query(ArtworkClassification).filter(
            ArtworkClassification.title_id == title.id,
            ArtworkClassification.candidate_uri.in_(saved_uris),
        ).update({"auto_applied": True}, synchronize_session=False)
        db.commit()
    return ArtworkAutoAssignResponse(
        title_id=title.id,
        threshold=threshold,
        saved_count=len(to_save),
        review_count=len([p for p in predictions if not p.auto_apply]),
        assets=[enrich_asset_read(asset) for asset in assets],
        predictions=predictions,
    )


def list_training_examples(
    db: Session, *, limit: int = 200
) -> list[ArtworkTrainingExampleRead]:
    rows = (
        db.query(ArtworkTrainingExample)
        .order_by(ArtworkTrainingExample.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [ArtworkTrainingExampleRead.model_validate(row) for row in rows]


def record_label(db: Session, request) -> ArtworkTrainingExampleRead:
    item: ArtworkItem = request.item
    example = ArtworkTrainingExample(
        title_id=request.title_id,
        candidate_uri=item.storage_uri,
        filename=item.filename,
        source_asset_type=item.asset_type,
        assigned_role=request.assigned_role,
        decision=request.decision,
        reviewer=request.reviewer,
        notes=request.notes,
        feature_json=_feature_json(item),
    )
    db.add(example)
    db.commit()
    db.refresh(example)
    return ArtworkTrainingExampleRead.model_validate(example)


def review_queue(db: Session, *, limit: int = 100) -> list[ArtworkClassification]:
    rows = (
        db.query(ArtworkClassification)
        .filter(
            ArtworkClassification.auto_applied.is_(False),
            ArtworkClassification.reviewed.is_(False),
        )
        .order_by(ArtworkClassification.confidence.desc())
        .limit(limit)
        .all()
    )
    # Deduplicate repeated classification runs by URI.
    seen: set[tuple[int, str]] = set()
    unique: list[ArtworkClassification] = []
    for row in rows:
        key = (row.title_id, row.candidate_uri)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique
