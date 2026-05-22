import type { ArtworkItem, ArtworkSpecs, MediaAsset } from "../types";

const LANG_NAMES: Record<string, string> = {
  en: "English",
  es: "Spanish",
  fr: "French",
  de: "German",
  ja: "Japanese",
  ko: "Korean",
  zh: "Chinese",
};

export function resolveSpecs(item: ArtworkItem | MediaAsset): ArtworkSpecs {
  if ("specs" in item && item.specs && Object.keys(item.specs).length > 0) {
    return item.specs;
  }
  return {
    resolution: item.resolution ?? undefined,
    language: item.language ?? undefined,
  };
}

export function formatLanguage(code: string | null | undefined): string | null {
  if (code === null || code === undefined || code === "") {
    return "Neutral";
  }
  return LANG_NAMES[code] ?? code.toUpperCase();
}

export type SpecLine = { key: string; value: string };

export function specLinesForItem(item: ArtworkItem | MediaAsset): SpecLine[] {
  const specs = resolveSpecs(item);
  const lines: SpecLine[] = [];

  if (specs.label) {
    lines.push({ key: "Title", value: specs.label });
  }
  if (specs.resolution) {
    lines.push({ key: "Resolution", value: specs.resolution });
  } else if (specs.width && specs.height) {
    lines.push({ key: "Resolution", value: `${specs.width}×${specs.height}` });
  }
  if (specs.aspect_ratio_label) {
    lines.push({ key: "Aspect", value: specs.aspect_ratio_label });
  } else if (specs.aspect_ratio != null) {
    lines.push({ key: "Aspect", value: `${specs.aspect_ratio.toFixed(2)}:1` });
  }
  const lang = formatLanguage(specs.language);
  if (lang) {
    lines.push({ key: "Language", value: lang });
  }
  if (specs.country) {
    lines.push({ key: "Country", value: specs.country.toUpperCase() });
  }
  if (specs.vote_average != null && specs.vote_average > 0) {
    const votes =
      specs.vote_count != null && specs.vote_count > 0
        ? ` (${specs.vote_count} votes)`
        : "";
    lines.push({
      key: "TMDB score",
      value: `${specs.vote_average.toFixed(1)}${votes}`,
    });
  }

  if (lines.length === 0) {
    lines.push({ key: "Source", value: "TMDB" });
  }

  return lines;
}
