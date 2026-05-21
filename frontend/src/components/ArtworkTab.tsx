import { useCallback, useEffect, useMemo, useState } from "react";
import { assetsApi, titlesApi } from "../api/client";
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
  preview?: ArtworkItem[];
  isPreview?: boolean;
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

export function ArtworkTab({
  titleId,
  externalId,
  preview = [],
  isPreview = false,
}: ArtworkTabProps) {
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!titleId) return;
    setLoading(true);
    setError(null);
    assetsApi
      .list({ title_id: String(titleId) })
      .then((list) => setAssets(list.filter(isArtworkAsset)))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load artwork"))
      .finally(() => setLoading(false));
  }, [titleId]);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const source = titleId
      ? assets
      : preview.map((p) => ({
          ...p,
          id: 0,
          title_id: 0,
          status: "ready" as const,
          version: 1,
          created_at: "",
          updated_at: "",
        }));
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

  const totalCount = titleId
    ? assets.length
    : preview.length;

  const handleSync = async () => {
    if (!titleId) return;
    setSyncing(true);
    setError(null);
    try {
      await titlesApi.syncArtwork(titleId);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const canSync =
    Boolean(titleId) &&
    Boolean(externalId?.startsWith("tmdb:"));

  if (!titleId && preview.length === 0) {
    return (
      <div className="artwork-empty">
        <p>Import metadata from TMDB on the Details tab to load artwork previews.</p>
      </div>
    );
  }

  return (
    <div className="artwork-tab">
      <div className="artwork-toolbar">
        <p className="artwork-summary">
          {isPreview
            ? `${preview.length} images from TMDB — saved when you create the title`
            : `${totalCount} artwork assets`}
        </p>
        {canSync && (
          <button
            type="button"
            className="btn btn-ghost"
            disabled={syncing || loading}
            onClick={handleSync}
          >
            {syncing ? "Syncing…" : "Refresh from TMDB"}
          </button>
        )}
      </div>
      {error && <div className="error-banner">{error}</div>}
      {loading && <p className="empty">Loading artwork…</p>}
      {!loading &&
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
      {!loading && totalCount === 0 && (
        <p className="empty">No artwork for this title yet.</p>
      )}
    </div>
  );
}
