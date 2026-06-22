/** Sidebar nav items. Set `hidden: true` to hide without removing routes or pages. */
export const NAV_ITEMS = [
  { path: "/", label: "Overview", end: true },
  { path: "/titles", label: "Titles" },
  { path: "/metadata-config", label: "Metadata config", hidden: true },
  { path: "/assets", label: "Media assets" },
  { path: "/storage", label: "Storage", hidden: true },
  { path: "/ai-training", label: "AI training", hidden: true },
] as const;

export const VISIBLE_NAV_ITEMS = NAV_ITEMS.filter(
  (item) => !("hidden" in item && item.hidden),
);
