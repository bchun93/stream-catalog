interface RelayMarkProps {
  size?: number;
  className?: string;
}

/** Brand tile — triple-chevron relay mark. */
export function RelayMark({ size = 36, className }: RelayMarkProps) {
  return (
    <img
      src="/relay-icon.png"
      alt=""
      width={size}
      height={size}
      className={className}
      aria-hidden
      draggable={false}
    />
  );
}
