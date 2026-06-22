import { NavLink } from "react-router-dom";
import { Film, HardDrive, LayoutDashboard } from "lucide-react";
import { RelayMark } from "../brand/RelayMark";
import { VISIBLE_NAV_ITEMS } from "../../navConfig";
import { ApiStatus } from "../ApiStatus";

const NAV_ICONS: Record<string, typeof LayoutDashboard> = {
  "/": LayoutDashboard,
  "/titles": Film,
  "/assets": HardDrive,
};

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-mark" aria-hidden>
          <RelayMark />
        </div>
        <div className="sidebar-wordmark">Relay</div>
      </div>

      <nav className="sidebar-nav" aria-label="Main">
        {VISIBLE_NAV_ITEMS.map((item) => {
          const Icon = NAV_ICONS[item.path] ?? LayoutDashboard;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              end={"end" in item ? item.end : undefined}
              className={({ isActive }) =>
                `sidebar-nav-item${isActive ? " active" : ""}`
              }
            >
              <Icon size={18} strokeWidth={1.75} aria-hidden />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <ApiStatus />
        <p className="sidebar-footer-credit">
          <a
            href="https://bchun93.github.io"
            target="_blank"
            rel="noopener noreferrer"
          >
            bchun93.github.io
          </a>
          {" "}
          2026
        </p>
      </div>
    </aside>
  );
}
