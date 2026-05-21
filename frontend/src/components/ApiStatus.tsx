import { useEffect, useState } from "react";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const IS_PROD = import.meta.env.PROD;

export function ApiStatus() {
  const [health, setHealth] = useState<"ok" | "error" | "loading" | "unset">(
    IS_PROD && !API_BASE ? "unset" : "loading"
  );
  const [metaHealth, setMetaHealth] = useState<string | null>(null);

  useEffect(() => {
    const healthUrl = API_BASE ? `${API_BASE}/health` : "/health";
    const metaUrl = API_BASE
      ? `${API_BASE}/api/v1/metadata/health`
      : "/api/v1/metadata/health";
    Promise.all([
      fetch(healthUrl).then((r) => (r.ok ? "ok" : "error")),
      fetch(metaUrl)
        .then((r) => r.json())
        .then((d: { ok?: boolean; message?: string }) =>
          d.ok ? "TMDB ok" : d.message ?? "TMDB unavailable"
        )
        .catch(() => "metadata check failed"),
    ])
      .then(([h, m]) => {
        setHealth(h === "ok" ? "ok" : "error");
        setMetaHealth(m);
      })
      .catch(() => setHealth("error"));
  }, []);

  if (!IS_PROD && !API_BASE) return null;

  if (health === "unset") {
    return (
      <div className="api-status api-status-error">
        <strong>API not configured</strong>
        <p>Set VITE_API_URL in Amplify and redeploy.</p>
      </div>
    );
  }

  return (
    <div className={`api-status api-status-${health}`}>
      <strong>API</strong>
      <p className="mono api-status-url">{API_BASE || "localhost (dev proxy)"}</p>
      {health === "loading" && <p>Checking…</p>}
      {health === "ok" && <p>Connected · {metaHealth}</p>}
      {health === "error" && (
        <p>Cannot reach API — deploy on Render and set VITE_API_URL in Amplify.</p>
      )}
    </div>
  );
}
