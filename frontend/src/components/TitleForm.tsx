import { useState } from "react";
import type { Title, TitleStatus, TitleType } from "../types";

interface TitleFormProps {
  initial?: Partial<Title>;
  parents?: Title[];
  onSubmit: (data: Partial<Title>) => Promise<void>;
  onCancel: () => void;
}

const TYPES: TitleType[] = ["movie", "series", "season", "episode"];
const STATUSES: TitleStatus[] = [
  "draft",
  "in_review",
  "scheduled",
  "published",
  "archived",
];

export function TitleForm({ initial, parents = [], onSubmit, onCancel }: TitleFormProps) {
  const [form, setForm] = useState({
    slug: initial?.slug ?? "",
    name: initial?.name ?? "",
    title_type: initial?.title_type ?? "movie",
    status: initial?.status ?? "draft",
    synopsis: initial?.synopsis ?? "",
    genres: initial?.genres ?? "",
    rating: initial?.rating ?? "",
    parent_id: initial?.parent_id?.toString() ?? "",
    season_number: initial?.season_number?.toString() ?? "",
    episode_number: initial?.episode_number?.toString() ?? "",
    runtime_minutes: initial?.runtime_minutes?.toString() ?? "",
    release_date: initial?.release_date ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (key: string, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        slug: form.slug,
        name: form.name,
        title_type: form.title_type as TitleType,
        status: form.status as TitleStatus,
        synopsis: form.synopsis || null,
        genres: form.genres || null,
        rating: form.rating || null,
        parent_id: form.parent_id ? Number(form.parent_id) : null,
        season_number: form.season_number ? Number(form.season_number) : null,
        episode_number: form.episode_number ? Number(form.episode_number) : null,
        runtime_minutes: form.runtime_minutes
          ? Number(form.runtime_minutes)
          : null,
        release_date: form.release_date || null,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {error && <div className="error-banner">{error}</div>}
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
          Genres (comma-separated)
          <input value={form.genres} onChange={(e) => set("genres", e.target.value)} />
        </label>
        <label>
          Rating
          <input value={form.rating} onChange={(e) => set("rating", e.target.value)} />
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
        <label>
          Runtime (minutes)
          <input
            type="number"
            value={form.runtime_minutes}
            onChange={(e) => set("runtime_minutes", e.target.value)}
          />
        </label>
        <label>
          Synopsis
          <textarea value={form.synopsis} onChange={(e) => set("synopsis", e.target.value)} />
        </label>
      </div>
      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}
