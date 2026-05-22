import json

from app.models.media_asset import MediaAsset
from app.schemas.artwork import ArtworkItem, ArtworkSpecs
from app.schemas.media_asset import MediaAssetRead


def artwork_item_metadata_json(item: ArtworkItem) -> str:
    payload = {
        "notes": item.notes,
        "specs": item.specs.model_dump(exclude_none=True),
    }
    return json.dumps(payload)


def specs_from_asset(asset: MediaAsset) -> ArtworkSpecs:
    if asset.metadata_json:
        try:
            data = json.loads(asset.metadata_json)
            raw = data.get("specs") or {}
            if raw:
                return ArtworkSpecs.model_validate(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    label = None
    if asset.notes:
        for part in asset.notes.split(";"):
            part = part.strip()
            if part.startswith("source:") or part.startswith("locale:"):
                continue
            if part.startswith("lang:"):
                continue
            if part and " as " in part or part.startswith("season:"):
                label = part.replace("season:", "Season ")
                break
            if part and not part.startswith("source"):
                label = part
                break
    return ArtworkSpecs(
        resolution=asset.resolution,
        language=asset.language,
        label=label,
    )


def enrich_asset_read(asset: MediaAsset) -> MediaAssetRead:
    data = MediaAssetRead.model_validate(asset)
    data.specs = specs_from_asset(asset)
    return data
