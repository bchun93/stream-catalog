import { useCallback, useEffect, useMemo, useState } from "react";
import { metadataApi, titlesApi } from "../api/client";
import { specLinesForItem } from "../utils/artworkSpecs";
import { filterArtworkAssets } from "../utils/artworkTypes";
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
  metadataJson?: string | null;
  /** When false, panel is hidden but stays mounted so catalog state persists. */
  visible?: boolean;
  /** Saves the title when needed and returns its id. */
  onEnsureTitleSaved?: () => Promise<number>;
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

function preferredArtworkLabel(item: ArtworkItem, labels: string[]): string {
  const aspect = item.specs?.aspect_ratio ?? null;

  if (item.asset_type === "poster" || item.asset_type === "season_poster") {
    if (labels.includes("Vertical poster")) return "Vertical poster";
    if (labels.includes("Box art")) return "Box art";
  }
  if (item.asset_type === "backdrop" || (typeof aspect === "number" && aspect >= 1.6)) {
    if (labels.includes("Hero image")) return "Hero image";
    if (labels.includes("Horizontal poster")) return "Horizontal poster";
  }
  if (item.asset_type === "still" && labels.includes("Still frame")) return "Still frame";
  if (item.asset_type === "logo" && labels.includes("Logo")) return "Logo";
  if (item.asset_type === "poster" || item.asset_type === "season_poster") {
    return "Vertical poster";
  }
  if (item.asset_type === "backdrop" || (typeof aspect === "number" && aspect >= 1.6)) {
    return "Hero image";
  }
  if (item.asset_type === "still") return "Still frame";
  if (item.asset_type === "logo") return "Logo";
  return labels[0] ?? "Artwork";
}

function normalizeFetchedArtwork(items: ArtworkItem[]): ArtworkItem[] {
  return items.map((item) => {
    const existingLabel = item.specs?.label;
    const labels =
      typeof existingLabel === "string" && existingLabel.trim()
        ? existingLabel.split("/").map((label) => label.trim()).filter(Boolean)
        : [];
    const label = preferredArtworkLabel(item, labels);
    return {
      ...item,
      specs: {
        ...(item.specs ?? {}),
        label,
      },
    };
  });
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

const SAVED_ARTWORK_CACHE = new Map<number, MediaAsset[]>();

function ArtworkStrip({
  items,
  mode,
  savedUris,
  selected,
  onToggle,
  downloadUrlFor,
}: {
  items: DisplayItem[];
  mode: "catalog" | "browse";
  savedUris: Set<string>;
  selected: Set<string>;
  onToggle?: (uri: string) => void;
  downloadUrlFor?: (catalogId: number) => string;
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
                      {mode === "catalog" && item.catalogId && downloadUrlFor && (
                        <a
                          className="btn btn-ghost artwork-download-btn"
                          href={downloadUrlFor(item.catalogId)}
                        >
                          Download
                        </a>
                      )}
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

export function ArtworkTab({
  titleId,
  externalId,
  visible = true,
  onEnsureTitleSaved,
  onSaved,
}: ArtworkTabProps) {
  const [saved, setSaved] = useState<MediaAsset[]>([]);
  const [candidates, setCandidates] = useState<ArtworkItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const canFetch = Boolean(externalId?.startsWith("tmdb:"));

  const savedArtworkItems: DisplayItem[] = useMemo(
    () => saved.map((a) => ({ ...assetToArtworkItem(a), catalogId: a.id })),
    [saved]
  );

  const savedItems: DisplayItem[] = useMemo(
    () => savedArtworkItems,
    [savedArtworkItems]
  );

  const savedUris = useMemo(
    () => new Set(savedArtworkItems.map((a) => a.storage_uri)),
    [savedArtworkItems]
  );

  const newCandidates = useMemo(
    () => candidates.filter((c) => !savedUris.has(artworkKey(c))),
    [candidates, savedUris]
  );

  const selectedNewCount = useMemo(
    () => [...selected].filter((uri) => !savedUris.has(uri)).length,
    [selected, savedUris]
  );

  const loadSaved = useCallback(async (overrideId?: number) => {
    const targetId = overrideId ?? titleId;
    if (!targetId) {
      setSaved([]);
      return [];
    }
    const cached = SAVED_ARTWORK_CACHE.get(targetId);
    if (cached) {
      setSaved(cached);
    }
    setCatalogLoading(!cached);
    setError(null);
    try {
      const list = await titlesApi.listArtwork(targetId);
      SAVED_ARTWORK_CACHE.set(targetId, list);
      setSaved(list);
      return list;
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to load saved artwork";
      setError(message);
      setSaved([]);
      return [];
    } finally {
      setCatalogLoading(false);
    }
  }, [titleId]);

  // Load whenever title changes (e.g. open edit modal).
  useEffect(() => {
    void loadSaved();
  }, [loadSaved]);

  // Refresh when user switches to the Artwork tab.
  useEffect(() => {
    if (visible && titleId) {
      void loadSaved();
    }
  }, [visible, titleId, loadSaved]);

  const handleSyncFromMetadata = async () => {
    if (!titleId) {
      setError("Save the title on the Metadata tab before syncing artwork.");
      return;
    }
    setSyncing(true);
    setError(null);
    setSuccess(null);
    try {
      const assets = await titlesApi.syncArtwork(titleId);
      SAVED_ARTWORK_CACHE.set(titleId, assets);
      setSaved(assets);
      setSuccess(
        assets.length > 0
          ? `Synced ${assets.length} artwork image${assets.length === 1 ? "" : "s"} from core metadata.`
          : "No artwork matched core metadata filenames for this title."
      );
      onSaved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to sync artwork from metadata");
    } finally {
      setSyncing(false);
    }
  };

  const handleFetch = async () => {
    if (!canFetch || !externalId) {
      setError("Import TMDB metadata on the Metadata tab first.");
      return;
    }
    setFetching(true);
    setError(null);
    setSuccess(null);
    try {
      const items = await metadataApi.importArtwork(externalId);
      setCandidates(normalizeFetchedArtwork(items));
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
    const items = candidates.filter(
      (c) => selected.has(artworkKey(c)) && !savedUris.has(artworkKey(c))
    );
    if (items.length === 0) {
      setError("Select at least one image to save to the title.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      let activeTitleId = titleId;
      if (!activeTitleId) {
        if (!onEnsureTitleSaved) {
          setError("Save the title on the Metadata tab before storing artwork.");
          return;
        }
        activeTitleId = await onEnsureTitleSaved();
      }
      const stored = await titlesApi.saveArtwork(activeTitleId, items);
      const artworkOnly = filterArtworkAssets(stored);
      SAVED_ARTWORK_CACHE.set(activeTitleId, artworkOnly);
      setSaved(artworkOnly);
      setSelected(new Set());
      setSuccess(
        `Saved ${items.length} artwork image${items.length === 1 ? "" : "s"} to the title.`
      );
      onSaved?.();
      await loadSaved(activeTitleId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save artwork");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className={`artwork-panel${visible ? "" : " artwork-panel-hidden"}`}
      hidden={!visible}
    >
      {!titleId ? null : (
        <header className="artwork-header">
          <h3 className="artwork-title">Artwork library</h3>
        </header>
      )}

      {(titleId && savedItems.length > 0) ||
      candidates.length > 0 ||
      selectedNewCount > 0 ? (
        <div className="artwork-meta-row">
          {titleId && savedItems.length > 0 && (
            <span className="artwork-pill artwork-pill-saved">
              {savedItems.length} in catalog
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
      ) : null}

      {error && <div className="error-banner artwork-error">{error}</div>}
      {success && !error && (
        <div className="metadata-applied-banner artwork-success">{success}</div>
      )}

      {titleId && (
        <div className="artwork-view-section">
          <div className="artwork-toolbar artwork-toolbar-compact">
            <h3 className="form-section-title">In your catalog</h3>
            {canFetch && (
              <button
                type="button"
                className="btn btn-ghost artwork-toolbar-action"
                disabled={syncing || fetching || saving}
                onClick={handleSyncFromMetadata}
              >
                {syncing ? "Syncing…" : "Sync from metadata"}
              </button>
            )}
          </div>
          {catalogLoading ? (
            <div className="artwork-state">
              <div className="artwork-spinner" aria-hidden />
              <p>Loading catalog artwork…</p>
            </div>
          ) : savedItems.length === 0 ? (
            <p className="artwork-view-empty">
              No artwork saved yet. Sync from metadata or fetch from TMDB below.
            </p>
          ) : (
            <ArtworkStrip
              items={savedItems}
              mode="catalog"
              savedUris={savedUris}
              selected={selected}
              downloadUrlFor={(assetId) =>
                titlesApi.artworkDownloadUrl(titleId, assetId)
              }
            />
          )}
        </div>
      )}

      <div className="artwork-view-section artwork-view-section-browse">
        <div className="artwork-toolbar">
          <div className="artwork-toolbar-text">
            <h3 className="form-section-title">Browse TMDB</h3>
            <p className="form-section-desc">
              {canFetch
                ? "Click Fetch artwork to browse all TMDB posters, backdrops, still frames, logos, and more. Fetching does not save anything to your catalog until you save the selected images."
                : "Import metadata on the Metadata tab to enable TMDB artwork."}
            </p>
          </div>
          {canFetch && (
            <button
              type="button"
              className="btn btn-primary artwork-toolbar-action"
              disabled={fetching || saving}
              onClick={handleFetch}
            >
              {fetching ? "Fetching…" : "Fetch artwork"}
            </button>
          )}
        </div>
        {canFetch && fetching ? (
          <div className="artwork-state">
            <div className="artwork-spinner" aria-hidden />
            <p>Loading artwork from TMDB…</p>
          </div>
        ) : canFetch && candidates.length > 0 ? (
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
                  : `Save selected artwork (${selectedNewCount})`}
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
        ) : null}
      </div>
    </div>
  );
}
