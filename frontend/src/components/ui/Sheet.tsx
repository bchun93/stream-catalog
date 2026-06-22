import { X } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

interface SheetProps {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}

export function Sheet({ title, subtitle, onClose, children, footer, wide }: SheetProps) {
  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <aside
        className={`sheet${wide ? " sheet-wide" : ""}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
      >
        <header className="sheet-header">
          <div className="sheet-header-text">
            <h2 id="sheet-title">{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <Button
            variant="subtle"
            className="sheet-close"
            onClick={onClose}
            aria-label="Close panel"
            icon={<X size={18} />}
          />
        </header>
        <div className="sheet-body">{children}</div>
        {footer && <footer className="sheet-footer">{footer}</footer>}
      </aside>
    </div>
  );
}
