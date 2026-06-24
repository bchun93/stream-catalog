import { Loader2 } from "lucide-react";
import { useApiWake } from "../context/ApiWakeContext";

export function ApiWakeBanner() {
  const { waking, error } = useApiWake();

  if (!waking && !error) return null;

  return (
    <div
      className={`api-wake-banner${error ? " api-wake-banner-error" : ""}`}
      role="status"
      aria-live="polite"
    >
      {waking ? (
        <>
          <Loader2 size={16} className="api-wake-banner-icon" aria-hidden />
          <span>
            Connecting to API — free hosting may take up to 30 seconds on first
            load.
          </span>
        </>
      ) : (
        <span>
          Could not reach the API. It may still be waking up — try refreshing
          in a moment.
        </span>
      )}
    </div>
  );
}
