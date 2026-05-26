export interface MetadataRequirementField {
  key: string;
  label: string;
  multiline?: boolean;
}

export const METADATA_REQUIREMENT_FIELDS: MetadataRequirementField[] = [
  { key: "content_type", label: "Content type" },
  { key: "movie_ref", label: "Movie ref" },
  { key: "series_ref", label: "Series ref" },
  { key: "season_ref", label: "Season ref" },
  { key: "reference_id", label: "Reference ID" },
  { key: "name", label: "Name" },
  { key: "synopsis", label: "Synopsis", multiline: true },
  { key: "short_synopsis", label: "Short synopsis", multiline: true },
  { key: "season_count", label: "Season count" },
  { key: "season_number", label: "Season number" },
  { key: "episode_count", label: "Episode count" },
  { key: "episode_no", label: "Episode no" },
  { key: "copyright_line", label: "Copyright line" },
  { key: "rating", label: "Rating" },
  { key: "advisory", label: "Advisory", multiline: true },
  { key: "release_date", label: "Release date (MM/DD/YYYY)" },
  { key: "initial_release_year", label: "Initial release year" },
  { key: "latest_release_year", label: "Latest release year" },
  { key: "runtime", label: "Runtime (minutes)" },
  { key: "studio", label: "Studio", multiline: true },
  { key: "genre", label: "Genre", multiline: true },
  { key: "language", label: "Language (ISO 639-1)" },
  { key: "origin", label: "Origin (ISO 3166-1)", multiline: true },
  { key: "actors", label: "Actors", multiline: true },
  { key: "directors", label: "Directors", multiline: true },
  { key: "writers", label: "Writers", multiline: true },
  { key: "creators", label: "Creators", multiline: true },
  { key: "producers", label: "Producers", multiline: true },
  { key: "h_poster", label: "Horizontal poster filename" },
  { key: "still_frame", label: "Still frame filename" },
  { key: "v_poster", label: "Vertical poster filename" },
  { key: "logo", label: "Logo filename" },
  { key: "hero_image", label: "Hero image filename" },
  { key: "hero_image_vertical", label: "Hero image vertical filename" },
  { key: "box_art", label: "Box art filename" },
  { key: "source_file_name", label: "Source file name" },
  { key: "ad_dv", label: "Audio description file" },
  { key: "hd_sd", label: "HD/SD" },
  { key: "surround", label: "Surround (Y/N)" },
  { key: "cc", label: "Closed captions", multiline: true },
  { key: "cc_language", label: "CC language", multiline: true },
  { key: "forced_narrative_cc", label: "Forced narrative CC", multiline: true },
  {
    key: "forced_narrative_cc_language",
    label: "Forced narrative CC language",
    multiline: true,
  },
  { key: "photosensitivity", label: "Photosensitivity (Y/N)" },
  { key: "dubbing", label: "Dubbing files", multiline: true },
  { key: "dubbing_language", label: "Dubbing language", multiline: true },
  { key: "dub_cards", label: "Dub cards", multiline: true },
  { key: "skip_intro_start", label: "Skip intro start" },
  { key: "skip_intro_end", label: "Skip intro end" },
  { key: "skip_recap_start", label: "Skip recap start" },
  { key: "skip_recap_end", label: "Skip recap end" },
  { key: "skip_creds_start", label: "Skip credits start" },
  { key: "ad_breaks", label: "Ad breaks", multiline: true },
  { key: "tags", label: "Tags", multiline: true },
  { key: "playback_start_date", label: "Playback start date" },
  { key: "playback_end_date", label: "Playback end date" },
];

export const CORE_METADATA_FIELDS = METADATA_REQUIREMENT_FIELDS;

export type TitleCoreMetadata = Record<string, string>;

export function parseCoreMetadata(raw?: string | null): TitleCoreMetadata {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const result: TitleCoreMetadata = {};
    for (const field of METADATA_REQUIREMENT_FIELDS) {
      const value = parsed[field.key];
      if (typeof value === "string") result[field.key] = value;
    }
    return result;
  } catch {
    return {};
  }
}

export function stringifyCoreMetadata(
  metadata: TitleCoreMetadata
): string | null {
  const cleaned: Record<string, string | null> = {};
  for (const field of METADATA_REQUIREMENT_FIELDS) {
    const value = (metadata[field.key] ?? "").trim();
    cleaned[field.key] = value || null;
  }
  if (Object.values(cleaned).every((v) => v == null)) return null;
  return JSON.stringify(cleaned);
}
