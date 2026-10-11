import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Clapperboard, FileSearch, Tag, Type } from "lucide-react";

import { rekognitionApi } from "../api/client";
import type { MediaAsset, PictureQcReport, RekognitionDetection } from "../types";
import { formatConfidence, formatTimecode } from "../utils/format";

const IMPLIED_RATING: Record<string, string> = {
  explicit: "R / TV-MA",
  "explicit nudity": "R / TV-MA",
  violence: "PG-13 / TV-14",
  "graphic violence": "R / TV-MA",
  "hate symbols": "R / TV-MA",
  "drugs & tobacco": "PG-13 / TV-14",
  drugs: "PG-13 / TV-14",
  tobacco: "PG-13 / TV-14",
  alcohol: "PG / TV-PG",
  gambling: "PG / TV-PG",
};

function isTechnicalCue(d: RekognitionDetection): boolean {
  return d.feature === "SEGMENT" && d.kind !== "Shot";
}

function pct(ms: number, durationMs: number): number {
  if (durationMs <= 0) return 0;
  return Math.min(100, Math.max(0, (ms / durationMs) * 100));
}

function metaNumber(meta: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = meta?.[key];
  return typeof value === "number" ? value : null;
}

function metaString(meta: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = meta?.[key];
  return typeof value === "string" && value ? value : null;
}

function impliedRating(kind?: string | null, parent?: string | null): string | null {
  for (const raw of [kind, parent]) {
    if (!raw) continue;
    const hit = IMPLIED_RATING[raw.trim().toLowerCase()];
    if (hit) return hit;
  }
  return null;
}

export function RekognitionResults({
  asset,
  reloadToken,
}: {
  asset: MediaAsset;
  reloadToken: number;
}) {
  const [detections, setDetections] = useState<RekognitionDetection[]>([]);
  const [report, setReport] = useState<PictureQcReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [labelQuery, setLabelQuery] = useState("");
  const [focusMs, setFocusMs] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextDetections, nextReport] = await Promise.all([
        rekognitionApi.listDetections(asset.id),
        rekognitionApi.getReport(asset.id),
      ]);
      setDetections(nextDetections);
      setReport(nextReport);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load picture QC");
    } finally {
      setLoading(false);
    }
  }, [asset.id]);

  useEffect(() => {
    void load();
  }, [load, reloadToken]);

  const { techCues, shots, moderation, labels, texts, durationMs } = useMemo(() => {
    const byStart = (a: RekognitionDetection, b: RekognitionDetection) =>
      (a.start_ms ?? 0) - (b.start_ms ?? 0);
    const byTimestamp = (a: RekognitionDetection, b: RekognitionDetection) =>
      (a.timestamp_ms ?? 0) - (b.timestamp_ms ?? 0);
    const techCues = detections.filter(isTechnicalCue).sort(byStart);
    const shots = detections
      .filter((d) => d.feature === "SEGMENT" && d.kind === "Shot")
      .sort(byStart);
    const moderation = detections
      .filter((d) => d.feature === "MODERATION")
      .sort(byTimestamp);
    const labels = detections.filter((d) => d.feature === "LABELS").sort(byTimestamp);
    const texts = detections
      .filter((d) => d.feature === "TEXT" && (d.kind ?? "").toUpperCase() !== "WORD")
      .sort(byTimestamp);
    const textRows = texts.length
      ? texts
      : detections.filter((d) => d.feature === "TEXT").sort(byTimestamp);
    const maxMs = detections.reduce(
      (m, d) => Math.max(m, d.end_ms ?? d.timestamp_ms ?? d.start_ms ?? 0),
      0
    );
    const fromMeta = metaNumber(report?.video_metadata, "DurationMillis");
    const durationMs = asset.duration_seconds
      ? asset.duration_seconds * 1000
      : fromMeta ?? maxMs || 1;
    return { techCues, shots, moderation, labels, texts: textRows, durationMs };
  }, [detections, asset.duration_seconds, report?.video_metadata]);

  const moderationGroups = useMemo(() => {
    const groups = new Map<string, { count: number; rating: string | null }>();
    for (const row of moderation) {
      const category = row.name && row.name !== row.kind ? row.name : row.kind ?? "Moderation";
      const current = groups.get(category) ?? {
        count: 0,
        rating: impliedRating(row.kind, row.name),
      };
      current.count += 1;
      if (!current.rating) current.rating = impliedRating(row.kind, row.name);
      groups.set(category, current);
    }
    return [...groups.entries()].sort((a, b) => b[1].count - a[1].count);
  }, [moderation]);

  const filteredLabels = useMemo(() => {
    const q = labelQuery.trim().toLowerCase();
    if (!q) return labels;
    return labels.filter((d) => (d.name ?? d.kind ?? "").toLowerCase().includes(q));
  }, [labels, labelQuery]);

  if (loading && detections.length === 0 && !report) {
    return <p className="empty">Loading picture QC…</p>;
  }
  if (error && detections.length === 0 && !report) {
    return <div className="error-banner">{error}</div>;
  }

  const video = report?.video_metadata ?? null;
  const audio = report?.audio_metadata ?? null;
  const width = metaNumber(video, "FrameWidth");
  const height = metaNumber(video, "FrameHeight");
  const fps = metaNumber(video, "FrameRate");
  const codec = metaString(video, "Codec");
  const channels = metaNumber(audio, "NumberOfChannels");
  const audioCodec = metaString(audio, "Codec");
  const outcome = report?.summary.outcome ?? "pending";
  const hasEvidence =
    techCues.length + shots.length + moderation.length + labels.length + texts.length > 0;
  const hasReport = Boolean(report && (report.ready || report.findings.length || report.pending_features.length));

  if (!hasReport && !hasEvidence) {
    return (
      <p className="empty">
        No picture QC yet. Analyze the H.264 proxy, then drain the queue (or wait for the cron).
      </p>
    );
  }

  return (
    <div className="reko-results">
      <section className="reko-section">
        <div className="reko-report-head">
          <div>
            <h3>Picture QC report</h3>
            <p className="text-tertiary">
              H.264 proxy only. Findings are deterministic rules over Rekognition detections.
            </p>
          </div>
          <span className={`reko-outcome reko-outcome-${outcome}`}>{outcome}</span>
        </div>
        <div className="reko-report-stats">
          <span>
            <strong>{report?.summary.error ?? 0}</strong> errors
          </span>
          <span>
            <strong>{report?.summary.warning ?? 0}</strong> warnings
          </span>
          <span>
            <strong>{report?.summary.info ?? 0}</strong> info
          </span>
        </div>
        <dl className="reko-meta">
          <div>
            <dt>Video</dt>
            <dd className="mono">
              {[codec, width && height ? `${width}×${height}` : null, fps != null ? `${fps.toFixed(3)} fps` : null]
                .filter(Boolean)
                .join(" · ") || "—"}
            </dd>
          </div>
          <div>
            <dt>Audio</dt>
            <dd className="mono">
              {[audioCodec, channels != null ? `${channels} ch` : null].filter(Boolean).join(" · ") || "—"}
            </dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd className="mono">{formatTimecode(durationMs)}</dd>
          </div>
        </dl>
        {report?.pending_features.length ? (
          <p className="text-tertiary reko-empty-line">
            Waiting on {report.pending_features.join(", ")} before findings can close.
          </p>
        ) : null}
      </section>

      <section className="reko-section">
        <div className="reko-section-head">
          <FileSearch size={15} aria-hidden />
          <h3>Findings</h3>
          <span className="text-tertiary">{report?.findings.length ?? 0}</span>
        </div>
        {report?.findings.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Rule</th>
                <th>Message</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {report.findings.map((finding) => (
                <tr key={finding.sk}>
                  <td>
                    <span className={`reko-sev reko-sev-${finding.severity ?? "info"}`}>
                      {finding.severity ?? "info"}
                    </span>
                  </td>
                  <td className="mono">{finding.rule_id ?? finding.kind}</td>
                  <td>{finding.message ?? finding.name ?? "—"}</td>
                  <td>
                    {finding.start_ms != null ? (
                      <button
                        type="button"
                        className="reko-timecode-btn mono"
                        onClick={() => setFocusMs(finding.start_ms ?? null)}
                      >
                        {formatTimecode(finding.start_ms)}
                        {finding.end_ms != null && finding.end_ms !== finding.start_ms
                          ? `–${formatTimecode(finding.end_ms)}`
                          : ""}
                      </button>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-tertiary reko-empty-line">
            {report?.ready ? "No findings." : "Findings appear after segments, moderation, and text succeed."}
          </p>
        )}
      </section>

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
            {focusMs != null && (
              <span
                className="reko-timeline-focus"
                style={{ left: `${pct(focusMs, durationMs)}%` }}
                title={`Finding @ ${formatTimecode(focusMs)}`}
              />
            )}
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
                  <td className="mono">{d.start_timecode ?? formatTimecode(d.start_ms)}</td>
                  <td className="mono">{d.end_timecode ?? formatTimecode(d.end_ms)}</td>
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

      <section className="reko-section">
        <div className="reko-section-head">
          <AlertTriangle size={15} aria-hidden />
          <h3>Content moderation</h3>
          <span className="text-tertiary">
            {moderation.length} flag{moderation.length === 1 ? "" : "s"}
          </span>
        </div>
        {moderationGroups.length > 0 ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Category</th>
                <th className="num">Hits</th>
                <th>Implies ≥</th>
              </tr>
            </thead>
            <tbody>
              {moderationGroups.map(([category, group]) => (
                <tr key={category}>
                  <td>
                    <span className="reko-mod-chip">{category}</span>
                  </td>
                  <td className="num">{group.count}</td>
                  <td className="text-tertiary">{group.rating ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-tertiary reko-empty-line">No moderation flags.</p>
        )}
      </section>

      <section className="reko-section">
        <div className="reko-section-head">
          <Type size={15} aria-hidden />
          <h3>On-screen text</h3>
          <span className="text-tertiary">{texts.length}</span>
        </div>
        {texts.length > 0 ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Text</th>
                <th>Time</th>
                <th className="num">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {texts.slice(0, 80).map((row) => (
                <tr key={row.sk}>
                  <td>{row.name || "—"}</td>
                  <td className="mono">{formatTimecode(row.timestamp_ms)}</td>
                  <td className="num text-tertiary">{formatConfidence(row.confidence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-tertiary reko-empty-line">No on-screen text detected.</p>
        )}
        {texts.length > 80 && (
          <p className="text-tertiary reko-empty-line">Showing first 80 of {texts.length} lines.</p>
        )}
      </section>

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
