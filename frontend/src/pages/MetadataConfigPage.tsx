import { useEffect, useMemo, useState } from "react";
import { metadataConfigApi } from "../api/client";
import type { MetadataConfig, MetadataDisplaySettings, TitleType } from "../types";
import { CORE_METADATA_FIELDS } from "../utils/metadataRequirements";

const TITLE_TYPES: TitleType[] = ["movie", "series", "season", "episode"];
const TITLE_TYPE_LABELS: Record<TitleType, string> = {
  movie: "Movie",
  series: "Series",
  season: "Season",
  episode: "Episode",
};

function allFieldKeys(): string[] {
  return CORE_METADATA_FIELDS.map((field) => field.key);
}

function emptySettings(): MetadataDisplaySettings {
  const keys = allFieldKeys();
  return {
    movie: keys,
    series: keys,
    season: keys,
    episode: keys,
  };
}

function normalizeSettings(
  settings?: Partial<MetadataDisplaySettings> | null
): MetadataDisplaySettings {
  const valid = new Set(allFieldKeys());
  const fallback = emptySettings();
  return TITLE_TYPES.reduce((acc, titleType) => {
    const selected = settings?.[titleType] ?? fallback[titleType];
    acc[titleType] = selected.filter((key) => valid.has(key));
    return acc;
  }, {} as MetadataDisplaySettings);
}

export function MetadataConfigPage() {
  const [config, setConfig] = useState<MetadataConfig | null>(null);
  const [settings, setSettings] = useState<MetadataDisplaySettings>(() => emptySettings());
  const [activeType, setActiveType] = useState<TitleType>("movie");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    metadataConfigApi
      .get()
      .then((data) => {
        setConfig(data);
        setSettings(normalizeSettings(data.settings));
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load metadata config");
        setSettings(emptySettings());
      })
      .finally(() => setLoading(false));
  }, []);

  const selected = useMemo(
    () => new Set(settings[activeType] ?? []),
    [settings, activeType]
  );

  const setTypeFields = (titleType: TitleType, keys: string[]) => {
    const valid = new Set(allFieldKeys());
    const next = keys.filter((key, index) => valid.has(key) && keys.indexOf(key) === index);
    setSettings((current) => ({ ...current, [titleType]: next }));
    setSuccess(null);
  };

  const toggleField = (key: string) => {
    const current = settings[activeType] ?? [];
    setTypeFields(
      activeType,
      current.includes(key)
        ? current.filter((existing) => existing !== key)
        : [...current, key]
    );
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await metadataConfigApi.update(settings);
      setConfig(updated);
      setSettings(normalizeSettings(updated.settings));
      setSuccess("Metadata display configuration saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save metadata config");
    } finally {
      setSaving(false);
    }
  };

  const restoreDefaults = () => {
    setSettings(normalizeSettings(config?.defaults ?? emptySettings()));
    setSuccess(null);
  };

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Metadata Config</h1>
          <p>Choose which Core metadata fields appear in the Edit Title form.</p>
        </div>
        <button className="btn btn-primary" onClick={save} disabled={loading || saving}>
          {saving ? "Saving..." : "Save configuration"}
        </button>
      </header>

      {error && <div className="error-banner">{error}</div>}
      {success && <div className="metadata-applied-banner">{success}</div>}

      <div className="card metadata-config-card">
        <div className="metadata-config-tabs">
          {TITLE_TYPES.map((titleType) => (
            <button
              key={titleType}
              type="button"
              className={`title-tab ${activeType === titleType ? "active" : ""}`}
              onClick={() => setActiveType(titleType)}
            >
              {TITLE_TYPE_LABELS[titleType]}
              <span>{settings[titleType]?.length ?? 0}</span>
            </button>
          ))}
        </div>

        <div className="metadata-config-toolbar">
          <div>
            <h2>{TITLE_TYPE_LABELS[activeType]} fields</h2>
            <p>
              Checked fields appear in Core metadata for {TITLE_TYPE_LABELS[activeType].toLowerCase()} titles.
            </p>
          </div>
          <div className="metadata-config-actions">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setTypeFields(activeType, allFieldKeys())}
              disabled={loading}
            >
              Select all
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setTypeFields(activeType, [])}
              disabled={loading}
            >
              Clear all
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={restoreDefaults}
              disabled={loading}
            >
              Restore defaults
            </button>
          </div>
        </div>

        {loading ? (
          <p className="empty">Loading metadata configuration...</p>
        ) : (
          <div className="metadata-field-grid">
            {CORE_METADATA_FIELDS.map((field) => (
              <label key={field.key} className="metadata-field-toggle">
                <input
                  type="checkbox"
                  checked={selected.has(field.key)}
                  onChange={() => toggleField(field.key)}
                />
                <span>
                  <strong>{field.label}</strong>
                  <code>{field.key}</code>
                </span>
              </label>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
