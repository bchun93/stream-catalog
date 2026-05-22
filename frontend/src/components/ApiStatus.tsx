import { useEffect, useState } from "react";
import { apiBaseUrl, titlesApi } from "../api/client";

const IS_PROD = import.meta.env.PROD;

export function ApiStatus() {
  const API_BASE = apiBaseUrl();
  const [health, setHealth] = useState<"ok" | "error" | "loading" | "unset">(
    IS_PROD && !API_BASE ? "unset" : "loading"
  );
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    const healthUrl = API_BASE ? `${API_BASE}/health` : "/health";
    const readyUrl = API_BASE ? `${API_BASE}/ready` : "/ready";

    Promise.all([
      fetch(healthUrl).then((r) => (r.ok ? "ok" : "error")),
      fetch(readyUrl)
        .then((r) => r.json())
        .then((d: { database?: string }) => d.database ?? "db?")
        .catch(() => "db unreachable"),
      titlesApi
        .list()
        .then((t) => `titles: ${t.length}`)
        .catch((e) => `titles failed: ${e instanceof Error ? e.message : "error"}`),
    ])
      .then(([h, db, titles]) => {
        setHealth(h === "ok" ? "ok" : "error");
        setDetail(`${db} · ${titles}`);
      })
      .catch(() => {
        setHealth("error");
        setDetail("API check failed");
      });
  }, [API_BASE]);

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
      {health === "ok" && detail && <p>Connected · {detail}</p>}
      {health === "error" && (
        <p>Cannot reach API — redeploy Render + Amplify from latest main.</p>
      )}
    </div>
  );
}
