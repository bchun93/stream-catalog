import { useEffect, useState } from "react";
import { artworkAiApi } from "../api/client";
import type { ArtworkItem, ArtworkRole, ArtworkTrainingExample, ArtworkType } from "../types";

const ARTWORK_ROLE_OPTIONS: ArtworkRole[] = [
  "vertical_poster",
  "box_art",
  "hero_image",
  "horizontal_poster",
  "still_frame",
  "logo",
  "season_poster",
  "cast_photo",
  "unknown",
];

const ARTWORK_ROLE_LABELS: Record<ArtworkRole, string> = {
  vertical_poster: "Vertical poster",
  box_art: "Box art",
  hero_image: "Hero image",
  horizontal_poster: "Horizontal poster",
  still_frame: "Still frame",
  logo: "Logo",
  season_poster: "Season poster",
  cast_photo: "Cast photo",
  unknown: "Unknown",
};

function roleToArtworkType(role: ArtworkRole): ArtworkType {
  if (role === "logo") return "logo";
  if (role === "still_frame") return "still";
  if (role === "season_poster") return "season_poster";
  if (role === "cast_photo") return "cast_photo";
  if (role === "hero_image" || role === "horizontal_poster") return "backdrop";
  return "poster";
}

export function AITrainingPage() {
  const [role, setRole] = useState<ArtworkRole>("vertical_poster");
  const [item, setItem] = useState<ArtworkItem | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [examples, setExamples] = useState<ArtworkTrainingExample[]>([]);
  const [loadingExamples, setLoadingExamples] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadExamples = () => {
    setLoadingExamples(true);
    artworkAiApi
      .listTraining()
      .then(setExamples)
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Could not load training examples");
      })
      .finally(() => setLoadingExamples(false));
  };

  useEffect(() => {
    loadExamples();
  }, []);

  const handleFile = (file: File | null) => {
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setItem(null);
    setSuccess(null);
    setError(null);
    if (!file) return;

    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const width = img.naturalWidth || null;
      const height = img.naturalHeight || null;
      const aspect = width && height ? width / height : null;
      setPreview(url);
      setItem({
        asset_type: roleToArtworkType(role),
        storage_uri: `training-upload://${Date.now()}-${encodeURIComponent(file.name)}`,
        filename: file.name.slice(0, 255),
        mime_type: file.type || "image/jpeg",
        resolution: width && height ? `${width}×${height}` : null,
        specs: {
          width,
          height,
          aspect_ratio: aspect,
          aspect_ratio_label: aspect ? `${aspect.toFixed(2)}:1` : null,
          label: ARTWORK_ROLE_LABELS[role],
        },
      });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      setError("Could not read that image file.");
    };
    img.src = url;
  };

  const updateRole = (nextRole: ArtworkRole) => {
    setRole(nextRole);
    if (!item) return;
    setItem({
      ...item,
      asset_type: roleToArtworkType(nextRole),
      specs: {
        ...(item.specs ?? {}),
        label: ARTWORK_ROLE_LABELS[nextRole],
      },
    });
  };

  const saveTrainingExample = async () => {
    if (!item) {
      setError("Choose an image file to train with.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await artworkAiApi.label({
        title_id: null,
        item: {
          ...item,
          asset_type: roleToArtworkType(role),
          specs: {
            ...(item.specs ?? {}),
            label: ARTWORK_ROLE_LABELS[role],
          },
        },
        assigned_role: role,
        decision: "approved",
      });
      setSuccess(`Saved training example as ${ARTWORK_ROLE_LABELS[role]}.`);
      loadExamples();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save training example");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <header className="page-header">
        <div>
          <h1>AI artwork training</h1>
          <p>
            Train the catalog-level classifier with example images, then apply that learning
            when titles fetch artwork from TMDB.
          </p>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}
      {success && <div className="metadata-applied-banner">{success}</div>}

      <section className="card ai-training-card">
        <h3>Upload training example</h3>
        <p className="metadata-hint">
          These examples are not attached to one title. They become global training inputs
          for classifying future TMDB candidates as hero, vertical poster, still frame, logo,
          and other artwork types.
        </p>
        <div className="artwork-training-upload">
          <label>
            Training image
            <input type="file" accept="image/*" onChange={(e) => handleFile(e.target.files?.[0] ?? null)} />
          </label>
          <label>
            Artwork type
            <select value={role} onChange={(e) => updateRole(e.target.value as ArtworkRole)}>
              {ARTWORK_ROLE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {ARTWORK_ROLE_LABELS[option]}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!item || saving}
            onClick={saveTrainingExample}
          >
            {saving ? "Saving…" : "Save training example"}
          </button>
        </div>
        {preview && item && (
          <div className="artwork-training-preview">
            <img src={preview} alt="" />
            <div>
              <strong>{item.filename}</strong>
              <p>
                {ARTWORK_ROLE_LABELS[role]} · {item.resolution || "unknown resolution"}
              </p>
            </div>
          </div>
        )}
      </section>

      <section className="card ai-training-card">
        <h3>Submitted training examples</h3>
        <p className="metadata-hint">
          These global examples are what AI Classify compares against when labeling TMDB
          candidates. The classifier uses image features (aspect ratio, dimensions, TMDB
          source type), not the uploaded file pixels.
        </p>
        {loadingExamples ? (
          <p className="empty">Loading training examples…</p>
        ) : examples.length === 0 ? (
          <p className="empty">No training examples saved yet.</p>
        ) : (
          <div className="ai-training-list">
            {examples.map((example) => (
              <div key={example.id} className="ai-training-list-item">
                <div>
                  <strong>{example.filename || "Untitled image"}</strong>
                  <p>
                    {ARTWORK_ROLE_LABELS[example.assigned_role]} · {example.decision}
                    {example.source_asset_type ? ` · ${example.source_asset_type}` : ""}
                  </p>
                  <p className="ai-training-list-meta">
                    Saved {new Date(example.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card ai-training-card">
        <h3>How the tool uses this</h3>
        <p className="metadata-hint">
          This is not an LLM. It is a lightweight nearest-neighbor classifier: when you run
          AI Classify on a title, TMDB image metadata is compared to your labeled examples.
          More diverse examples improve labeling, especially for roles that look similar
          (hero vs horizontal poster, vertical poster vs box art).
        </p>
        <p className="metadata-hint">
          On each title, use Browse TMDB to fetch candidates, then run AI Classify or
          Auto-assign high confidence. Confident matches can be saved automatically.
        </p>
      </section>
    </>
  );
}
