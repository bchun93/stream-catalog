import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Clapperboard, Tag } from "lucide-react";

import { rekognitionApi } from "../api/client";
import type { MediaAsset, RekognitionDetection } from "../types";
import { formatConfidence, formatTimecode } from "../utils/format";

/** Technical-cue kinds are the QC markers an ops user acts on. "Shot" is a cut boundary. */
function isTechnicalCue(d: RekognitionDetection): boolean {
  return d.feature === "SEGMENT" && d.kind !== "Shot";
}

function pct(ms: number, durationMs: number): number {
  if (durationMs <= 0) return 0;
  return Math.min(100, Math.max(0, (ms / durationMs) * 100));
}

export function RekognitionResults({
  asset,
  reloadToken,
}: {
  asset: MediaAsset;
  reloadToken: number;
}) {
  const [detections, setDetections] = useState<RekognitionDetection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [labelQuery, setLabelQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDetections(await rekognitionApi.listDetections(asset.id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load detections");
    } finally {
      setLoading(false);
    }
  }, [asset.id]);

  useEffect(() => {
    void load();
  }, [load, reloadToken]);

  const { techCues, shots, moderation, labels, durationMs } = useMemo(() => {
    const techCues = detections.filter(isTechnicalCue);
    const shots = detections.filter((d) => d.feature === "SEGMENT" && d.kind === "Shot");
    const moderation = detections.filter((d) => d.feature === "MODERATION");
    const labels = detections.filter((d) => d.feature === "LABELS");
    const maxMs = detections.reduce(
      (m, d) => Math.max(m, d.end_ms ?? d.timestamp_ms ?? d.start_ms ?? 0),
      0
    );
    const durationMs = asset.duration_seconds
      ? asset.duration_seconds * 1000
      : maxMs || 1;
    return { techCues, shots, moderation, labels, durationMs };
  }, [detections, asset.duration_seconds]);

  const filteredLabels = useMemo(() => {
    const q = labelQuery.trim().toLowerCase();
    if (!q) return labels;
    return labels.filter((d) => (d.name ?? d.kind ?? "").toLowerCase().includes(q));
  }, [labels, labelQuery]);

  if (loading) return <p className="empty">Loading detections…</p>;
  if (error) return <div className="error-banner">{error}</div>;

  const hasAny =
    techCues.length + shots.length + moderation.length + labels.length > 0;
  if (!hasAny) {
    return (
      <p className="empty">
        No detections yet. Run an analysis, then drain the queue (or wait for the cron).
      </p>
    );
  }

  return (
    <div className="reko-results">
      {/* QC markers — segment technical cues + shot boundaries on a proportional timeline */}
      <section className="reko-section">
        <div className="reko-section-head">
          <Clapperboard size={15} aria-hidden />
          <h3>QC markers</h3>
          <span className="text-tertiary">
            {techCues.length} technical cue{techCues.length === 1 ? "" : "s"} ·{" "}
            {shots.length} shot{shots.length === 1 ? "" : "s"}
          </span>
        </div>

        {techCues.length + shots.length > 0 && (
          <div
            className="reko-timeline-track"
            role="img"
            aria-label="Timeline of technical cues and shots"
          >
            {shots.map((d) => (
              <span
                key={d.sk}
                className="reko-timeline-shot"
                style={{ left: `${pct(d.start_ms ?? 0, durationMs)}%` }}
                title={`Shot @ ${formatTimecode(d.start_ms)}`}
              />
            ))}
            {techCues.map((d) => {
              const start = d.start_ms ?? 0;
              const end = d.end_ms ?? start;
              const left = pct(start, durationMs);
              const width = Math.max(0.8, pct(end, durationMs) - left);
              return (
                <span
                  key={d.sk}
                  className={`reko-timeline-cue cue-${(d.kind ?? "").toLowerCase()}`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`${d.kind}: ${formatTimecode(start)}–${formatTimecode(end)} (${formatConfidence(d.confidence)})`}
                />
              );
            })}
          </div>
        )}

        {techCues.length > 0 ? (
          <table className="data-table reko-cue-table">
            <thead>
              <tr>
                <th>Cue</th>
                <th>Start</th>
                <th>End</th>
                <th className="num">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {techCues.map((d) => (
                <tr key={d.sk}>
                  <td>
                    <span className="reko-cue-chip">{d.kind}</span>
                  </td>
                  <td className="mono">{formatTimecode(d.start_ms)}</td>
                  <td className="mono">{formatTimecode(d.end_ms)}</td>
                  <td className="num text-tertiary">{formatConfidence(d.confidence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-tertiary reko-empty-line">
            No technical cues (black frames, color bars, end credits) detected.
          </p>
        )}
      </section>

      {/* Moderation — compliance flags by timestamp */}
      <section className="reko-section">
        <div className="reko-section-head">
          <AlertTriangle size={15} aria-hidden />
          <h3>Content moderation</h3>
          <span className="text-tertiary">{moderation.length} flag{moderation.length === 1 ? "" : "s"}</span>
        </div>
        {moderation.length > 0 ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Label</th>
                <th>Category</th>
                <th>Time</th>
                <th className="num">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {moderation.map((d) => (
                <tr key={d.sk}>
                  <td>
                    <span className="reko-mod-chip">{d.kind}</span>
                  </td>
                  <td className="text-tertiary">{d.name && d.name !== d.kind ? d.name : "—"}</td>
                  <td className="mono">{formatTimecode(d.timestamp_ms)}</td>
                  <td className="num text-tertiary">{formatConfidence(d.confidence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-tertiary reko-empty-line">No moderation flags.</p>
        )}
      </section>

      {/* Labels — time-stamped searchable tags */}
      <section className="reko-section">
        <div className="reko-section-head">
          <Tag size={15} aria-hidden />
          <h3>Labels</h3>
          <span className="text-tertiary">{labels.length} detected</span>
        </div>
        {labels.length > 0 ? (
          <>
            <input
              type="search"
              className="reko-label-search"
              placeholder="Search labels…"
              value={labelQuery}
              onChange={(e) => setLabelQuery(e.target.value)}
              aria-label="Search labels"
            />
            <div className="reko-tags">
              {filteredLabels.slice(0, 400).map((d) => (
                <span key={d.sk} className="reko-tag" title={formatConfidence(d.confidence)}>
                  {d.name ?? d.kind}
                  <span className="reko-tag-time mono">{formatTimecode(d.timestamp_ms)}</span>
                </span>
              ))}
              {filteredLabels.length === 0 && (
                <span className="text-tertiary">No labels match “{labelQuery}”.</span>
              )}
            </div>
            {filteredLabels.length > 400 && (
              <p className="text-tertiary reko-empty-line">
                Showing first 400 of {filteredLabels.length} matches.
              </p>
            )}
          </>
        ) : (
          <p className="text-tertiary reko-empty-line">No labels detected.</p>
        )}
      </section>
    </div>
  );
}
