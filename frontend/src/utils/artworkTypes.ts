import { ARTWORK_TYPES, type ArtworkType, type MediaAsset } from "../types";

/** Normalize API enum strings (e.g. "poster", "AssetType.POSTER"). */
export function normalizeArtworkType(
  value: string | undefined | null
): ArtworkType | null {
  if (!value) return null;
  const raw = value.includes(".") ? value.split(".").pop()! : value;
  const lower = raw.toLowerCase();
  return ARTWORK_TYPES.find((t) => t === lower) ?? null;
}

export function isArtworkAsset(
  asset: MediaAsset
): asset is MediaAsset & { asset_type: ArtworkType } {
  return normalizeArtworkType(asset.asset_type) !== null;
}

export function filterArtworkAssets(assets: MediaAsset[]): MediaAsset[] {
  return assets.filter(isArtworkAsset);
}
