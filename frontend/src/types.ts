export type TitleType = "movie" | "series" | "season" | "episode";
export type TitleStatus =
  | "draft"
  | "in_review"
  | "scheduled"
  | "published"
  | "archived";

export type MetadataDisplaySettings = Record<TitleType, string[]>;

export interface MetadataConfig {
  key: string;
  settings: MetadataDisplaySettings;
  defaults: MetadataDisplaySettings;
  updated_at?: string | null;
}

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

export interface ArtworkSpecs {
  width?: number | null;
  height?: number | null;
  aspect_ratio?: number | null;
  aspect_ratio_label?: string | null;
  resolution?: string | null;
  language?: string | null;
  country?: string | null;
  vote_average?: number | null;
  vote_count?: number | null;
  label?: string | null;
}

export interface ArtworkItem {
  asset_type: ArtworkType;
  storage_uri: string;
  filename: string;
  mime_type?: string | null;
  language?: string | null;
  resolution?: string | null;
  notes?: string | null;
  specs?: ArtworkSpecs;
}

export type ArtworkRole =
  | "vertical_poster"
  | "box_art"
  | "hero_image"
  | "horizontal_poster"
  | "still_frame"
  | "logo"
  | "season_poster"
  | "cast_photo"
  | "unknown";

export type ArtworkTrainingDecision = "approved" | "corrected" | "rejected";

export interface ArtworkPrediction {
  item: ArtworkItem;
  predicted_role: ArtworkRole;
  confidence: number;
  model_version: string;
  auto_apply: boolean;
  rationale?: string | null;
}

export interface ArtworkClassifyResponse {
  title_id: number;
  threshold: number;
  predictions: ArtworkPrediction[];
}

export interface ArtworkAutoAssignResponse {
  title_id: number;
  threshold: number;
  saved_count: number;
  review_count: number;
  assets: MediaAsset[];
  predictions: ArtworkPrediction[];
}

export interface ArtworkLabelRequest {
  title_id?: number | null;
  item: ArtworkItem;
  assigned_role: ArtworkRole;
  decision: ArtworkTrainingDecision;
  reviewer?: string | null;
  notes?: string | null;
}

export interface ArtworkTrainingExample {
  id: number;
  title_id?: number | null;
  candidate_uri: string;
  filename?: string | null;
  source_asset_type?: ArtworkType | null;
  assigned_role: ArtworkRole;
  decision: ArtworkTrainingDecision;
  reviewer?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export type AssetStatus =
  | "uploaded"
  | "processing"
  | "ready"
  | "failed"
  | "archived";

export interface Title {
  id: number;
  internal_id?: string | null;
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
  eidr?: string | null;
  external_id?: string | null;
  metadata_source?: string | null;
  metadata_json?: string | null;
  parent_id?: number | null;
  season_number?: number | null;
  episode_number?: number | null;
  runtime_minutes?: number | null;
  poster_url?: string | null;
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
  metadata_json?: string | null;
  specs?: ArtworkSpecs | null;
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

export type IngestJobStatus = "pending" | "running" | "completed" | "failed";
export type IngestItemStatus = "discovered" | "skipped" | "ingested" | "failed";

export interface IngestManifestRule {
  name?: string | null;
  pattern: string;
  use_regex?: boolean;
  asset_type: AssetType;
  status?: AssetStatus;
  language?: string | null;
  resolution?: string | null;
  mime_type?: string | null;
  notes?: string | null;
}

export interface IngestManifest {
  id: number;
  name: string;
  version: number;
  description?: string | null;
  enabled: boolean;
  rules: IngestManifestRule[];
  created_at: string;
  updated_at: string;
}

export interface IngestItemPreview {
  s3_key: string;
  filename: string;
  inferred_asset_type?: AssetType | null;
  language?: string | null;
  resolution?: string | null;
  matched_rule?: string | null;
  media_info?: Record<string, unknown> | null;
  warnings: string[];
}

export interface IngestManifestValidateResponse {
  manifest_id: number;
  source_prefix: string;
  discovered_count: number;
  matched_count: number;
  skipped_count: number;
  items: IngestItemPreview[];
}

export interface IngestItem {
  id: number;
  s3_key: string;
  filename: string;
  inferred_asset_type?: AssetType | null;
  status: IngestItemStatus;
  error_message?: string | null;
  resulting_asset_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface IngestJob {
  id: number;
  title_id: number;
  manifest_id?: number | null;
  source_prefix: string;
  status: IngestJobStatus;
  dry_run: boolean;
  created_by?: string | null;
  error_message?: string | null;
  discovered_count: number;
  ingested_count: number;
  skipped_count: number;
  failed_count: number;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
  items?: IngestItem[] | null;
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
  core_metadata?: Record<string, string | null>;
  artwork?: ArtworkItem[];
}

export interface EpisodeHierarchyPreview {
  external_id: string;
  name: string;
  slug: string;
  season_number: number;
  episode_number: number;
  synopsis?: string | null;
  release_date?: string | null;
  runtime_minutes?: number | null;
  still_url?: string | null;
  core_metadata: Record<string, string | null>;
  existing_title_id?: number | null;
  action: "create" | "update";
}

export interface SeasonHierarchyPreview {
  external_id: string;
  name: string;
  slug: string;
  season_number: number;
  synopsis?: string | null;
  release_date?: string | null;
  poster_url?: string | null;
  episode_count: number;
  core_metadata: Record<string, string | null>;
  episodes: EpisodeHierarchyPreview[];
  existing_title_id?: number | null;
  action: "create" | "update";
}

export interface SeriesHierarchyPreview {
  external_id: string;
  name: string;
  slug: string;
  synopsis?: string | null;
  short_description?: string | null;
  release_date?: string | null;
  release_year?: number | null;
  rating?: string | null;
  genres?: string | null;
  runtime_minutes?: number | null;
  studio?: string | null;
  cast?: string | null;
  crew?: string | null;
  poster_url?: string | null;
  core_metadata: Record<string, string | null>;
  seasons: SeasonHierarchyPreview[];
  season_count: number;
  episode_count: number;
  existing_title_id?: number | null;
  action: "create" | "update";
}

export interface SeriesHierarchyApplyResult {
  series: Title;
  season_count: number;
  episode_count: number;
  created_count: number;
  updated_count: number;
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
