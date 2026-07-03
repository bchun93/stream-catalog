export function formatBytes(n?: number | null): string {
  if (!n) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} KB`;
  return `${n} B`;
}

/** Milliseconds -> timecode, e.g. 5000 -> "0:05", 3723000 -> "1:02:03". */
export function formatTimecode(ms?: number | null): string {
  if (ms == null || ms < 0) return "—";
  const totalSeconds = Math.floor(ms / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const ss = String(s).padStart(2, "0");
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${ss}`;
  return `${m}:${ss}`;
}

/** Confidence (0–100) -> "95.0%". */
export function formatConfidence(value?: number | null): string {
  if (value == null) return "—";
  return `${value.toFixed(1)}%`;
}

export function truncateMiddle(text: string, max = 36): string {
  if (text.length <= max) return text;
  const head = Math.ceil((max - 1) / 2);
  const tail = Math.floor((max - 1) / 2);
  return `${text.slice(0, head)}…${text.slice(-tail)}`;
}
