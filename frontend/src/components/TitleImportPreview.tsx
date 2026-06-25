import { StatusBadge, TypeBadge } from "./ui/Badge";
import type { TitleStatus, TitleType } from "../types";

interface TitleImportPreviewProps {
  name: string;
  titleType: TitleType | string;
  posterUrl?: string | null;
  releaseYear?: number | string | null;
  rating?: string | null;
  runtimeMinutes?: number | string | null;
  status?: TitleStatus | string;
  metadataSource?: string | null;
  internalId?: string | null;
  eidr?: string | null;
  kicker?: string;
}

function metaLine({
  titleType,
  releaseYear,
  rating,
  runtimeMinutes,
}: Pick<
  TitleImportPreviewProps,
  "titleType" | "releaseYear" | "rating" | "runtimeMinutes"
>): string {
  const runtime =
    runtimeMinutes != null && runtimeMinutes !== ""
      ? `${Number(runtimeMinutes)} min`
      : null;
  return [titleType, releaseYear, rating, runtime].filter(Boolean).join(" · ");
}

export function TitleImportPreview({
  name,
  titleType,
  posterUrl,
  releaseYear,
  rating,
  runtimeMinutes,
  status = "draft",
  metadataSource,
  internalId,
  eidr,
  kicker,
}: TitleImportPreviewProps) {
  const line = metaLine({ titleType, releaseYear, rating, runtimeMinutes });
  const label =
    kicker ??
    (metadataSource?.toLowerCase() === "tmdb"
      ? "Imported from TMDB"
      : "Selected title");

  return (
    <section className="title-import-preview" aria-label="Selected title">
      {posterUrl ? (
        <img src={posterUrl} alt="" className="title-import-preview-poster" loading="lazy" />
      ) : (
        <div className="title-import-preview-poster title-import-preview-poster-empty" aria-hidden>
          {name.charAt(0).toUpperCase() || "—"}
        </div>
      )}
      <div className="title-import-preview-body">
        <div className="title-import-preview-kicker">{label}</div>
        <h3 className="title-import-preview-name">{name}</h3>
        {line && <p className="title-import-preview-meta">{line}</p>}
        <div className="title-import-preview-pills">
          <StatusBadge value={status} />
          {internalId && (
            <span className="title-modal-pill mono">{internalId}</span>
          )}
          {eidr && <span className="title-modal-pill mono">EIDR {eidr}</span>}
          {!internalId && <TypeBadge value={titleType} />}
        </div>
      </div>
    </section>
  );
}
