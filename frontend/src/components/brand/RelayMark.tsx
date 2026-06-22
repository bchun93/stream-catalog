interface RelayMarkProps {
  size?: number;
  className?: string;
}

/** Brand mark — signal relay between two nodes. */
export function RelayMark({ size = 20, className }: RelayMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden
    >
      <circle cx="6" cy="12" r="2.5" fill="currentColor" />
      <circle cx="18" cy="12" r="2.5" stroke="currentColor" strokeWidth="2" />
      <path
        d="M8.8 12h4.4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M14.2 10.2 16.8 12l-2.6 1.8"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
