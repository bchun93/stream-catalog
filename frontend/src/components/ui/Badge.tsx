const STATUS_STYLES: Record<string, string> = {
  draft: "status-draft",
  in_review: "status-in-review",
  scheduled: "status-scheduled",
  published: "status-published",
  archived: "status-archived",
  uploaded: "status-draft",
  processing: "status-processing",
  ready: "status-published",
  delivered: "status-scheduled",
  failed: "status-failed",
};

interface StatusBadgeProps {
  value: string;
  pulse?: boolean;
}

export function StatusBadge({ value, pulse }: StatusBadgeProps) {
  const key = value.replace(/ /g, "_");
  const cls = STATUS_STYLES[key] ?? "status-draft";
  const label = value.replace(/_/g, " ");
  return (
    <span className={`status-badge ${cls}${pulse ? " status-pulse" : ""}`}>
      {label}
    </span>
  );
}

const TYPE_STYLES: Record<string, string> = {
  movie: "type-movie",
  series: "type-series",
  season: "type-season",
  episode: "type-episode",
  poster: "type-asset",
  backdrop: "type-asset",
  logo: "type-asset",
  still: "type-asset",
  cast_photo: "type-asset",
  season_poster: "type-asset",
  video_master: "type-asset",
  trailer: "type-asset",
  subtitle: "type-asset",
};

interface TypeBadgeProps {
  value: string;
}

export function TypeBadge({ value }: TypeBadgeProps) {
  const cls = TYPE_STYLES[value] ?? "type-asset";
  const label = value.replace(/_/g, " ");
  return <span className={`type-badge ${cls}`}>{label}</span>;
}

/** @deprecated Use StatusBadge or TypeBadge */
export function Badge({
  value,
  kind = "status",
}: {
  value: string;
  kind?: "type" | "status" | "asset";
}) {
  if (kind === "type") return <TypeBadge value={value} />;
  if (kind === "asset") return <TypeBadge value={value} />;
  return <StatusBadge value={value} pulse={value === "processing"} />;
}
