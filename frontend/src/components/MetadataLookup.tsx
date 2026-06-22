import { useEffect, useState } from "react";
import { metadataApi } from "../api/client";
import type {
  MetadataSearchResult,
  SeriesHierarchyPreview,
  TitleMetadataImport,
} from "../types";

interface MetadataLookupProps {
  onApply: (metadata: TitleMetadataImport) => void;
  onHierarchyApplied?: () => void;
}

export function MetadataLookup({ onApply, onHierarchyApplied }: MetadataLookupProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MetadataSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState<string | null>(null);
  const [applyingHierarchy, setApplyingHierarchy] = useState(false);
  const [hierarchyPreview, setHierarchyPreview] = useState<SeriesHierarchyPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    metadataApi
      .health()
      .then((health) => {
        if (!health.ok) setError(health.message);
      })
      .catch(() => {
        /* search will surface API errors */
      });
  }, []);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    setResults([]);
    setHierarchyPreview(null);
    try {
      const data = await metadataApi.search(query.trim());
      setResults(data);
      if (data.length === 0) {
        setError("No matches found. Try a different title or type.");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Search failed";
      setError(msg);
      try {
        const health = await metadataApi.health();
        if (!health.ok) setError(health.message);
      } catch {
        /* keep search error */
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (item: MetadataSearchResult) => {
    setImporting(item.external_id);
    setError(null);
    setNotice(null);
    try {
      const meta = await metadataApi.import(item.external_id);
      onApply({ ...meta, artwork: [] });
      setResults([]);
      setQuery("");
      setHierarchyPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(null);
    }
  };

  const handlePreviewHierarchy = async (item: MetadataSearchResult) => {
    setPreviewing(item.external_id);
    setError(null);
    setNotice(null);
    setHierarchyPreview(null);
    try {
      const preview = await metadataApi.hierarchyPreview(item.external_id);
      setHierarchyPreview(preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not preview hierarchy");
    } finally {
      setPreviewing(null);
    }
  };

  const handleApplyHierarchy = async () => {
    if (!hierarchyPreview) return;
    setApplyingHierarchy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await metadataApi.applyHierarchy(hierarchyPreview.external_id);
      setHierarchyPreview(null);
      setResults([]);
      setQuery("");
      setNotice(
        `Imported hierarchy for ${result.series.name}: ${result.season_count} seasons, ${result.episode_count} episodes (${result.created_count} created, ${result.updated_count} updated).`
      );
      onHierarchyApplied?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not import hierarchy");
    } finally {
      setApplyingHierarchy(false);
    }
  };

  return (
    <div className="metadata-lookup">
      <div className="metadata-search-row">
        <input
          placeholder="Search by title name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleSearch())}
        />
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSearch}
          disabled={loading || !query.trim()}
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </div>
      {error && <div className="error-banner metadata-error">{error}</div>}
      {notice && <div className="metadata-applied-banner metadata-notice">{notice}</div>}
      {hierarchyPreview && (
        <div className="hierarchy-preview">
          <div>
            <strong>{hierarchyPreview.name}</strong>
            <p>
              Preview: {hierarchyPreview.season_count} seasons and{" "}
              {hierarchyPreview.episode_count} episodes.{" "}
              {hierarchyPreview.action === "update"
                ? "Existing series will be updated."
                : "A new series hierarchy will be created."}
            </p>
          </div>
          <ul>
            {hierarchyPreview.seasons.slice(0, 6).map((season) => (
              <li key={season.external_id}>
                {season.name}: {season.episode_count} episodes
              </li>
            ))}
            {hierarchyPreview.seasons.length > 6 && (
              <li>+ {hierarchyPreview.seasons.length - 6} more seasons</li>
            )}
          </ul>
          <div className="hierarchy-preview-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={applyingHierarchy}
              onClick={handleApplyHierarchy}
            >
              {applyingHierarchy ? "Importing…" : "Create / update hierarchy"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={applyingHierarchy}
              onClick={() => setHierarchyPreview(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {results.length > 0 && (
        <ul className="metadata-results">
          {results.map((item) => (
            <li key={item.external_id}>
              <div className="metadata-result-row">
                <button
                  type="button"
                  className="metadata-result-btn"
                  onClick={() => handleSelect(item)}
                  disabled={importing === item.external_id}
                >
                  {item.poster_url ? (
                    <img src={item.poster_url} alt="" className="metadata-poster" />
                  ) : (
                    <div className="metadata-poster metadata-poster-empty">?</div>
                  )}
                  <span className="metadata-result-text">
                    <span className="metadata-result-title">{item.name}</span>
                    <span className="metadata-result-meta">
                      {item.title_type}
                      {item.release_year ? ` · ${item.release_year}` : ""}
                    </span>
                    {item.overview && (
                      <span className="metadata-result-overview">{item.overview}</span>
                    )}
                  </span>
                </button>
                {item.title_type === "series" && (
                  <button
                    type="button"
                    className="btn btn-ghost metadata-hierarchy-btn"
                    onClick={() => handlePreviewHierarchy(item)}
                    disabled={previewing === item.external_id}
                  >
                    {previewing === item.external_id ? "Previewing…" : "Preview hierarchy"}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
