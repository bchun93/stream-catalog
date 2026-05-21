import { useCallback, useEffect, useMemo, useState } from "react";
import { assetsApi, metadataApi, titlesApi } from "../api/client";
import {
  ARTWORK_LABELS,
  ARTWORK_TYPES,
  type ArtworkItem,
  type ArtworkType,
  type MediaAsset,
} from "../types";

interface ArtworkTabProps {
  titleId?: number;
  externalId?: string | null;
}

function isArtworkAsset(a: MediaAsset): a is MediaAsset & { asset_type: ArtworkType } {
  return ARTWORK_TYPES.includes(a.asset_type as ArtworkType);
}

function previewLabel(item: ArtworkItem | MediaAsset): string {
  const notes = item.notes ?? "";
  if (notes.includes(" as ")) {
    return notes.split(";").pop()?.trim() ?? item.filename;
  }
  if (notes.includes("season:")) {
    const match = notes.match(/season:(\d+)/);
    return match ? `Season ${match[1]}` : item.filename;
  }
  if ("language" in item && item.language) {
    return item.language.toUpperCase();
  }
  return item.filename;
}

export function ArtworkTab({ titleId, externalId }: ArtworkTabProps) {
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [preview, setPreview] = useState<ArtworkItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  const canFetch = Boolean(externalId?.startsWith("tmdb:"));

  const loadSaved = useCallback(() => {
    if (!titleId) return;
    setLoading(true);
    setError(null);
    assetsApi
      .list({ title_id: String(titleId) })
      .then((list) => {
        const artwork = list.filter(isArtworkAsset);
        setAssets(artwork);
        if (artwork.length > 0) {
          setFetched(true);
          setPreview([]);
        }
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load artwork")
      )
      .finally(() => setLoading(false));
  }, [titleId]);

  useEffect(() => {
    loadSaved();
  }, [loadSaved]);

  const handleFetch = async () => {
    if (!canFetch || !externalId) {
      setError("Import TMDB metadata on the Details tab first.");
      return;
    }
    setFetching(true);
    setError(null);
    try {
      if (titleId) {
        const synced = await titlesApi.syncArtwork(titleId);
        setAssets(synced.filter(isArtworkAsset));
        setPreview([]);
        setFetched(true);
      } else {
        const items = await metadataApi.importArtwork(externalId);
        setPreview(items);
        setAssets([]);
        setFetched(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch artwork");
    } finally {
      setFetching(false);
    }
  };

  const grouped = useMemo(() => {
    const source: (ArtworkItem | MediaAsset)[] = titleId && assets.length > 0
      ? assets
      : preview;
    const map = new Map<ArtworkType, (ArtworkItem | MediaAsset)[]>();
    for (const type of ARTWORK_TYPES) {
      map.set(type, []);
    }
    for (const item of source) {
      const type = item.asset_type as ArtworkType;
      if (ARTWORK_TYPES.includes(type)) {
        map.get(type)!.push(item);
      }
    }
    return map;
  }, [assets, preview, titleId]);

  const totalCount =
    titleId && assets.length > 0 ? assets.length : preview.length;

  const isPreviewOnly = !titleId && preview.length > 0;

  return (
    <div className="artwork-tab">
      <div className="artwork-toolbar">
        <p className="artwork-summary">
          {!fetched && !loading
            ? "Artwork is loaded on demand from TMDB."
            : isPreviewOnly
              ? `${preview.length} images loaded — save the title, then Fetch artwork again to store them`
              : `${totalCount} artwork assets`}
        </p>
        {canFetch && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={fetching || loading}
            onClick={handleFetch}
          >
            {fetching ? "Fetching…" : "Fetch artwork"}
          </button>
        )}
      </div>
      {error && <div className="error-banner">{error}</div>}
      {loading && <p className="empty">Loading saved artwork…</p>}
      {!loading && !canFetch && (
        <div className="artwork-empty">
          <p>Import metadata from TMDB on the Details tab, then return here to fetch artwork.</p>
        </div>
      )}
      {!loading &&
        canFetch &&
        !fetched &&
        !fetching && (
          <div className="artwork-empty">
            <p>Click Fetch artwork to load posters, backdrops, logos, and more from TMDB.</p>
          </div>
        )}
      {!loading &&
        fetched &&
        ARTWORK_TYPES.map((type) => {
          const items = grouped.get(type) ?? [];
          if (items.length === 0) return null;
          return (
            <section key={type} className="artwork-section">
              <h3 className="artwork-section-title">
                {ARTWORK_LABELS[type]}
                <span className="artwork-count">{items.length}</span>
              </h3>
              <div className="artwork-grid">
                {items.map((item, idx) => (
                  <figure
                    key={`${type}-${item.storage_uri}-${idx}`}
                    className={`artwork-card artwork-card-${type}`}
                  >
                    <img
                      src={item.storage_uri}
                      alt={previewLabel(item)}
                      loading="lazy"
                    />
                    <figcaption>{previewLabel(item)}</figcaption>
                  </figure>
                ))}
              </div>
            </section>
          );
        })}
      {!loading && fetched && totalCount === 0 && (
        <p className="empty">No artwork found for this title on TMDB.</p>
      )}
    </div>
  );
}
