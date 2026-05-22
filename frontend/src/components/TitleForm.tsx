import { useEffect, useState } from "react";
import { ArtworkTab } from "./ArtworkTab";
import { MetadataLookup } from "./MetadataLookup";
import type {
  Title,
  TitleMetadataImport,
  TitleStatus,
  TitleType,
} from "../types";

interface TitleFormProps {
  initial?: Partial<Title>;
  titleId?: number;
  parents?: Title[];
  isCreate?: boolean;
  initialTab?: "details" | "artwork";
  onSubmit: (data: Partial<Title>) => Promise<Title | void>;
  onCancel: () => void;
  onArtworkSaved?: () => void;
}

const TYPES: TitleType[] = ["movie", "series", "season", "episode"];
const STATUSES: TitleStatus[] = [
  "draft",
  "in_review",
  "scheduled",
  "published",
  "archived",
];

const emptyForm = (initial?: Partial<Title>) => ({
  slug: initial?.slug ?? "",
  name: initial?.name ?? "",
  title_type: initial?.title_type ?? "movie",
  status: initial?.status ?? "draft",
  synopsis: initial?.synopsis ?? "",
  short_description: initial?.short_description ?? "",
  genres: initial?.genres ?? "",
  rating: initial?.rating ?? "",
  release_date: initial?.release_date ?? "",
  release_year: initial?.release_year?.toString() ?? "",
  licensor: initial?.licensor ?? "",
  studio: initial?.studio ?? "",
  cast: initial?.cast ?? "",
  crew: initial?.crew ?? "",
  external_id: initial?.external_id ?? "",
  metadata_source: initial?.metadata_source ?? "",
  poster_url: initial?.poster_url ?? "",
  parent_id: initial?.parent_id?.toString() ?? "",
  season_number: initial?.season_number?.toString() ?? "",
  episode_number: initial?.episode_number?.toString() ?? "",
  runtime_minutes: initial?.runtime_minutes?.toString() ?? "",
});

export function TitleForm({
  initial,
  titleId,
  parents = [],
  isCreate = false,
  initialTab = "details",
  onSubmit,
  onCancel,
  onArtworkSaved,
}: TitleFormProps) {
  const [tab, setTab] = useState<"details" | "artwork">(initialTab);
  const [form, setForm] = useState(emptyForm(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metadataApplied, setMetadataApplied] = useState(false);
  const [savedTitleId, setSavedTitleId] = useState<number | undefined>(titleId);

  useEffect(() => {
    setTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    setSavedTitleId(titleId);
  }, [titleId]);

  useEffect(() => {
    setForm(emptyForm(initial));
    setError(null);
    setMetadataApplied(false);
  }, [initial?.id, isCreate]);

  const set = (key: string, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const applyMetadata = (meta: TitleMetadataImport) => {
    setForm((f) => ({
      ...f,
      name: meta.name,
      slug: meta.slug ?? f.slug,
      title_type: meta.title_type,
      synopsis: meta.synopsis ?? "",
      short_description: meta.short_description ?? "",
      genres: meta.genres ?? "",
      rating: meta.rating ?? "",
      release_date: meta.release_date ?? "",
      release_year: meta.release_year?.toString() ?? "",
      runtime_minutes: meta.runtime_minutes?.toString() ?? "",
      studio: meta.studio ?? "",
      licensor: meta.licensor ?? f.licensor,
      cast: meta.cast ?? "",
      crew: meta.crew ?? "",
      external_id: meta.external_id,
      metadata_source: meta.source,
      poster_url: meta.poster_url ?? "",
    }));
    setMetadataApplied(true);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Name is required — switch to the Details tab to fill it in.");
      setTab("details");
      return;
    }
    if (!form.slug.trim()) {
      setError("Slug is required — switch to the Details tab to fill it in.");
      setTab("details");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: Partial<Title> = {
        slug: form.slug,
        name: form.name,
        title_type: form.title_type as TitleType,
        status: form.status as TitleStatus,
        synopsis: form.synopsis || null,
        short_description: form.short_description || null,
        genres: form.genres || null,
        rating: form.rating || null,
        release_date: form.release_date || null,
        release_year: form.release_year ? Number(form.release_year) : null,
        licensor: form.licensor || null,
        studio: form.studio || null,
        cast: form.cast || null,
        crew: form.crew || null,
        external_id: form.external_id || null,
        metadata_source: form.metadata_source || null,
        poster_url: form.poster_url || null,
        parent_id: form.parent_id ? Number(form.parent_id) : null,
        season_number: form.season_number ? Number(form.season_number) : null,
        episode_number: form.episode_number ? Number(form.episode_number) : null,
        runtime_minutes: form.runtime_minutes
          ? Number(form.runtime_minutes)
          : null,
      };
      const result = await onSubmit(payload);
      if (result?.id) {
        setSavedTitleId(result.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const activeTitleId = savedTitleId ?? titleId;

  return (
    <form onSubmit={handleSubmit} noValidate>
      {error && <div className="error-banner">{error}</div>}
      <div className="title-tabs">
        <button
          type="button"
          className={`title-tab ${tab === "details" ? "active" : ""}`}
          onClick={() => setTab("details")}
        >
          Details
        </button>
        <button
          type="button"
          className={`title-tab ${tab === "artwork" ? "active" : ""}`}
          onClick={() => setTab("artwork")}
        >
          Artwork
        </button>
      </div>

      {tab === "details" && (
        <>
          {isCreate && <MetadataLookup onApply={applyMetadata} />}
          {metadataApplied && (
            <div className="metadata-applied-banner">
              Metadata imported — review fields below, add licensor if needed, then save.
              Fetch artwork separately on the Artwork tab.
            </div>
          )}
          <div className="form-grid">
            <label>
              Name
              <input required value={form.name} onChange={(e) => set("name", e.target.value)} />
            </label>
            <label>
              Slug
              <input required value={form.slug} onChange={(e) => set("slug", e.target.value)} />
            </label>
            <label>
              Type
              <select
                value={form.title_type}
                onChange={(e) => set("title_type", e.target.value)}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Status
              <select value={form.status} onChange={(e) => set("status", e.target.value)}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Release year
              <input
                type="number"
                value={form.release_year}
                onChange={(e) => set("release_year", e.target.value)}
              />
            </label>
            <label>
              Release date
              <input
                type="date"
                value={form.release_date}
                onChange={(e) => set("release_date", e.target.value)}
              />
            </label>
            <label>
              Genres
              <input value={form.genres} onChange={(e) => set("genres", e.target.value)} />
            </label>
            <label>
              Content rating
              <input value={form.rating} onChange={(e) => set("rating", e.target.value)} />
            </label>
            <label>
              Studio
              <input value={form.studio} onChange={(e) => set("studio", e.target.value)} />
            </label>
            <label>
              Licensor
              <input
                value={form.licensor}
                onChange={(e) => set("licensor", e.target.value)}
                placeholder="Your distribution / rights holder"
              />
            </label>
            <label>
              Runtime (minutes)
              <input
                type="number"
                value={form.runtime_minutes}
                onChange={(e) => set("runtime_minutes", e.target.value)}
              />
            </label>
            <label>
              Parent title
              <select
                value={form.parent_id}
                onChange={(e) => set("parent_id", e.target.value)}
              >
                <option value="">— None —</option>
                {parents.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.title_type})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Season #
              <input
                type="number"
                value={form.season_number}
                onChange={(e) => set("season_number", e.target.value)}
              />
            </label>
            <label>
              Episode #
              <input
                type="number"
                value={form.episode_number}
                onChange={(e) => set("episode_number", e.target.value)}
              />
            </label>
            <label className="form-span-2">
              Tagline / short description
              <input
                value={form.short_description}
                onChange={(e) => set("short_description", e.target.value)}
              />
            </label>
            <label className="form-span-2">
              Synopsis
              <textarea value={form.synopsis} onChange={(e) => set("synopsis", e.target.value)} />
            </label>
            <label className="form-span-2">
              Cast
              <textarea
                value={form.cast}
                onChange={(e) => set("cast", e.target.value)}
                rows={3}
              />
            </label>
            <label className="form-span-2">
              Crew
              <textarea
                value={form.crew}
                onChange={(e) => set("crew", e.target.value)}
                rows={2}
              />
            </label>
          </div>
        </>
      )}

      {tab === "artwork" && (
        <ArtworkTab
          key={activeTitleId ?? "new"}
          titleId={activeTitleId}
          externalId={form.external_id}
          onSaved={onArtworkSaved}
        />
      )}

      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save title"}
        </button>
      </div>
    </form>
  );
}
