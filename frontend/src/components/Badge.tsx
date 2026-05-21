interface BadgeProps {
  value: string;
  kind?: "type" | "status" | "asset";
}

export function Badge({ value, kind = "status" }: BadgeProps) {
  const prefix =
    kind === "type"
      ? "badge-"
      : kind === "asset"
        ? "badge-"
        : "badge-";
  const cls = `${prefix}${value.replace(/ /g, "_")}`;
  const label = value.replace(/_/g, " ");
  return <span className={`badge ${cls}`}>{label}</span>;
}
