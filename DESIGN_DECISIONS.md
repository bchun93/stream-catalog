# Relay — Design Decisions

A concise case study for the UI design revamp of **Relay**, an internal title-management (TM) and media-asset-management (MAM) admin tool for streaming operations.

---

## Problem statement

The app was functionally complete but visually read as **vibe-coded**: a single dark stylesheet, stock blue accent, flat surfaces, raw API strings in tables, three equal action buttons per row, and a long centered modal for title creation. For a portfolio piece aimed at product hiring, it needed to feel like a **deliberate ops product** — closer to Linear, Mux, or Frame.io than a starter template.

**Constraint:** Preserve all data wiring and behavior. This was a design and front-end craft pass only.

---

## Design direction: “Control room, not dashboard”

### Brand & accent

- Replaced generic `#5b8def` blue with **teal** (`#2DD4BF`) — still professional, but distinct and appropriate for media/broadcast tooling.
- Accent is used **sparingly**: primary buttons, active nav indicator, TMDB import hero, focus rings. Neutrals carry most of the UI.

### Typography

- Kept **DM Sans** (already in the project) with **tabular lining figures** (`font-feature-settings: tnum, lnum`) so stat cards, years, IDs, and sizes align in tables.
- **JetBrains Mono** reserved for metadata: internal IDs, filenames, storage URIs — always at tertiary color and smaller size so they don’t compete with titles.

### Color & semantic status

Defined a single status system used across titles and assets:

| Status | Treatment |
|--------|-----------|
| Draft | Neutral slate |
| In review | Amber |
| Scheduled | Violet |
| Published / Ready | Green |
| Processing | Blue + subtle pulse |
| Failed | Red |
| Archived | Muted gray |

Badges use **tinted backgrounds** (~12% opacity) instead of loud solid fills.

### Surfaces & elevation

Three layers:

1. **Page** — `#090B0F` base  
2. **Raised** — cards, table bodies — border + inset highlight  
3. **Overlay** — right sheet, overflow menus — stronger border + shadow  

Cards are visibly separated from the background; the old problem of “everything the same gray” is addressed with clearer value steps.

### Spacing

Committed to an **8pt grid** (`4 / 8 / 12 / 16 / 24 / 32 / 40 / 48px`). Page padding is 32px; table cell padding 12×16px; consistent section gaps in forms.

---

## Architecture changes

### Before

- One ~1,640-line `index.css` with tokens, layout, tables, forms, artwork, and storage mixed together.
- Thin `Badge` and `Modal` components; pages owned most markup and inline styles.

### After

```
frontend/src/
  styles/
    tokens.css          # Design tokens only
    base.css            # Reset, focus, motion keyframes
    components.css      # Shell, sidebar, tables, sheet, stats
    forms-features.css  # Forms, metadata, artwork (legacy pages)
  components/
    ui/                 # Button, Badge, Sheet, StatCard, OverflowMenu, …
    layout/             # Sidebar
```

Pages import composed primitives instead of re-styling raw elements.

---

## Screen-by-screen decisions

### Sidebar

| Before | After |
|--------|-------|
| Text-only nav, weak active state | Lucide icons + labels, left accent bar on active item |
| “TM + MAM for streaming” orphan caption | “Internal catalog tool” footer + minimal API status dot |
| Plain wordmark | Mark (layers icon) + wordmark |

### Overview

| Before | After |
|--------|-------|
| Four identical stat boxes | Stat cards with icon, tabular value, context line |
| `0 Published` same as other metrics | **Attention** variant (amber left border) when zero |
| Recent assets showed raw TMDB filenames | Humanized label (`Poster · EN`) + filename as secondary mono |
| Equal-weight 50/50 panels | Hierarchy primary (wider column), assets secondary |

### Titles table

| Before | After |
|--------|-------|
| Three buttons: Edit / Artwork / Delete | **Edit** + overflow menu (Artwork, Delete with confirm) |
| Tiny `?` poster fallback | Initial letter on gradient fallback |
| Internal ID at body weight | Tertiary mono, truncated with `title` tooltip |
| Raw toolbar inputs | Unified **table toolbar** inside card (search icon + filter) |
| Text “Loading titles…” | Skeleton shimmer rows |
| Plain empty text | Empty state with icon + CTA |

### Media assets

| Before | After |
|--------|-------|
| Filename as primary column | Humanized type label + mono filename secondary |
| No thumbnails | Thumbnail for image URIs |
| Truncated storage with no action | Truncate + **copy** button |
| `—` size column | Same, styled as tertiary (honest empty) |

### Create / Edit title

| Before | After |
|--------|-------|
| Centered modal, scroll entire form | **Right-side sheet** (720px), sticky header + footer |
| Save at bottom of long scroll | Sticky footer: Cancel + Save (submit via `form` attribute) |
| TMDB import same weight as all fields | **Hero section** with teal tint for import |
| Read-only Internal ID looked editable | `field-readonly` styling (inset bg, muted) |
| Flat field list | Sections: Import → Identification → Core metadata |

---

## Component patterns introduced

- **`StatusBadge` / `TypeBadge`** — semantic mapping in one place  
- **`Sheet`** — slide-in panel with backdrop, a11y `role="dialog"`  
- **`OverflowMenu`** — keyboard-dismissible, Delete in danger style  
- **`StatCard`** — overview metrics with optional `attention` prop  
- **`EmptyState` / `TableSkeleton`** — designed loading and zero states  
- **`CopyButton`** — clipboard for storage URIs  

---

## Accessibility notes

- `focus-visible` rings on interactive elements (global base style)  
- Icon-only buttons include `aria-label`  
- Sheet uses `aria-modal` and labelled title  
- Overflow menu: `role="menu"` / `menuitem`, Escape to close  

---

## What we intentionally did not change

- Backend APIs, routes, and data models  
- Hidden pages (Storage, Metadata config, AI training) — legacy styles retained in `forms-features.css`  
- Asset register flow still uses a **centered modal** (shorter form; sheet reserved for title workflow)  

---

## Portfolio narrative (elevator pitch)

> Relay is an internal TM+MAM tool for streaming libraries. The first build proved the workflows — hierarchy, TMDB import, asset linking — but the UI looked like a generic dark template. I defined a tight token system (teal accent, semantic status, 8pt grid), rebuilt the shell and data tables for scanability, and moved the 40-field title workflow into a right-side sheet with a hero TMDB import. The result reads as an intentional ops product: dense but breathable, with hierarchy from typography and surface value rather than decoration.

---

## Files to review in the repo

| Area | Path |
|------|------|
| Tokens | `frontend/src/styles/tokens.css` |
| Layout & tables | `frontend/src/styles/components.css` |
| Sidebar | `frontend/src/components/layout/Sidebar.tsx` |
| Sheet | `frontend/src/components/ui/Sheet.tsx` |
| Titles (sheet + table) | `frontend/src/pages/TitlesPage.tsx` |
| Title form sections | `frontend/src/components/TitleForm.tsx` |
