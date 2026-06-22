import { useEffect, useMemo, useState } from "react";
import { metadataConfigApi } from "../api/client";
import { ArtworkTab } from "./ArtworkTab";
import { MetadataLookup } from "./MetadataLookup";
import type {
  MetadataDisplaySettings,
  Title,
  TitleMetadataImport,
  TitleStatus,
  TitleType,
} from "../types";
import {
  CORE_METADATA_FIELDS,
  parseCoreMetadata,
  stringifyCoreMetadata,
} from "../utils/metadataRequirements";

interface TitleFormProps {
  initial?: Partial<Title>;
  titleId?: number;
  parents?: Title[];
  isCreate?: boolean;
  initialTab?: "details" | "artwork";
  formId?: string;
  hideActions?: boolean;
  onSavingChange?: (saving: boolean) => void;
  onSubmit: (data: Partial<Title>) => Promise<Title | void>;
  onCancel: () => void;
  /** Called after title details save succeeds (e.g. refresh list). */
  onSaved?: () => void;
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

function toIsoDate(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  const mmddyyyy = /^(\d{2})\/(\d{2})\/(\d{4})$/;
  const m = text.match(mmddyyyy);
  if (!m) return null;
  const [, mm, dd, yyyy] = m;
  return `${yyyy}-${mm}-${dd}`;
}

function metadataImportToCore(meta: TitleMetadataImport): Record<string, string> {
  const fromPayload: Record<string, string> = {};
  for (const [key, value] of Object.entries(meta.core_metadata ?? {})) {
    if (typeof value === "string" && value.trim()) fromPayload[key] = value;
  }
  if (Object.keys(fromPayload).length > 0) return fromPayload;

  const fallback: Record<string, string> = {};
  if (meta.media_type === "movie") fallback.content_type = "movie";
  if (meta.media_type === "tv") fallback.content_type = "series";
  if (meta.name) fallback.name = meta.name;
  if (meta.synopsis) fallback.synopsis = meta.synopsis;
  if (meta.short_description) fallback.short_synopsis = meta.short_description;
  if (meta.rating) fallback.rating = meta.rating;
  if (meta.release_date) {
    const asDate = new Date(meta.release_date);
    if (!Number.isNaN(asDate.getTime())) {
      const mm = String(asDate.getMonth() + 1).padStart(2, "0");
      const dd = String(asDate.getDate()).padStart(2, "0");
      const yyyy = String(asDate.getFullYear());
      fallback.release_date = `${mm}/${dd}/${yyyy}`;
    }
  }
  if (meta.release_year != null) fallback.latest_release_year = String(meta.release_year);
  if (meta.runtime_minutes != null) fallback.runtime = String(meta.runtime_minutes);
  if (meta.studio) fallback.studio = meta.studio.replace(/,\s*/g, "\n");
  if (meta.genres) fallback.genre = meta.genres.replace(/,\s*/g, "\n");
  if (meta.cast) fallback.actors = meta.cast.replace(/;\s*/g, "\n");
  if (meta.crew) fallback.producers = meta.crew.replace(/;\s*/g, "\n");
  return fallback;
}

function stripEpisodeHierarchyPrefix(name: string): string {
  const marker = ": Episode ";
  if (!name.includes(marker)) return name;
  const tail = name.split(marker)[1] ?? name;
  return tail.replace(/^\d+: /, "");
}

function allowedParentType(titleType: string): TitleType | null {
  if (titleType === "season") return "series";
  if (titleType === "episode") return "season";
  return null;
}

const emptyForm = (initial?: Partial<Title>) => ({
  internal_id: initial?.internal_id ?? "",
  slug: initial?.slug ?? "",
  name:
    initial?.title_type === "episode"
      ? stripEpisodeHierarchyPrefix(initial?.name ?? "")
      : initial?.name ?? "",
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
  eidr: initial?.eidr ?? "",
  external_id: initial?.external_id ?? "",
  metadata_source: initial?.metadata_source ?? "",
  poster_url: initial?.poster_url ?? "",
  parent_id: initial?.parent_id?.toString() ?? "",
  season_number: initial?.season_number?.toString() ?? "",
  episode_number: initial?.episode_number?.toString() ?? "",
  runtime_minutes: initial?.runtime_minutes?.toString() ?? "",
  core_metadata: parseCoreMetadata(initial?.metadata_json),
});

export function TitleForm({
  initial,
  titleId,
  parents = [],
  isCreate = false,
  initialTab = "details",
  formId = "title-form",
  hideActions = false,
  onSavingChange,
  onSubmit,
  onCancel,
  onSaved,
  onArtworkSaved,
}: TitleFormProps) {
  const [tab, setTab] = useState<"details" | "artwork">(initialTab);
  const [form, setForm] = useState(emptyForm(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metadataApplied, setMetadataApplied] = useState(false);
  const [metadataSettings, setMetadataSettings] = useState<MetadataDisplaySettings | null>(null);
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

  useEffect(() => {
    metadataConfigApi
      .get()
      .then((config) => setMetadataSettings(config.settings))
      .catch(() => setMetadataSettings(null));
  }, []);

  const parentType = allowedParentType(form.title_type);
  const parentOptions = useMemo(
    () => (parentType ? parents.filter((parent) => parent.title_type === parentType) : []),
    [parents, parentType]
  );
  const visibleCoreMetadataFields = useMemo(() => {
    const configuredKeys = metadataSettings?.[form.title_type as TitleType];
    if (!configuredKeys) return CORE_METADATA_FIELDS;
    const selected = new Set(configuredKeys);
    return CORE_METADATA_FIELDS.filter((field) => selected.has(field.key));
  }, [metadataSettings, form.title_type]);

  useEffect(() => {
    if (!form.parent_id) return;
    if (parentOptions.some((parent) => String(parent.id) === form.parent_id)) return;
    setForm((f) => ({ ...f, parent_id: "" }));
  }, [form.parent_id, parentOptions]);

  const set = (key: string, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));
  const setCoreMetadata = (key: string, value: string) =>
    setForm((f) => ({
      ...f,
      core_metadata: { ...f.core_metadata, [key]: value },
    }));

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
      core_metadata: {
        ...f.core_metadata,
        ...metadataImportToCore(meta),
      },
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
    onSavingChange?.(true);
    setError(null);
    try {
      const payload: Partial<Title> = {
        slug: form.slug,
        name: form.name,
        title_type: form.title_type as TitleType,
        status: form.status as TitleStatus,
        synopsis: (form.core_metadata["synopsis"] || form.synopsis) || null,
        short_description:
          (form.core_metadata["short_synopsis"] || form.short_description) || null,
        genres: (form.core_metadata["genre"] || form.genres) || null,
        rating: (form.core_metadata["rating"] || form.rating) || null,
        release_date: form.core_metadata["release_date"]
          ? toIsoDate(form.core_metadata["release_date"])
          : form.release_date || null,
        release_year: form.release_year
          ? Number(form.release_year)
          : form.core_metadata["latest_release_year"]
            ? Number(form.core_metadata["latest_release_year"])
            : null,
        licensor: form.licensor || null,
        studio: (form.core_metadata["studio"] || form.studio) || null,
        cast: (form.core_metadata["actors"] || form.cast) || null,
        crew:
          [
            form.core_metadata["directors"],
            form.core_metadata["writers"],
            form.core_metadata["producers"],
            form.crew,
          ]
            .filter(Boolean)
            .join("\n") || null,
        eidr: form.eidr || null,
        external_id: form.external_id || null,
        metadata_source: form.metadata_source || null,
        poster_url: form.poster_url || null,
        parent_id: form.parent_id ? Number(form.parent_id) : null,
        season_number: form.season_number ? Number(form.season_number) : null,
        episode_number: form.episode_number ? Number(form.episode_number) : null,
        runtime_minutes: form.runtime_minutes
          ? Number(form.runtime_minutes)
          : form.core_metadata["runtime"]
            ? Number(form.core_metadata["runtime"])
            : null,
        metadata_json: stringifyCoreMetadata(form.core_metadata),
      };
      const result = await onSubmit(payload);
      if (result?.id) {
        setSavedTitleId(result.id);
      }
      onSaved?.();
      onCancel();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
      onSavingChange?.(false);
    }
  };

  const activeTitleId = savedTitleId ?? titleId;

  return (
    <form id={formId} onSubmit={handleSubmit} noValidate>
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
          {(isCreate || !form.external_id?.startsWith("tmdb:")) && (
            <section className="form-section form-section-hero">
              <h3 className="form-section-title">Import metadata</h3>
              <p className="form-section-desc">
                Search TMDB to pre-fill fields and sync artwork into the title library.
              </p>
              <MetadataLookup
                onApply={applyMetadata}
                onHierarchyApplied={() => {
                  onSaved?.();
                  onCancel();
                }}
              />
            </section>
          )}
          {metadataApplied && (
            <div className="metadata-applied-banner">
              Metadata imported — review the fields below and save.
            </div>
          )}
          <section className="form-section">
            <h3 className="form-section-title">Identification</h3>
            <p className="form-section-desc">
              Internal ID is assigned by the catalog and stays with this title.
            </p>
            <div className="form-grid">
            <label className="field-readonly">
              Internal ID
              <input
                value={form.internal_id || "Assigned when saved"}
                readOnly
                aria-readonly="true"
              />
            </label>
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
              EIDR
              <input
                value={form.eidr}
                onChange={(e) => set("eidr", e.target.value)}
                placeholder="10.5240/XXXX-XXXX-XXXX-XXXX-XXXX-C"
              />
            </label>
            <label>
              Parent title
              <select
                value={form.parent_id}
                onChange={(e) => set("parent_id", e.target.value)}
                disabled={!parentType}
              >
                <option value="">
                  {parentType ? `— Select ${parentType} —` : "— No parent —"}
                </option>
                {parentOptions.map((p) => (
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
            </div>
          </section>
          <section className="form-section">
            <h3 className="form-section-title">Core metadata</h3>
            <p className="form-section-desc">
              TMDB import maps matching fields automatically; unmatched fields remain blank.
            </p>
            <div className="form-grid">
                {visibleCoreMetadataFields.map((field) => (
                  <label key={field.key} className={field.multiline ? "form-span-2" : undefined}>
                    {field.label}
                    {field.multiline ? (
                      <textarea
                        rows={2}
                        value={form.core_metadata[field.key] ?? ""}
                        onChange={(e) => setCoreMetadata(field.key, e.target.value)}
                      />
                    ) : (
                      <input
                        value={form.core_metadata[field.key] ?? ""}
                        onChange={(e) => setCoreMetadata(field.key, e.target.value)}
                      />
                    )}
                  </label>
                ))}
                {visibleCoreMetadataFields.length === 0 && (
                  <p className="empty form-span-2">
                    No core metadata fields are configured for this content type.
                  </p>
                )}
            </div>
          </section>
        </>
      )}

      {activeTitleId ? (
        <ArtworkTab
          key={activeTitleId}
          titleId={activeTitleId}
          externalId={form.external_id || null}
          metadataJson={stringifyCoreMetadata(form.core_metadata)}
          visible={tab === "artwork"}
          onSaved={onArtworkSaved}
        />
      ) : (
        tab === "artwork" && (
          <ArtworkTab
            key="new"
            externalId={form.external_id || null}
            metadataJson={stringifyCoreMetadata(form.core_metadata)}
            visible
            onSaved={onArtworkSaved}
          />
        )
      )}

      {!hideActions && (
        <div className="form-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "Saving…" : "Save title"}
          </button>
        </div>
      )}
    </form>
  );
}
