interface RelayMarkProps {
  size?: number;
  className?: string;
  /** Subtle chevron pulse; respects prefers-reduced-motion. */
  animated?: boolean;
}

const CHEVRON = "M8.5 11.5 13.5 18 8.5 24.5";

/** Brand tile — triple-chevron relay mark. */
export function RelayMark({
  size = 40,
  className,
  animated = true,
}: RelayMarkProps) {
  return (
    <svg
      className={`relay-mark${animated ? " relay-mark-animated" : ""}${
        className ? ` ${className}` : ""
      }`}
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      draggable={false}
    >
      <rect width="36" height="36" rx="9" className="relay-mark-bg" />
      <path d={CHEVRON} className="relay-chevron relay-chevron-1" />
      <path d={CHEVRON} className="relay-chevron relay-chevron-2" transform="translate(6.5 0)" />
      <path d={CHEVRON} className="relay-chevron relay-chevron-3" transform="translate(13 0)" />
    </svg>
  );
}
