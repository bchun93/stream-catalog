import { useState } from "react";
import { metadataApi } from "../api/client";
import type { MetadataSearchResult, TitleMetadataImport } from "../types";

interface MetadataLookupProps {
  onApply: (metadata: TitleMetadataImport) => void;
}

export function MetadataLookup({ onApply }: MetadataLookupProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MetadataSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      // Always search movies + TV; many titles (e.g. House of David) are series.
      const data = await metadataApi.search(query.trim());
      setResults(data);
      if (data.length === 0) {
        setError("No matches found. Try a different title or type.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (item: MetadataSearchResult) => {
    setImporting(item.external_id);
    setError(null);
    try {
      const meta = await metadataApi.import(item.external_id);
      let artwork = meta.artwork ?? [];
      try {
        artwork = await metadataApi.importArtwork(item.external_id);
      } catch {
        setError(
          "Metadata imported, but artwork failed to load. Save the title and use Refresh from TMDB on the Artwork tab."
        );
      }
      onApply({ ...meta, artwork });
      if (artwork.length > 0) {
        setError(null);
      }
      setResults([]);
      setQuery("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(null);
    }
  };

  return (
    <div className="metadata-lookup">
      <div className="metadata-lookup-header">
        <strong>Import metadata</strong>
        <span className="metadata-hint">Powered by TMDB — genre, cast, synopsis, and more</span>
      </div>
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
      {results.length > 0 && (
        <ul className="metadata-results">
          {results.map((item) => (
            <li key={item.external_id}>
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
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
