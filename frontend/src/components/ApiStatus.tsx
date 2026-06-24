import { useApiWake } from "../context/ApiWakeContext";

const IS_PROD = import.meta.env.PROD;

export function ApiStatus() {
  const { waking, ready, error, tmdbConfigured } = useApiWake();
  const apiConfigured = IS_PROD ? Boolean(import.meta.env.VITE_API_URL) : true;

  if (!IS_PROD && !import.meta.env.VITE_API_URL) return null;

  const health = !apiConfigured
    ? "unset"
    : waking
      ? "loading"
      : error
        ? "error"
        : ready
          ? "ok"
          : "loading";

  const label =
    health === "loading"
      ? "Connecting…"
      : health === "ok"
        ? tmdbConfigured === false
          ? "Connected · TMDB off"
          : "Connected"
        : health === "unset"
          ? "API not configured"
          : "Unreachable";

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
