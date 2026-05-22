import { useCallback, useEffect, useMemo, useState } from "react";
import { assetsApi, metadataApi, titlesApi } from "../api/client";
import { specLinesForItem } from "../utils/artworkSpecs";
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
  onSaved?: () => void;
}

const ARTWORK_HINTS: Record<ArtworkType, string> = {
  poster: "2:3",
  backdrop: "16:9",
  logo: "transparent",
  still: "16:9",
  cast_photo: "1:1",
  season_poster: "2:3",
};

function artworkKey(item: { storage_uri: string }): string {
  return item.storage_uri;
}

function isArtworkAsset(a: MediaAsset): a is MediaAsset & { asset_type: ArtworkType } {
  return ARTWORK_TYPES.includes(a.asset_type as ArtworkType);
}

function assetToArtworkItem(asset: MediaAsset): ArtworkItem {
  return {
    asset_type: asset.asset_type as ArtworkType,
    storage_uri: asset.storage_uri,
    filename: asset.filename,
    mime_type: asset.mime_type,
    language: asset.language,
    resolution: asset.resolution,
    notes: asset.notes,
    specs: asset.specs ?? undefined,
  };
}

type DisplayItem = ArtworkItem & { catalogId?: number };

function ArtworkStrip({
  items,
  mode,
  savedUris,
  selected,
  onToggle,
}: {
  items: DisplayItem[];
  mode: "catalog" | "browse";
  savedUris: Set<string>;
  selected: Set<string>;
  onToggle?: (uri: string) => void;
}) {
  if (items.length === 0) return null;

  const byType = new Map<ArtworkType, DisplayItem[]>();
  for (const type of ARTWORK_TYPES) {
    byType.set(type, []);
  }
  for (const item of items) {
    const type = item.asset_type as ArtworkType;
    if (ARTWORK_TYPES.includes(type)) {
      byType.get(type)!.push(item);
    }
  }

  return (
    <>
      {ARTWORK_TYPES.map((type) => {
        const typeItems = byType.get(type) ?? [];
        if (typeItems.length === 0) return null;
        return (
          <section key={`${mode}-${type}`} className="artwork-section">
            <div className="artwork-section-head">
              <h4>{ARTWORK_LABELS[type]}</h4>
              <span className="artwork-section-meta">
                {typeItems.length} · {ARTWORK_HINTS[type]}
              </span>
            </div>
            <div className="artwork-strip" role="list">
              {typeItems.map((item, idx) => {
                const key = artworkKey(item);
                const inCatalog = savedUris.has(key);
                const isSelected = selected.has(key);
                const selectable = mode === "browse" && onToggle && !inCatalog;

                return (
                  <figure
                    key={`${mode}-${type}-${key}-${idx}`}
                    className={`artwork-tile artwork-tile-${type} ${
                      isSelected ? "artwork-tile-selected" : ""
                    } ${inCatalog ? "artwork-tile-in-catalog" : ""}`}
                    role="listitem"
                  >
                    {selectable ? (
                      <button
                        type="button"
                        className="artwork-tile-select"
                        aria-pressed={isSelected}
                        aria-label={
                          isSelected ? "Deselect artwork" : "Select to add"
                        }
                        onClick={() => onToggle(key)}
                      >
                        <span className="artwork-tile-check" aria-hidden>
                          {isSelected ? "✓" : ""}
                        </span>
                        <div className="artwork-tile-img-wrap">
                          <img
                            src={item.storage_uri}
                            alt={specLinesForItem(item)[0]?.value ?? "Artwork"}
                            loading="lazy"
                          />
                        </div>
                      </button>
                    ) : (
                      <div className="artwork-tile-img-wrap artwork-tile-img-static">
                        <img
                          src={item.storage_uri}
                          alt={specLinesForItem(item)[0]?.value ?? "Artwork"}
                          loading="lazy"
                        />
                      </div>
                    )}
                    {inCatalog && (
                      <span className="artwork-tile-badge">In catalog</span>
                    )}
                    <figcaption className="artwork-tile-specs">
                      <ul>
                        {specLinesForItem(item).map((line) => (
                          <li key={`${line.key}-${line.value}`}>
                            <span className="artwork-spec-key">{line.key}</span>
                            <span className="artwork-spec-val">{line.value}</span>
                          </li>
                        ))}
                      </ul>
                    </figcaption>
                  </figure>
                );
              })}
            </div>
          </section>
        );
      })}
    </>
  );
}

export function ArtworkTab({ titleId, externalId, onSaved }: ArtworkTabProps) {
  const [saved, setSaved] = useState<MediaAsset[]>([]);
  const [candidates, setCandidates] = useState<ArtworkItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const canFetch = Boolean(externalId?.startsWith("tmdb:"));

  const savedUris = useMemo(
    () => new Set(saved.map((a) => a.storage_uri)),
    [saved]
  );

  const savedItems: DisplayItem[] = useMemo(
    () => saved.map((a) => ({ ...assetToArtworkItem(a), catalogId: a.id })),
    [saved]
  );

  const newCandidates = useMemo(
    () => candidates.filter((c) => !savedUris.has(artworkKey(c))),
    [candidates, savedUris]
  );

  const selectedNewCount = useMemo(
    () => [...selected].filter((uri) => !savedUris.has(uri)).length,
    [selected, savedUris]
  );

  const loadSaved = useCallback(async () => {
    if (!titleId) {
      setSaved([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await assetsApi.list({ title_id: String(titleId) });
      setSaved(list.filter(isArtworkAsset));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load saved artwork");
    } finally {
      setLoading(false);
    }
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
    setSuccess(null);
    try {
      const items = await metadataApi.importArtwork(externalId);
      setCandidates(items);
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch artwork");
    } finally {
      setFetching(false);
    }
  };

  const toggle = (uri: string) => {
    if (savedUris.has(uri)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(uri)) next.delete(uri);
      else next.add(uri);
      return next;
    });
  };

  const selectAllNew = () => {
    setSelected(new Set(newCandidates.map(artworkKey)));
  };

  const clearSelection = () => setSelected(new Set());

  const handleSaveSelected = async () => {
    if (!titleId) {
      setError("Save the title on the Details tab before storing artwork.");
      return;
    }
    const items = candidates.filter(
      (c) => selected.has(artworkKey(c)) && !savedUris.has(artworkKey(c))
    );
    if (items.length === 0) {
      setError("Select at least one new image to add to the catalog.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await titlesApi.saveArtwork(titleId, items);
      await loadSaved();
      setSelected(new Set());
      setSuccess(
        `Added ${items.length} artwork asset${items.length === 1 ? "" : "s"} to the catalog.`
      );
      onSaved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save artwork");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="artwork-panel">
      <header className="artwork-header">
        <div className="artwork-header-text">
          <h3 className="artwork-title">Artwork library</h3>
          <p className="artwork-subtitle">
            View saved assets, browse TMDB, and add new images to the catalog
          </p>
        </div>
        {canFetch && (
          <button
            type="button"
            className="btn btn-primary artwork-fetch-btn"
            disabled={fetching || loading || saving}
            onClick={handleFetch}
          >
            {fetching ? "Fetching…" : candidates.length ? "Refresh browse" : "Fetch artwork"}
          </button>
        )}
      </header>

      <div className="artwork-meta-row">
        {titleId && saved.length > 0 && (
          <span className="artwork-pill artwork-pill-saved">
            {saved.length} in catalog
          </span>
        )}
        {candidates.length > 0 && (
          <span className="artwork-pill">
            {candidates.length} from TMDB · {newCandidates.length} new
          </span>
        )}
        {selectedNewCount > 0 && (
          <span className="artwork-pill artwork-pill-preview">
            {selectedNewCount} selected to add
          </span>
        )}
      </div>

      {error && <div className="error-banner artwork-error">{error}</div>}
      {success && !error && (
        <div className="metadata-applied-banner artwork-success">{success}</div>
      )}

      {loading && (
        <div className="artwork-state">
          <div className="artwork-spinner" aria-hidden />
          <p>Loading catalog artwork…</p>
        </div>
      )}

      {!loading && !titleId && (
        <div className="artwork-state artwork-state-action">
          <p className="artwork-state-title">Save the title first</p>
          <p className="artwork-state-body">
            Save title details on the Details tab, then return here to fetch and
            store artwork.
          </p>
        </div>
      )}

      {!loading && titleId && (
        <>
          <div className="artwork-view-section">
            <h3 className="artwork-view-heading">In your catalog</h3>
            {saved.length === 0 ? (
              <p className="artwork-view-empty">
                No artwork saved yet. Fetch from TMDB below and add selected images.
              </p>
            ) : (
              <ArtworkStrip
                items={savedItems}
                mode="catalog"
                savedUris={savedUris}
                selected={selected}
              />
            )}
          </div>

          <div className="artwork-view-section artwork-view-section-browse">
            <h3 className="artwork-view-heading">Browse TMDB</h3>
            {!canFetch ? (
              <p className="artwork-view-empty">
                Import metadata on the Details tab to enable TMDB artwork.
              </p>
            ) : fetching ? (
              <div className="artwork-state">
                <div className="artwork-spinner" aria-hidden />
                <p>Loading artwork from TMDB…</p>
              </div>
            ) : candidates.length === 0 ? (
              <p className="artwork-view-empty">
                Click Fetch artwork to browse posters, backdrops, logos, and more.
                Selected images are added to your catalog — nothing is saved until you
                confirm.
              </p>
            ) : (
              <>
                <div className="artwork-select-bar">
                  <button type="button" className="btn btn-ghost" onClick={selectAllNew}>
                    Select all new
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={clearSelection}>
                    Clear
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={selectedNewCount === 0 || saving}
                    onClick={handleSaveSelected}
                  >
                    {saving
                      ? "Saving…"
                      : `Add selected to catalog (${selectedNewCount})`}
                  </button>
                </div>
                <ArtworkStrip
                  items={candidates}
                  mode="browse"
                  savedUris={savedUris}
                  selected={selected}
                  onToggle={toggle}
                />
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
