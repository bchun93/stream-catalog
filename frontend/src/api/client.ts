import { filterArtworkAssets } from "../utils/artworkTypes";
import type {
  ArtworkItem,
  ArtworkAutoAssignResponse,
  ArtworkClassifyResponse,
  ArtworkLabelRequest,
  ArtworkTrainingExample,
  IngestJob,
  IngestManifest,
  IngestManifestValidateResponse,
  MediaAsset,
  MetadataConfig,
  MetadataDisplaySettings,
  MetadataSearchResult,
  SeriesHierarchyApplyResult,
  SeriesHierarchyPreview,
  StorageBrowse,
  StorageConfig,
  StoragePresignDownload,
  StoragePresignUpload,
  Title,
  TitleMetadataImport,
  TitleTree,
  TitleType,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const API = `${API_BASE}/api/v1`;
const IS_PROD = import.meta.env.PROD;
const REQUEST_TIMEOUT_MS = IS_PROD ? 90000 : 30000;
/** Per-attempt cap while waking Render — avoids hanging on one 90s timeout. */
const WAKE_ATTEMPT_TIMEOUT_MS = IS_PROD ? 12000 : 8000;
const WAKE_POLL_INTERVAL_MS = 2000;
const WAKE_MAX_ATTEMPTS = IS_PROD ? 25 : 8;
const INGEST_OPERATOR_TOKEN = (
  import.meta.env.VITE_INGEST_OPERATOR_TOKEN as string | undefined
)?.trim();

function rootUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return API_BASE ? `${API_BASE}${normalized}` : normalized;
}

export type ApiHealth = {
  status: string;
  tmdb_configured?: boolean;
};

export type ApiWakeState = {
  waking: boolean;
  ready: boolean;
  error: boolean;
  tmdbConfigured?: boolean;
};

let warmPromise: Promise<ApiHealth> | null = null;

function shouldWarmApi(): boolean {
  return IS_PROD && Boolean(API_BASE);
}

async function pingRoot(
  path: string,
  attempts = WAKE_MAX_ATTEMPTS,
  timeoutMs = WAKE_ATTEMPT_TIMEOUT_MS
): Promise<Response> {
  const url = rootUrl(path);
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal });
      if (res.ok) return res;
      last = new Error(`HTTP ${res.status}`);
      // 502/503 while the container is still booting — keep polling.
      if (res.status < 500) throw last;
    } catch (err) {
      last = err;
      const msg = err instanceof Error ? err.message : "";
      const retryable =
        msg.includes("aborted") ||
        msg.includes("Failed to fetch") ||
        msg.includes("Load failed") ||
        msg.includes("NetworkError") ||
        msg.includes("HTTP 5");
      if (!retryable || i === attempts - 1) throw err;
    } finally {
      clearTimeout(timeout);
    }
    await new Promise((r) => setTimeout(r, WAKE_POLL_INTERVAL_MS));
  }
  throw last instanceof Error ? last : new Error("Request failed");
}

/** Lightweight root /health — used for wake-up and sidebar status. */
export async function pingHealth(
  attempts = WAKE_MAX_ATTEMPTS
): Promise<ApiHealth> {
  const res = await pingRoot("/health", attempts);
  if (!res.ok) {
    throw new Error(`Health check failed (${res.status})`);
  }
  return res.json() as Promise<ApiHealth>;
}

/** Single shared warm-up before API v1 requests (Render free tier). */
export function ensureApiWarm(): Promise<ApiHealth> {
  if (!shouldWarmApi()) {
    return Promise.resolve({ status: "ok" });
  }
  if (!warmPromise) {
    warmPromise = pingHealth();
  }
  return warmPromise;
}

function operatorHeaders(): HeadersInit {
  return INGEST_OPERATOR_TOKEN ? { "X-Ingest-Token": INGEST_OPERATOR_TOKEN } : {};
}

function isArtworkRouteDatabaseError(message: string): boolean {
  const text = message.toLowerCase();
  return (
    text.includes("database error") ||
    text.includes("database_url") ||
    text.includes("db not ready")
  );
}

function friendlySkippedArtworkMessage(count: number): string {
  const plural = count === 1 ? "" : "s";
  return (
    `Saved what the current API schema supports, but skipped ${count} selected ` +
    `image${plural}. Redeploy API migrations to enable all artwork types.`
  );
}

function catalogSafeArtworkType(): "poster" {
  // Some deployed databases still have legacy enum constraints. Store selected
  // image artwork under the stable poster type and preserve its role in specs.
  return "poster";
}

function artworkMetadataJson(item: ArtworkItem): string {
  return JSON.stringify({
    notes: item.notes ?? null,
    specs: item.specs ?? {},
  });
}

function buildHeaders(init?: RequestInit): HeadersInit {
  const headers = new Headers(init?.headers);
  const method = (init?.method ?? "GET").toUpperCase();
  const hasBody = init?.body != null && method !== "GET" && method !== "HEAD";
  // Do not set Content-Type on GET — it triggers CORS preflight and breaks Amplify → Render.
  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (IS_PROD && !API_BASE) {
    throw new Error(
      "API URL not configured. In Amplify, set VITE_API_URL to your Render API URL and redeploy."
    );
  }
  const url = `${API}${path}`;
  let res: Response;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    res = await fetch(url, {
      ...init,
      signal: init?.signal ?? controller.signal,
      headers: buildHeaders(init),
    });
  } catch (err) {
    if (controller.signal.aborted) {
      throw new Error(
        `Request timed out after ${Math.round(
          REQUEST_TIMEOUT_MS / 1000
        )}s reaching ${url}. The API may be waking up; retrying usually fixes this.`
      );
    }
    const hint =
      err instanceof TypeError
        ? ` Network error reaching ${url}. Check VITE_API_URL (${API_BASE || "not set"}) and retry (Render may be temporarily unreachable).`
        : "";
    throw new Error(
      `${err instanceof Error ? err.message : "Request failed"}${hint}`
    );
  } finally {
    clearTimeout(timeout);
  }
  if (!res.ok) {
    const raw = await res.text().catch(() => "");
    let detail = res.statusText || `HTTP ${res.status}`;
    if (raw) {
      try {
        const err = JSON.parse(raw) as { detail?: unknown };
        detail =
          typeof err.detail === "string"
            ? err.detail
            : err.detail != null
              ? JSON.stringify(err.detail)
              : raw.slice(0, 300);
      } catch {
        detail = raw.slice(0, 300) || detail;
      }
    }
    if (res.status === 404 && detail === "Not Found") {
      if (path.includes("/metadata/hierarchy/")) {
        throw new Error(
          "Hierarchy preview is not available on this API yet. Deploy the latest Render backend or run the local backend with Python 3.10+."
        );
      }
      throw new Error(
        "API route not found. Redeploy Render from latest main and verify /api/v1 is live."
      );
    }
    if (detail === "Internal Server Error" && res.status >= 500) {
      const hint = path.includes("/metadata")
        ? `Check TMDB_API_KEY on Render and open ${API}/metadata/health`
        : `Redeploy Render from latest main and open ${API}/diagnostics`;
      throw new Error(`API error (${res.status}). ${hint}`);
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Retry cold-start / transient failures (Render free tier). */
async function requestWithRetry<T>(
  path: string,
  init?: RequestInit,
  attempts = 4
): Promise<T> {
  if (shouldWarmApi()) {
    try {
      await ensureApiWarm();
    } catch {
      // Fall through — per-request retries still apply.
    }
  }
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await request<T>(path, init);
    } catch (e) {
      last = e;
      const msg = e instanceof Error ? e.message : "";
      const retryable =
        msg.includes("Network error") ||
        msg.includes("Failed to fetch") ||
        msg.includes("Load failed") ||
        msg.includes("timed out") ||
        msg.includes("aborted") ||
        msg.includes("503") ||
        msg.includes("Database not") ||
        msg.includes("Database error") ||
        msg.includes("db not ready");
      if (!retryable || i === attempts - 1) throw e;
      await new Promise((r) => setTimeout(r, 1500 * (i + 1)));
    }
  }
  throw last;
}

export const titlesApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return requestWithRetry<Title[]>(`/titles${q ? `?${q}` : ""}`);
  },
  tree: () => requestWithRetry<TitleTree[]>("/titles/tree"),
  get: (id: number) => requestWithRetry<Title>(`/titles/${id}`),
  create: (body: Partial<Title>) =>
    request<Title>("/titles", { method: "POST", body: JSON.stringify(body) }),
  update: (id: number, body: Partial<Title>) =>
    request<Title>(`/titles/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  delete: (id: number) =>
    request<void>(`/titles/${id}`, { method: "DELETE" }),
  listArtwork: async (id: number) => {
    try {
      const list = await requestWithRetry<MediaAsset[]>(`/titles/${id}/artwork`);
      return filterArtworkAssets(list);
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      const missing =
        message.includes("Not Found") ||
        message.includes("404") ||
        message.includes("route not found");
      const dbFailure = isArtworkRouteDatabaseError(message);
      if (!missing && !dbFailure) throw err;
      const fallbackAssets = await requestWithRetry<MediaAsset[]>(
        `/assets?title_id=${id}`,
        undefined,
        8
      );
      return filterArtworkAssets(fallbackAssets);
    }
  },
  syncArtwork: (id: number) =>
    requestWithRetry<MediaAsset[]>(`/titles/${id}/artwork/sync`, {
      method: "POST",
    }).then(filterArtworkAssets),
  artworkDownloadUrl: (titleId: number, assetId: number) =>
    `${API}/titles/${titleId}/artwork/${assetId}/download`,
  saveArtwork: (id: number, items: ArtworkItem[]) =>
    request<MediaAsset[]>(`/titles/${id}/artwork`, {
      method: "POST",
      body: JSON.stringify({
        items: items.map((item) => ({
          asset_type: catalogSafeArtworkType(),
          storage_uri: item.storage_uri,
          filename: item.filename,
          mime_type: item.mime_type ?? "image/jpeg",
          language: item.language ?? null,
          resolution: item.resolution ?? null,
          notes: item.notes ?? null,
          specs: item.specs ?? {},
        })),
      }),
    })
      .then(filterArtworkAssets)
      .catch(async (err: unknown) => {
        const message = err instanceof Error ? err.message : "";
        if (!isArtworkRouteDatabaseError(message)) {
          throw err;
        }

        const existing = await requestWithRetry<MediaAsset[]>(
          `/assets?title_id=${id}`,
          undefined,
          8
        );
        const existingUris = new Set(existing.map((asset) => asset.storage_uri));
        const toCreate = items.filter((item) => !existingUris.has(item.storage_uri));
        let skipped = 0;
        let created = 0;

        for (const item of toCreate) {
          try {
            await request<MediaAsset>("/assets", {
              method: "POST",
              body: JSON.stringify({
                title_id: id,
                asset_type: catalogSafeArtworkType(),
                status: "ready",
                filename: item.filename,
                mime_type: item.mime_type ?? "image/jpeg",
                storage_uri: item.storage_uri,
                language: item.language ?? null,
                resolution: item.resolution ?? null,
                notes: item.notes ?? null,
                metadata_json: artworkMetadataJson(item),
              }),
            });
            created += 1;
          } catch (createErr) {
            const createMessage =
              createErr instanceof Error ? createErr.message : "";
            if (!isArtworkRouteDatabaseError(createMessage)) {
              throw createErr;
            }
            skipped += 1;
          }
        }

        const refreshed = await requestWithRetry<MediaAsset[]>(
          `/assets?title_id=${id}`,
          undefined,
          8
        );
        if (created === 0 && skipped > 0) {
          throw new Error(friendlySkippedArtworkMessage(skipped));
        }
        return filterArtworkAssets(refreshed);
      }),
};

export type MetadataHealth = {
  ok: boolean;
  message: string;
  tmdb_configured?: boolean;
};

export type ApiDiagnostics = {
  status: string;
  db_ready: boolean;
  database_driver: string;
  database_host: string | null;
  neon_pooler: boolean;
  migration_error: string | null;
  tmdb_configured: boolean;
  titles_count: number | null;
  titles_error: string | null;
  hints: string[];
};

export const diagnosticsApi = {
  get: () => requestWithRetry<ApiDiagnostics>("/diagnostics"),
};

export const metadataConfigApi = {
  get: () => requestWithRetry<MetadataConfig>("/metadata-config"),
  update: (settings: MetadataDisplaySettings) =>
    request<MetadataConfig>("/metadata-config", {
      method: "PUT",
      body: JSON.stringify({ settings }),
    }),
};

export const metadataApi = {
  health: () => requestWithRetry<MetadataHealth>("/metadata/health"),
  search: (q: string, titleType?: TitleType) => {
    const params = new URLSearchParams({ q });
    if (titleType) params.set("title_type", titleType);
    return requestWithRetry<MetadataSearchResult[]>(`/metadata/search?${params}`);
  },
  import: (externalId: string) =>
    requestWithRetry<TitleMetadataImport>(
      `/metadata/import/${encodeURIComponent(externalId)}`
    ),
  hierarchyPreview: (externalId: string) =>
    requestWithRetry<SeriesHierarchyPreview>(
      `/metadata/hierarchy/preview?${new URLSearchParams({ external_id: externalId })}`
    ),
  applyHierarchy: (externalId: string) =>
    requestWithRetry<SeriesHierarchyApplyResult>(
      `/metadata/hierarchy/apply?${new URLSearchParams({ external_id: externalId })}`,
      { method: "POST" }
    ),
  importArtwork: async (externalId: string) => {
    const params = new URLSearchParams({ external_id: externalId });
    try {
      return await requestWithRetry<ArtworkItem[]>(`/metadata/artwork?${params}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      if (!message.includes("Not Found") && !message.includes("404")) {
        throw err;
      }
      return requestWithRetry<ArtworkItem[]>(
        `/metadata/import/${encodeURIComponent(externalId)}/artwork`
      );
    }
  },
};

export const artworkAiApi = {
  classify: (titleId: number, threshold = 0.9) =>
    requestWithRetry<ArtworkClassifyResponse>(
      `/titles/${titleId}/artwork/classify?${new URLSearchParams({
        threshold: String(threshold),
      })}`,
      { method: "POST" }
    ),
  autoAssign: (titleId: number, threshold = 0.9) =>
    requestWithRetry<ArtworkAutoAssignResponse>(
      `/titles/${titleId}/artwork/auto-assign`,
      {
        method: "POST",
        body: JSON.stringify({ threshold }),
      },
      8
    ).then((response) => ({
      ...response,
      assets: filterArtworkAssets(response.assets),
    })),
  label: (body: ArtworkLabelRequest) =>
    request<ArtworkTrainingExample>("/artwork-ai/labels", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listTraining: () =>
    requestWithRetry<ArtworkTrainingExample[]>("/artwork-ai/training"),
};

export const assetsApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return requestWithRetry<MediaAsset[]>(`/assets${q ? `?${q}` : ""}`);
  },
  get: (id: number) => requestWithRetry<MediaAsset>(`/assets/${id}`),
  create: (body: Partial<MediaAsset>) =>
    request<MediaAsset>("/assets", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: number, body: Partial<MediaAsset>) =>
    request<MediaAsset>(`/assets/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  delete: (id: number) =>
    request<void>(`/assets/${id}`, { method: "DELETE" }),
};

function operatorRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(operatorHeaders())) {
    headers.set(key, value);
  }
  return requestWithRetry<T>(path, { ...init, headers });
}

export const ingestApi = {
  listManifests: (enabledOnly = true) =>
    operatorRequest<IngestManifest[]>(
      `/ingest/manifests?enabled_only=${enabledOnly ? "true" : "false"}`
    ),
  validateManifest: (body: {
    manifest_id: number;
    source_prefix?: string;
    max_keys?: number;
  }) =>
    operatorRequest<IngestManifestValidateResponse>("/ingest/manifests/validate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createJob: (body: {
    title_id: number;
    manifest_id: number;
    source_prefix?: string;
    created_by?: string;
    dry_run?: boolean;
    max_keys?: number;
  }) =>
    operatorRequest<IngestJob>("/ingest/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listJobs: (params?: { title_id?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.title_id) q.set("title_id", String(params.title_id));
    if (params?.limit) q.set("limit", String(params.limit));
    return operatorRequest<IngestJob[]>(`/ingest/jobs${q.toString() ? `?${q}` : ""}`);
  },
  getJob: (id: number) => operatorRequest<IngestJob>(`/ingest/jobs/${id}`),
};

export const storageApi = {
  getConfig: () => operatorRequest<StorageConfig>("/storage/config"),
  browse: (prefix = "", maxKeys = 500) => {
    const q = new URLSearchParams();
    if (prefix) q.set("prefix", prefix);
    q.set("max_keys", String(maxKeys));
    return operatorRequest<StorageBrowse>(`/storage/browse?${q}`);
  },
  presignUpload: (body: { prefix?: string; filename: string; content_type?: string }) =>
    operatorRequest<StoragePresignUpload>("/storage/presign-upload", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  presignDownload: (key: string) =>
    operatorRequest<StoragePresignDownload>(
      `/storage/presign-download?${new URLSearchParams({ key })}`
    ),
};

export function apiBaseUrl(): string {
  return API_BASE;
}
