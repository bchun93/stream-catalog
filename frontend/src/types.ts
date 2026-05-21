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
  | "backdrop"
  | "logo"
  | "still"
  | "cast_photo"
  | "season_poster"
  | "thumbnail"
  | "subtitle"
  | "audio"
  | "caption";

export type ArtworkType =
  | "poster"
  | "backdrop"
  | "logo"
  | "still"
  | "cast_photo"
  | "season_poster";

export interface ArtworkItem {
  asset_type: ArtworkType;
  storage_uri: string;
  filename: string;
  mime_type?: string | null;
  language?: string | null;
  resolution?: string | null;
  notes?: string | null;
}

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
  release_year?: number | null;
  rating?: string | null;
  genres?: string | null;
  territories?: string | null;
  availability_start?: string | null;
  availability_end?: string | null;
  licensor?: string | null;
  studio?: string | null;
  cast?: string | null;
  crew?: string | null;
  external_id?: string | null;
  metadata_source?: string | null;
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

export interface MetadataSearchResult {
  external_id: string;
  source: string;
  media_type: string;
  title_type: TitleType;
  name: string;
  release_year?: number | null;
  overview?: string | null;
  poster_url?: string | null;
}

export interface TitleMetadataImport {
  source: string;
  external_id: string;
  media_type: string;
  title_type: TitleType;
  name: string;
  slug?: string | null;
  synopsis?: string | null;
  short_description?: string | null;
  release_date?: string | null;
  release_year?: number | null;
  rating?: string | null;
  genres?: string | null;
  runtime_minutes?: number | null;
  studio?: string | null;
  licensor?: string | null;
  cast?: string | null;
  crew?: string | null;
  poster_url?: string | null;
  artwork?: ArtworkItem[];
}

export const ARTWORK_TYPES: ArtworkType[] = [
  "poster",
  "backdrop",
  "logo",
  "still",
  "cast_photo",
  "season_poster",
];

export const ARTWORK_LABELS: Record<ArtworkType, string> = {
  poster: "Posters",
  backdrop: "Backdrops",
  logo: "Logos",
  still: "Stills",
  cast_photo: "Cast photos",
  season_poster: "Season posters",
};
