const TYPE_LABELS: Record<string, string> = {
  poster: "Poster",
  backdrop: "Backdrop",
  logo: "Logo",
  still: "Still",
  cast_photo: "Cast photo",
  season_poster: "Season poster",
  video_master: "Video master",
  trailer: "Trailer",
  subtitle: "Subtitle",
};

const LANG_RE = /_([a-z]{2})(?:[-_]|\.)/i;

export function humanizeAssetType(assetType: string): string {
  return TYPE_LABELS[assetType] ?? assetType.replace(/_/g, " ");
}

export function parseFilenameLanguage(filename: string): string | null {
  const m = filename.match(LANG_RE);
  if (!m) return null;
  return m[1].toUpperCase();
}

/** Primary row label for media assets, e.g. "Poster · EN". */
export function assetPrimaryLabel(filename: string, assetType: string): string {
  const type = humanizeAssetType(assetType);
  const lang = parseFilenameLanguage(filename);
  return lang ? `${type} · ${lang}` : type;
}

export function isImageUri(uri: string): boolean {
  return (
    uri.includes("image.tmdb.org") ||
    /\.(jpe?g|png|gif|webp|svg)(\?|$)/i.test(uri)
  );
}
