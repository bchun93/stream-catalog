import { useCallback, useEffect, useMemo, useState } from "react";

import { ingestApi, titlesApi } from "../api/client";
import { Badge } from "../components/Badge";
import type {
  IngestJob,
  IngestManifest,
  IngestManifestValidateResponse,
  Title,
} from "../types";
import { ingestJobSummary } from "../utils/ingest";

const DEFAULT_MAX_KEYS = 1000;

export function IngestPage() {
  const [titles, setTitles] = useState<Title[]>([]);
  const [manifests, setManifests] = useState<IngestManifest[]>([]);
  const [jobs, setJobs] = useState<IngestJob[]>([]);

  const [titleId, setTitleId] = useState("");
  const [manifestId, setManifestId] = useState("");
  const [sourcePrefix, setSourcePrefix] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [maxKeys, setMaxKeys] = useState(String(DEFAULT_MAX_KEYS));
  const [dryRun, setDryRun] = useState(false);

  const [preview, setPreview] = useState<IngestManifestValidateResponse | null>(null);
  const [selectedJob, setSelectedJob] = useState<IngestJob | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = Boolean(titleId && manifestId);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [loadedTitles, loadedManifests, loadedJobs] = await Promise.all([
        titlesApi.list(),
        ingestApi.listManifests(true),
        ingestApi.listJobs({ limit: 100 }),
      ]);
      setTitles(loadedTitles);
      setManifests(loadedManifests);
      setJobs(loadedJobs);
      if (!titleId && loadedTitles.length) setTitleId(String(loadedTitles[0].id));
      if (!manifestId && loadedManifests.length) setManifestId(String(loadedManifests[0].id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load ingest data");
    }
  }, [manifestId, titleId]);

  useEffect(() => {
    void load();
  }, [load]);

  const titleMap = useMemo(
    () => new Map(titles.map((title) => [title.id, title.name])),
    [titles]
  );

  const parseMaxKeys = () => {
    const parsed = Number(maxKeys);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_MAX_KEYS;
  };

  const handlePreview = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      const data = await ingestApi.validateManifest({
        manifest_id: Number(manifestId),
        source_prefix: sourcePrefix,
        max_keys: parseMaxKeys(),
      });
      setPreview(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Validation failed");
    } finally {
      setLoading(false);
    }
  };

  const handleStartJob = async (isDryRun: boolean) => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      const job = await ingestApi.createJob({
        title_id: Number(titleId),
        manifest_id: Number(manifestId),
        source_prefix: sourcePrefix,
        created_by: createdBy || undefined,
        dry_run: isDryRun,
        max_keys: parseMaxKeys(),
      });
      setDryRun(isDryRun);
      setSelectedJob(job);
      setPreview(null);
      const refreshed = await ingestApi.listJobs({ limit: 100 });
      setJobs(refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start ingest job");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectJob = async (jobId: number) => {
    setLoading(true);
    setError(null);
    try {
      const job = await ingestApi.getJob(jobId);
      setSelectedJob(job);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load job details");
    } finally {
      setLoading(false);
    }
  };

  const retryJob = async (job: IngestJob) => {
    setTitleId(String(job.title_id));
    if (job.manifest_id != null) setManifestId(String(job.manifest_id));
    setSourcePrefix(job.source_prefix);
    setCreatedBy(job.created_by ?? "");
    await handleStartJob(job.dry_run);
  };

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Ingest</h1>
          <p>
            Run manifest-driven ingest from Aspera/S3 landing prefixes and register media
            assets with visible MediaInfo specs.
          </p>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="card ingest-card">
        <h3>New ingest job</h3>
        <div className="form-grid">
          <label>
            Title
            <select value={titleId} onChange={(e) => setTitleId(e.target.value)}>
              {titles.map((title) => (
                <option key={title.id} value={String(title.id)}>
                  {title.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Manifest template
            <select value={manifestId} onChange={(e) => setManifestId(e.target.value)}>
              {manifests.map((manifest) => (
                <option key={manifest.id} value={String(manifest.id)}>
                  {manifest.name} v{manifest.version}
                </option>
              ))}
            </select>
          </label>
          <label className="form-span-2">
            S3/Aspera source prefix
            <input
              placeholder="drop-2026-05/title-54"
              value={sourcePrefix}
              onChange={(e) => setSourcePrefix(e.target.value)}
            />
          </label>
          <label>
            Created by
            <input
              placeholder="operator name/email"
              value={createdBy}
              onChange={(e) => setCreatedBy(e.target.value)}
            />
          </label>
          <label>
            Max keys
            <input
              type="number"
              min={1}
              max={5000}
              value={maxKeys}
              onChange={(e) => setMaxKeys(e.target.value)}
            />
          </label>
        </div>
        <div className="form-actions" style={{ justifyContent: "space-between" }}>
          <label className="ingest-checkbox">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            Default to dry run
          </label>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button className="btn btn-ghost" disabled={!canSubmit || loading} onClick={handlePreview}>
              Validate + preview
            </button>
            <button
              className="btn btn-primary"
              disabled={!canSubmit || loading}
              onClick={() => handleStartJob(dryRun)}
            >
              {loading ? "Running…" : dryRun ? "Run dry job" : "Start ingest"}
            </button>
          </div>
        </div>
      </section>

      {preview && (
        <section className="card ingest-card">
          <h3>
            Preview results{" "}
            <span className="ingest-muted">
              ({preview.discovered_count} files, {preview.matched_count} matched)
            </span>
          </h3>
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Matched type</th>
                <th>Rule</th>
                <th>Resolution</th>
                <th>Warnings</th>
              </tr>
            </thead>
            <tbody>
              {preview.items.slice(0, 50).map((item) => (
                <tr key={item.s3_key}>
                  <td className="mono">{item.filename}</td>
                  <td>
                    {item.inferred_asset_type ? (
                      <Badge value={item.inferred_asset_type} kind="asset" />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{item.matched_rule ?? "—"}</td>
                  <td>{item.resolution ?? "—"}</td>
                  <td>{item.warnings.join(" ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="card ingest-card">
        <div className="ingest-jobs-header">
          <h3>Ingest jobs</h3>
          <button className="btn btn-ghost" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </div>
        {jobs.length === 0 ? (
          <p className="empty">No ingest jobs yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Status</th>
                <th>Source prefix</th>
                <th>Results</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td className="mono">#{job.id}</td>
                  <td>{titleMap.get(job.title_id) ?? job.title_id}</td>
                  <td>
                    <Badge value={job.status} />
                  </td>
                  <td className="mono">{job.source_prefix || "—"}</td>
                  <td>{ingestJobSummary(job)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button
                      className="btn btn-ghost"
                      style={{ marginRight: "0.35rem" }}
                      onClick={() => void handleSelectJob(job.id)}
                    >
                      Details
                    </button>
                    <button className="btn btn-ghost" onClick={() => void retryJob(job)}>
                      Retry
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {selectedJob && (
        <section className="card ingest-card">
          <h3>
            Job #{selectedJob.id} details <span className="ingest-muted">({selectedJob.status})</span>
          </h3>
          {selectedJob.items && selectedJob.items.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Asset ID</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {selectedJob.items.map((item) => (
                  <tr key={item.id}>
                    <td className="mono">{item.filename}</td>
                    <td>
                      {item.inferred_asset_type ? (
                        <Badge value={item.inferred_asset_type} kind="asset" />
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <Badge value={item.status} />
                    </td>
                    <td>{item.resulting_asset_id ?? "—"}</td>
                    <td>{item.error_message ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty">No ingest items found for this job.</p>
          )}
        </section>
      )}
    </>
  );
}
