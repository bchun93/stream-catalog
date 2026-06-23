import { useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import type { TitleType } from "../../types";

const TYPE_OPTIONS: { value: TitleType | "all"; label: string }[] = [
  { value: "all", label: "All types" },
  { value: "movie", label: "Movie" },
  { value: "series", label: "Series" },
  { value: "season", label: "Season" },
  { value: "episode", label: "Episode" },
];

interface TitlesByTypeStatCardProps {
  icon: LucideIcon;
  titles: { title_type: TitleType }[];
}

export function TitlesByTypeStatCard({ icon: Icon, titles }: TitlesByTypeStatCardProps) {
  const [typeFilter, setTypeFilter] = useState<TitleType | "all">("all");

  const count = useMemo(() => {
    if (typeFilter === "all") return titles.length;
    return titles.filter((t) => t.title_type === typeFilter).length;
  }, [titles, typeFilter]);

  const typeLabel =
    TYPE_OPTIONS.find((o) => o.value === typeFilter)?.label.toLowerCase() ?? "all types";

  return (
    <div className="stat-card stat-card-filterable">
      <div className="stat-card-icon" aria-hidden>
        <Icon size={18} strokeWidth={1.75} />
      </div>
      <div className="stat-card-body">
        <strong className="stat-card-value">{count}</strong>
        <span className="stat-card-label">Titles across types</span>
        <label className="stat-card-filter">
          <span className="sr-only">Filter titles by type</span>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as TitleType | "all")}
          >
            {TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <span className="stat-card-context">
          {typeFilter === "all"
            ? `${titles.length} total in catalog`
            : `${count} ${typeLabel}`}
        </span>
      </div>
    </div>
  );
}
