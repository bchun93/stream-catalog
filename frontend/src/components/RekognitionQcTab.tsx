import { useCallback, useEffect, useState } from "react";
import { DownloadCloud, RefreshCw, ScanSearch } from "lucide-react";

import { rekognitionApi } from "../api/client";
import type {
  MediaAsset,
  RekognitionAnalyzeResponse,
  RekognitionFeature,
  RekognitionJob,
} from "../types";
import { StatusBadge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { RekognitionVideoPicker } from "./RekognitionVideoPicker";

const FEATURES: { key: RekognitionFeature; label: string; hint: string }[] = [
  { key: "SEGMENT", label: "Segments", hint: "Technical cues & shots (QC markers)" },
  { key: "MODERATION", label: "Moderation", hint: "Content compliance flags" },
  { key: "LABELS", label: "Labels", hint: "On-screen objects & scenes" },
];

function jobBadge(status?: string) {
  if (!status) return <span className="text-tertiary">Not started</span>;
  if (status === "IN_PROGRESS") return <StatusBadge value="processing" pulse />;
  if (status === "SUCCEEDED") return <StatusBadge value="ready" />;
  if (status === "FAILED" || status === "ERROR") return <StatusBadge value="failed" />;
  return <StatusBadge value={status} />;
}

export function RekognitionQcTab({ asset }: { asset: MediaAsset }) {
  const [jobs, setJobs] = useState<RekognitionJob[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<RekognitionAnalyzeResponse | null>(null);
  const [overrideKey, setOverrideKey] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [draining, setDraining] = useState(false);
  const [drainMsg, setDrainMsg] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      setJobs(await rekognitionApi.listJobs(asset.id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [asset.id]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const target = overrideKey ?? asset.storage_uri;

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      const res = await rekognitionApi.analyze(
        asset.id,
        overrideKey ? { s3_key: overrideKey } : undefined
      );
      setResult(res);
      await loadJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analyze failed");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDrain = async () => {
    setDraining(true);
    setDrainMsg(null);
    setError(null);
    try {
      const res = await rekognitionApi.drain();
      setDrainMsg(
        `Drained queue: received ${res.received}, processed ${res.processed}, failed ${res.failed}.`
      );
      await loadJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Drain failed");
    } finally {
      setDraining(false);
    }
  };

  const jobByFeature = (feature: RekognitionFeature) =>
    jobs.find((j) => j.feature === feature);
  const resultByFeature = (feature: RekognitionFeature) =>
    result?.results.find((r) => r.feature === feature);

  return (
    <div className="reko-qc">
      <div className="reko-qc-intro">
        <p className="text-secondary">
          Run Amazon Rekognition Video on the H.264 MP4 proxy. Jobs run asynchronously;
          status updates arrive via the completion consumer (no polling).
        </p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="card reko-qc-target">
        <div className="reko-qc-target-row">
          <div className="reko-qc-target-info">
            <span className="text-tertiary">Proxy to analyze</span>
            <code className="mono" title={target}>
              {target}
            </code>
            {overrideKey && (
              <span className="reko-qc-override-note">
                Overriding the asset proxy with a picked S3 object.
              </span>
            )}
          </div>
          <div className="reko-qc-target-actions">
            <Button variant="ghost" onClick={() => setPickerOpen((v) => !v)}>
              {pickerOpen ? "Close picker" : "Choose S3 video"}
            </Button>
            {overrideKey && (
              <Button variant="subtle" onClick={() => setOverrideKey(null)}>
                Use asset proxy
              </Button>
            )}
          </div>
        </div>

        {pickerOpen && (
          <RekognitionVideoPicker
            onPick={(key) => {
              setOverrideKey(key);
              setPickerOpen(false);
            }}
            onCancel={() => setPickerOpen(false)}
          />
        )}
      </div>

      <div className="reko-qc-actions">
        <Button
          variant="primary"
          icon={<ScanSearch size={16} />}
          disabled={analyzing}
          onClick={handleAnalyze}
        >
          {analyzing ? "Starting…" : "Analyze with Rekognition"}
        </Button>
        <Button
          variant="ghost"
          icon={<RefreshCw size={15} />}
          disabled={loading}
          onClick={() => void loadJobs()}
        >
          Refresh
        </Button>
        <Button
          variant="subtle"
          icon={<DownloadCloud size={15} />}
          disabled={draining}
          onClick={handleDrain}
          title="Pull any completed Rekognition results from the queue now (instead of waiting for the cron)."
        >
          {draining ? "Draining…" : "Drain now"}
        </Button>
      </div>

      {drainMsg && <div className="reko-qc-drain-note">{drainMsg}</div>}

      {result?.warnings?.length ? (
        <div className="reko-qc-warnings">
          {result.warnings.map((w) => (
            <div key={w} className="reko-qc-warning">
              {w}
            </div>
          ))}
        </div>
      ) : null}

      <div className="card reko-qc-jobs">
        <table className="data-table">
          <thead>
            <tr>
              <th>Feature</th>
              <th>Status</th>
              <th>Job ID</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {FEATURES.map(({ key, label, hint }) => {
              const job = jobByFeature(key);
              const res = resultByFeature(key);
              const status = res?.status ?? job?.status;
              return (
                <tr key={key}>
                  <td>
                    <div className="reko-qc-feature">
                      <strong>{label}</strong>
                      <span className="text-tertiary">{hint}</span>
                    </div>
                  </td>
                  <td>{jobBadge(status)}</td>
                  <td className="mono text-tertiary">
                    {job?.aws_job_id ?? res?.aws_job_id ?? "—"}
                  </td>
                  <td className="text-tertiary">
                    {res?.message ?? job?.error ?? ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
