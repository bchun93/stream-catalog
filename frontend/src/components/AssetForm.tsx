import { useState } from "react";
import type { AssetStatus, AssetType, MediaAsset, Title } from "../types";

interface AssetFormProps {
  titles: Title[];
  initial?: Partial<MediaAsset>;
  onSubmit: (data: Partial<MediaAsset>) => Promise<void>;
  onCancel: () => void;
}

const TYPES: AssetType[] = [
  "video_master",
  "trailer",
  "poster",
  "backdrop",
  "logo",
  "still",
  "cast_photo",
  "season_poster",
  "thumbnail",
  "subtitle",
  "audio",
  "caption",
];
const STATUSES: AssetStatus[] = [
  "uploaded",
  "processing",
  "ready",
  "failed",
  "archived",
];

export function AssetForm({ titles, initial, onSubmit, onCancel }: AssetFormProps) {
  const [form, setForm] = useState({
    title_id: initial?.title_id?.toString() ?? (titles[0]?.id?.toString() ?? ""),
    asset_type: initial?.asset_type ?? "video_master",
    status: initial?.status ?? "uploaded",
    filename: initial?.filename ?? "",
    storage_uri: initial?.storage_uri ?? "",
    mime_type: initial?.mime_type ?? "",
    resolution: initial?.resolution ?? "",
    language: initial?.language ?? "",
    codec: initial?.codec ?? "",
    duration_seconds: initial?.duration_seconds?.toString() ?? "",
    size_bytes: initial?.size_bytes?.toString() ?? "",
    notes: initial?.notes ?? "",
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
        title_id: Number(form.title_id),
        asset_type: form.asset_type as AssetType,
        status: form.status as AssetStatus,
        filename: form.filename,
        storage_uri: form.storage_uri,
        mime_type: form.mime_type || null,
        resolution: form.resolution || null,
        language: form.language || null,
        codec: form.codec || null,
        duration_seconds: form.duration_seconds
          ? Number(form.duration_seconds)
          : null,
        size_bytes: form.size_bytes ? Number(form.size_bytes) : null,
        notes: form.notes || null,
      });
      onCancel();
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
          Linked title
          <select
            required
            value={form.title_id}
            onChange={(e) => set("title_id", e.target.value)}
          >
            {titles.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Asset type
          <select
            value={form.asset_type}
            onChange={(e) => set("asset_type", e.target.value)}
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={form.status} onChange={(e) => set("status", e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Filename
          <input
            required
            value={form.filename}
            onChange={(e) => set("filename", e.target.value)}
          />
        </label>
        <label>
          Storage URI
          <input
            required
            className="mono"
            value={form.storage_uri}
            onChange={(e) => set("storage_uri", e.target.value)}
            placeholder="s3://bucket/path/file.ext"
          />
        </label>
        <label>
          MIME type
          <input value={form.mime_type} onChange={(e) => set("mime_type", e.target.value)} />
        </label>
        <label>
          Resolution
          <input value={form.resolution} onChange={(e) => set("resolution", e.target.value)} />
        </label>
        <label>
          Language
          <input value={form.language} onChange={(e) => set("language", e.target.value)} />
        </label>
        <label>
          Codec
          <input value={form.codec} onChange={(e) => set("codec", e.target.value)} />
        </label>
        <label>
          Duration (seconds)
          <input
            type="number"
            value={form.duration_seconds}
            onChange={(e) => set("duration_seconds", e.target.value)}
          />
        </label>
        <label>
          Size (bytes)
          <input
            type="number"
            value={form.size_bytes}
            onChange={(e) => set("size_bytes", e.target.value)}
          />
        </label>
        <label>
          Notes
          <textarea value={form.notes} onChange={(e) => set("notes", e.target.value)} />
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
