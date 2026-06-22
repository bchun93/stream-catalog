import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  icon: LucideIcon;
  value: number | string;
  label: string;
  context?: string;
  attention?: boolean;
}

export function StatCard({ icon: Icon, value, label, context, attention }: StatCardProps) {
  return (
    <div className={`stat-card${attention ? " stat-card-attention" : ""}`}>
      <div className="stat-card-icon" aria-hidden>
        <Icon size={18} strokeWidth={1.75} />
      </div>
      <div className="stat-card-body">
        <strong className="stat-card-value">{value}</strong>
        <span className="stat-card-label">{label}</span>
        {context && <span className="stat-card-context">{context}</span>}
      </div>
    </div>
  );
}
