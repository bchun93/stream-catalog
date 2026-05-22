import { useEffect, useState } from "react";
import { apiBaseUrl, diagnosticsApi } from "../api/client";

const IS_PROD = import.meta.env.PROD;

export function ApiStatus() {
  const API_BASE = apiBaseUrl();
  const [health, setHealth] = useState<"ok" | "error" | "loading" | "unset">(
    IS_PROD && !API_BASE ? "unset" : "loading"
  );
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    if (!API_BASE) return;

    diagnosticsApi
      .get()
      .then((d) => {
        const ok =
          d.db_ready &&
          !d.titles_error &&
          (d.titles_count !== null || d.database_driver === "sqlite");
        setHealth(ok ? "ok" : "error");
        const parts = [
          d.db_ready ? "db ok" : "db not ready",
          d.tmdb_configured ? "tmdb ok" : "tmdb missing",
        ];
        if (d.titles_count !== null) parts.push(`titles: ${d.titles_count}`);
        if (d.titles_error) parts.push(`titles err: ${d.titles_error.slice(0, 60)}`);
        if (d.neon_pooler) parts.push("neon pooler URL");
        if (d.migration_error) parts.push(`migrate: ${d.migration_error.slice(0, 50)}`);
        setDetail(parts.join(" · "));
        if (!ok && d.hints.length > 0) {
          setDetail((prev) => `${prev}\n${d.hints[0]}`);
        }
      })
      .catch((e) => {
        setHealth("error");
        const msg = e instanceof Error ? e.message : "diagnostics failed";
        setDetail(
          `${msg}\nIf health works in browser but this fails, redeploy Amplify (VITE_API_URL is baked at build).`
        );
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
      {health === "loading" && <p>Checking server…</p>}
      {health === "ok" && detail && <p>Connected · {detail}</p>}
      {health === "error" && (
        <>
          <p>Server mismatch or not ready — see detail below.</p>
          {detail && <p style={{ fontSize: "0.75rem", whiteSpace: "pre-wrap" }}>{detail}</p>}
        </>
      )}
    </div>
  );
}
