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
        const parts: string[] = [];
        if (d.titles_count !== null) parts.push(`${d.titles_count} titles`);
        if (!d.tmdb_configured) parts.push("TMDB off");
        setDetail(parts.join(" · ") || "Connected");
      })
      .catch(() => {
        setHealth("error");
        setDetail("Unreachable");
      });
  }, [API_BASE]);

  if (!IS_PROD && !API_BASE) return null;

  const label =
    health === "loading"
      ? "Connecting…"
      : health === "ok"
        ? detail ?? "Connected"
        : health === "unset"
          ? "API not configured"
          : detail ?? "Connection issue";

  return (
    <div className={`api-status api-status-${health}`}>
      <strong>
        <span className="api-status-dot" aria-hidden />
        API
      </strong>
      <p>{label}</p>
    </div>
  );
}
