import { filterArtworkAssets } from "../utils/artworkTypes";
import type {
  ArtworkItem,
  MediaAsset,
  MetadataSearchResult,
  Title,
  TitleMetadataImport,
  TitleTree,
  TitleType,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const API = `${API_BASE}/api/v1`;
const IS_PROD = import.meta.env.PROD;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (IS_PROD && !API_BASE) {
    throw new Error(
      "API URL not configured. In Amplify, set VITE_API_URL to your Render API URL and redeploy."
    );
  }
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
  listArtwork: async (id: number) => {
    try {
      const list = await request<MediaAsset[]>(`/titles/${id}/artwork`);
      return filterArtworkAssets(list);
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      const missing =
        message.includes("Not Found") ||
        message.includes("404") ||
        message.includes("Metadata API not found");
      if (!missing) throw err;
      const assets = await request<MediaAsset[]>(`/assets?title_id=${id}`);
      return filterArtworkAssets(assets);
    }
  },
  saveArtwork: (id: number, items: ArtworkItem[]) =>
    request<MediaAsset[]>(`/titles/${id}/artwork`, {
      method: "POST",
      body: JSON.stringify({
        items: items.map((item) => ({
          asset_type: item.asset_type,
          storage_uri: item.storage_uri,
          filename: item.filename,
          mime_type: item.mime_type ?? "image/jpeg",
          language: item.language ?? null,
          resolution: item.resolution ?? null,
          notes: item.notes ?? null,
          specs: item.specs ?? {},
        })),
      }),
    }).then(filterArtworkAssets),
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
  importArtwork: async (externalId: string) => {
    const params = new URLSearchParams({ external_id: externalId });
    try {
      return await request<ArtworkItem[]>(`/metadata/artwork?${params}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      if (!message.includes("Not Found") && !message.includes("404")) {
        throw err;
      }
      return request<ArtworkItem[]>(
        `/metadata/import/${encodeURIComponent(externalId)}/artwork`
      );
    }
  },
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
