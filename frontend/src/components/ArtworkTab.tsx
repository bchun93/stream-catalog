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

const CORE_ARTWORK_LABELS: Record<string, string> = {
  h_poster: "Horizontal poster",
  still_frame: "Still frame",
  v_poster: "Vertical poster",
  logo: "Logo",
  hero_image: "Hero image",
  hero_image_vertical: "Hero image vertical",
  box_art: "Box art",
};

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

function uriBasename(uri: string): string {
  return uri.split("?")[0].replace(/\/+$/, "").split("/").pop() ?? uri;
}

function metadataArtworkLabels(raw?: string | null): Map<string, string[]> {
  const byFilename = new Map<string, string[]>();
  if (!raw) return byFilename;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    for (const [key, label] of Object.entries(CORE_ARTWORK_LABELS)) {
      const value = parsed[key];
      if (typeof value !== "string" || !value.trim()) continue;
      const filename = value.trim().split("/").pop() ?? value.trim();
      const labels = byFilename.get(filename) ?? [];
      if (!labels.includes(label)) labels.push(label);
      byFilename.set(filename, labels);
    }
  } catch {
    return byFilename;
  }
  return byFilename;
}

function filterToMetadataArtwork(
  items: ArtworkItem[],
  metadataJson?: string | null
): ArtworkItem[] {
  const labelsByFilename = metadataArtworkLabels(metadataJson);
  if (labelsByFilename.size === 0) return items;
  const selected = new Map<string, ArtworkItem>();
  for (const item of items) {
    const labels = labelsByFilename.get(uriBasename(item.storage_uri));
    if (!labels || selected.has(item.storage_uri)) continue;
    const label = preferredArtworkLabel(item, labels);
    selected.set(item.storage_uri, {
      ...item,
      asset_type: "poster",
      notes: `source:tmdb; ${label}${item.language && item.language !== "en" ? `; lang:${item.language}` : ""}`,
      specs: {
        ...(item.specs ?? {}),
        label,
      },
    });
  }
  return [...selected.values()];
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

export function ArtworkTab({
  titleId,
  externalId,
  metadataJson,
  visible = true,
  onSaved,
}: ArtworkTabProps) {
  const [saved, setSaved] = useState<MediaAsset[]>([]);
  const [candidates, setCandidates] = useState<ArtworkItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const canFetch = Boolean(externalId?.startsWith("tmdb:"));

  const savedArtworkItems: DisplayItem[] = useMemo(
    () => saved.map((a) => ({ ...assetToArtworkItem(a), catalogId: a.id })),
    [saved]
  );

  const savedItems: DisplayItem[] = useMemo(
    () => filterToMetadataArtwork(savedArtworkItems, metadataJson),
    [metadataJson, savedArtworkItems]
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

  const loadSaved = useCallback(async () => {
    if (!titleId) {
      setSaved([]);
      return [];
    }
    setCatalogLoading(true);
    setError(null);
    try {
      const list = await titlesApi.listArtwork(titleId);
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
      const stored = await titlesApi.saveArtwork(titleId, items);
      const artworkOnly = filterArtworkAssets(stored);
      setSaved(artworkOnly);
      setSelected(new Set());
      setSuccess(
        `Added ${items.length} artwork asset${items.length === 1 ? "" : "s"} to the catalog.`
      );
      onSaved?.();
      await loadSaved();
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
      <header className="artwork-header">
        <div className="artwork-header-text">
          <h3 className="artwork-title">Artwork library</h3>
          <p className="artwork-subtitle">
            Saved artwork loads from this title when the modal opens. Use Browse TMDB
            to fetch metadata-matched artwork candidates.
          </p>
        </div>
      </header>

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

      {error && <div className="error-banner artwork-error">{error}</div>}
      {success && !error && (
        <div className="metadata-applied-banner artwork-success">{success}</div>
      )}

      <div className="artwork-view-section">
        <h3 className="artwork-view-heading">In your catalog</h3>
        {!titleId ? (
          <p className="artwork-view-empty">
            Save the title on the Details tab first, then return here to store artwork.
          </p>
        ) : catalogLoading ? (
          <div className="artwork-state">
            <div className="artwork-spinner" aria-hidden />
            <p>Loading catalog artwork…</p>
          </div>
        ) : savedItems.length === 0 ? (
          <p className="artwork-view-empty">
            No artwork saved yet. Fetch from TMDB below, then add selected images.
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
        <div className="artwork-browse-header">
          <div>
            <h3 className="artwork-view-heading">Browse TMDB</h3>
            <p className="artwork-view-empty artwork-view-empty-inline">
              Fetch all available posters, hero images, stills, logos, and box art from TMDB.
              Fetching does not change saved catalog artwork.
            </p>
          </div>
          {canFetch && (
            <button
              type="button"
              className="btn btn-primary artwork-fetch-btn"
              disabled={fetching || saving}
              onClick={handleFetch}
            >
              {fetching ? "Fetching…" : "Fetch artwork"}
            </button>
          )}
        </div>
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
            Click Fetch artwork to browse all TMDB posters, backdrops, logos, and more.
            Fetching does not save anything until you add selected images.
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
                disabled={selectedNewCount === 0 || saving || !titleId}
                onClick={handleSaveSelected}
              >
                {saving
                  ? "Saving…"
                  : titleId
                    ? `Add selected to catalog (${selectedNewCount})`
                    : "Save title first"}
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
    </div>
  );
}
