import type {
  MediaAsset,
  MetadataSearchResult,
  Title,
  TitleMetadataImport,
  TitleTree,
  TitleType,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const API = `${API_BASE}/api/v1`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail =
      typeof err.detail === "string"
        ? err.detail
        : JSON.stringify(err.detail ?? err);
    if (res.status === 404 && detail === "Not Found") {
      throw new Error(
        "Metadata API not found. Restart the backend (uvicorn) after pulling latest code, and ensure it runs on port 8000."
      );
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const titlesApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<Title[]>(`/titles${q ? `?${q}` : ""}`);
  },
  tree: () => request<TitleTree[]>("/titles/tree"),
  get: (id: number) => request<Title>(`/titles/${id}`),
  create: (body: Partial<Title>) =>
    request<Title>("/titles", { method: "POST", body: JSON.stringify(body) }),
  update: (id: number, body: Partial<Title>) =>
    request<Title>(`/titles/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  delete: (id: number) =>
    request<void>(`/titles/${id}`, { method: "DELETE" }),
};

export const metadataApi = {
  search: (q: string, titleType?: TitleType) => {
    const params = new URLSearchParams({ q });
    if (titleType) params.set("title_type", titleType);
    return request<MetadataSearchResult[]>(`/metadata/search?${params}`);
  },
  import: (externalId: string) =>
    request<TitleMetadataImport>(
      `/metadata/import/${encodeURIComponent(externalId)}`
    ),
};

export const assetsApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<MediaAsset[]>(`/assets${q ? `?${q}` : ""}`);
  },
  get: (id: number) => request<MediaAsset>(`/assets/${id}`),
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
