import { useEffect, useMemo, useState } from "react";
import { Play, Plus, X } from "lucide-react";
import { titlesApi } from "../api/client";
import type { MediaAsset, Title } from "../types";
import { Button } from "./ui/Button";

function splitList(value?: string | null): string[] {
  if (!value?.trim()) return [];
  return value
    .split(/[\n,;|]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function formatRuntime(minutes?: number | null): string | null {
  if (minutes == null || minutes <= 0) return null;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h <= 0) return `${m}m`;
  if (m <= 0) return `${h}h`;
  return `${h}h ${m}m`;
}

function formatAvailability(title: Title): string | null {
  const start = title.availability_start;
  const end = title.availability_end;
  if (!start && !end) return null;
  if (start && end) return `Available ${start} – ${end}`;
  if (start) return `Available from ${start}`;
  return `Available until ${end}`;
}

function hierarchyLabel(title: Title): string | null {
  if (title.title_type === "season") {
    return title.season_number === 0
      ? "Specials"
      : `Season ${title.season_number ?? "—"}`;
  }
  if (title.title_type === "episode") {
    const season =
      title.season_number != null ? `S${title.season_number}` : null;
    const episode =
      title.episode_number != null ? `E${title.episode_number}` : null;
    return [season, episode].filter(Boolean).join(" · ") || "Episode";
  }
  return null;
}

function pickArtwork(assets: MediaAsset[]) {
  const byType = (type: string) =>
    assets.find((a) => a.asset_type === type)?.storage_uri ?? null;
  return {
    backdrop: byType("backdrop") ?? byType("still") ?? null,
    poster: byType("poster") ?? byType("season_poster") ?? byType("thumbnail") ?? null,
    logo: byType("logo") ?? null,
  };
}

interface TitlePreviewOverlayProps {
  titleId: number;
  onClose: () => void;
}

export function TitlePreviewOverlay({ titleId, onClose }: TitlePreviewOverlayProps) {
  const [title, setTitle] = useState<Title | null>(null);
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([titlesApi.get(titleId), titlesApi.listArtwork(titleId)])
      .then(([full, artwork]) => {
        if (cancelled) return;
        setTitle(full);
        setAssets(artwork);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load preview");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [titleId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("title-preview-open");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("title-preview-open");
    };
  }, [onClose]);

  const art = useMemo(() => pickArtwork(assets), [assets]);
  const genres = useMemo(() => splitList(title?.genres), [title?.genres]);
  const cast = useMemo(() => splitList(title?.cast).slice(0, 8), [title?.cast]);
  const heroUrl = art.backdrop ?? art.poster ?? title?.poster_url ?? null;
  const posterUrl = art.poster ?? title?.poster_url ?? null;
  const runtime = title ? formatRuntime(title.runtime_minutes) : null;
  const availability = title ? formatAvailability(title) : null;
  const hierarchy = title ? hierarchyLabel(title) : null;
  const blurb = title?.short_description || title?.synopsis || null;

  const metaBits = [
    title?.release_year != null ? String(title.release_year) : null,
    title?.rating || null,
    runtime,
    title?.title_type
      ? title.title_type.charAt(0).toUpperCase() + title.title_type.slice(1)
      : null,
  ].filter(Boolean) as string[];

  return (
    <div className="title-preview-backdrop" role="presentation" onClick={onClose}>
      <div
        className="title-preview-shell"
        role="dialog"
        aria-modal="true"
        aria-labelledby="title-preview-heading"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="title-preview-chrome">
          <div className="title-preview-chrome-text">
            <span className="title-preview-chrome-eyebrow">Preview mode</span>
            <p>Streaming service info page mockup — playback decision fields only.</p>
          </div>
          <Button
            variant="subtle"
            className="title-preview-close"
            onClick={onClose}
            aria-label="Close preview"
            icon={<X size={18} />}
          />
        </header>

        {loading ? (
          <div className="title-preview-state">Loading title preview…</div>
        ) : error ? (
          <div className="title-preview-state title-preview-state-error">{error}</div>
        ) : title ? (
          <div className="title-preview-stage">
            <div
              className="title-preview-hero"
              style={
                heroUrl
                  ? { backgroundImage: `url(${heroUrl})` }
                  : undefined
              }
            >
              <div className="title-preview-hero-shade" aria-hidden />
              <div className="title-preview-hero-content">
                <div className="title-preview-hero-copy">
                  {hierarchy ? (
                    <p className="title-preview-hierarchy">{hierarchy}</p>
                  ) : null}
                  {art.logo ? (
                    <img
                      className="title-preview-logo"
                      src={art.logo}
                      alt=""
                    />
                  ) : null}
                  <h2 id="title-preview-heading" className="title-preview-title">
                    {title.name}
                  </h2>
                  {metaBits.length > 0 ? (
                    <p className="title-preview-meta">
                      {metaBits.map((bit, i) => (
                        <span key={`${bit}-${i}`}>
                          {i > 0 ? <span aria-hidden> · </span> : null}
                          {bit}
                        </span>
                      ))}
                    </p>
                  ) : (
                    <p className="title-preview-meta title-preview-missing">
                      Year, rating, and runtime not set
                    </p>
                  )}
                  {genres.length > 0 ? (
                    <ul className="title-preview-genres">
                      {genres.slice(0, 6).map((g) => (
                        <li key={g}>{g}</li>
                      ))}
                    </ul>
                  ) : null}
                  <p
                    className={
                      blurb
                        ? "title-preview-blurb"
                        : "title-preview-blurb title-preview-missing"
                    }
                  >
                    {blurb || "No short description or synopsis yet."}
                  </p>
                  <div className="title-preview-ctas" aria-hidden>
                    <button type="button" className="title-preview-play" disabled>
                      <Play size={18} fill="currentColor" aria-hidden />
                      Play
                    </button>
                    <button type="button" className="title-preview-list" disabled>
                      <Plus size={18} aria-hidden />
                      My List
                    </button>
                  </div>
                  {availability ? (
                    <p className="title-preview-availability">{availability}</p>
                  ) : null}
                </div>
                <aside className="title-preview-poster-panel">
                  {posterUrl ? (
                    <img src={posterUrl} alt="" className="title-preview-poster" />
                  ) : (
                    <div className="title-preview-poster title-preview-poster-empty">
                      No poster
                    </div>
                  )}
                </aside>
              </div>
            </div>

            <section className="title-preview-details">
              <div className="title-preview-detail-block">
                <h3>Synopsis</h3>
                <p className={title.synopsis ? undefined : "title-preview-missing"}>
                  {title.synopsis || "No synopsis provided."}
                </p>
              </div>
              <div className="title-preview-detail-grid">
                <div className="title-preview-detail-block">
                  <h3>Cast</h3>
                  {cast.length > 0 ? (
                    <ul className="title-preview-cast">
                      {cast.map((name) => (
                        <li key={name}>{name}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="title-preview-missing">No cast listed.</p>
                  )}
                </div>
                <div className="title-preview-detail-block">
                  <h3>Studio</h3>
                  <p className={title.studio ? undefined : "title-preview-missing"}>
                    {title.studio
                      ? splitList(title.studio).join(", ")
                      : "No studio listed."}
                  </p>
                </div>
                <div className="title-preview-detail-block">
                  <h3>Territories</h3>
                  <p className={title.territories ? undefined : "title-preview-missing"}>
                    {title.territories
                      ? splitList(title.territories).join(", ")
                      : "No territories listed."}
                  </p>
                </div>
              </div>
            </section>
          </div>
        ) : null}
      </div>
    </div>
  );
}
