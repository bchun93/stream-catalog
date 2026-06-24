import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ensureApiWarm, type ApiWakeState } from "../api/client";

const ApiWakeContext = createContext<ApiWakeState | null>(null);

export function ApiWakeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ApiWakeState>(() => ({
    waking: import.meta.env.PROD && Boolean(import.meta.env.VITE_API_URL),
    ready: !(import.meta.env.PROD && import.meta.env.VITE_API_URL),
    error: false,
    tmdbConfigured: undefined,
  }));

  useEffect(() => {
    let cancelled = false;

    ensureApiWarm()
      .then((health) => {
        if (cancelled) return;
        setState({
          waking: false,
          ready: true,
          error: false,
          tmdbConfigured: health.tmdb_configured,
        });
      })
      .catch(() => {
        if (cancelled) return;
        setState((prev) => ({
          ...prev,
          waking: false,
          ready: false,
          error: true,
        }));
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => state, [state]);

  return (
    <ApiWakeContext.Provider value={value}>{children}</ApiWakeContext.Provider>
  );
}

export function useApiWake(): ApiWakeState {
  const ctx = useContext(ApiWakeContext);
  if (!ctx) {
    throw new Error("useApiWake must be used within ApiWakeProvider");
  }
  return ctx;
}
