export type TitleType = "movie" | "series" | "season" | "episode";
export type TitleStatus =
  | "draft"
  | "in_review"
  | "scheduled"
  | "published"
  | "archived";

export type AssetType =
  | "video_master"
  | "trailer"
  | "poster"
  | "thumbnail"
  | "subtitle"
  | "audio"
  | "caption";

export type AssetStatus =
  | "uploaded"
  | "processing"
  | "ready"
  | "failed"
  | "archived";

export interface Title {
  id: number;
  slug: string;
  name: string;
  title_type: TitleType;
  status: TitleStatus;
  synopsis?: string | null;
  short_description?: string | null;
  release_date?: string | null;
  rating?: string | null;
  genres?: string | null;
  territories?: string | null;
  availability_start?: string | null;
  availability_end?: string | null;
  parent_id?: number | null;
  season_number?: number | null;
  episode_number?: number | null;
  runtime_minutes?: number | null;
  created_at: string;
  updated_at: string;
}

export interface TitleTree extends Title {
  children: TitleTree[];
}

export interface MediaAsset {
  id: number;
  title_id: number;
  asset_type: AssetType;
  status: AssetStatus;
  filename: string;
  mime_type?: string | null;
  storage_uri: string;
  size_bytes?: number | null;
  checksum?: string | null;
  language?: string | null;
  resolution?: string | null;
  duration_seconds?: number | null;
  codec?: string | null;
  version: number;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}
