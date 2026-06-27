import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight, Film, Plus, Search } from "lucide-react";
import { apiBaseUrl, titlesApi } from "../api/client";
import { StatusBadge, TypeBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { Sheet } from "../components/ui/Sheet";
import { TableSkeleton } from "../components/ui/TableSkeleton";
import { TitleForm } from "../components/TitleForm";
import { TitleRowPoster } from "../components/TitleRowPoster";
import type { Title, TitleTree } from "../types";

const TITLE_FORM_ID = "title-form";

function displayInternalId(title: Pick<Title, "internal_id" | "slug">): string {
  return title.internal_id || "Pending";
}

function stripHierarchyPrefix(name: string): string {
  const marker = ": Episode ";
  if (!name.includes(marker)) return name;
  const tail = name.split(marker)[1] ?? name;
  return tail.replace(/^\d+: /, "");
}

function matchesFilters(node: TitleTree, search: string, typeFilter: string): boolean {
  const needle = search.trim().toLowerCase();
  const textMatch =
    !needle ||
    node.name.toLowerCase().includes(needle) ||
    node.slug.toLowerCase().includes(needle) ||
    (node.internal_id ?? "").toLowerCase().includes(needle);
  const typeMatch = !typeFilter || node.title_type === typeFilter;
  return textMatch && typeMatch;
}

function filterTree(nodes: TitleTree[], search: string, typeFilter: string): TitleTree[] {
  return nodes
    .map((node) => {
      const children = filterTree(node.children, search, typeFilter);
      if (matchesFilters(node, search, typeFilter) || children.length > 0) {
        return { ...node, children };
      }
      return null;
    })
    .filter((node): node is TitleTree => node !== null);
}

function flattenTitleTree(nodes: TitleTree[]): Title[] {
  return nodes.flatMap((node) => [node, ...flattenTitleTree(node.children)]);
}

function findTreeNode(nodes: TitleTree[], id: number): TitleTree | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const found = findTreeNode(node.children, id);
    if (found) return found;
  }
  return null;
}

function countChildTitles(node: TitleTree): number {
  return node.children.reduce(
    (total, child) => total + 1 + countChildTitles(child),
    0
  );
}

function collectSubtreeIds(node: TitleTree): number[] {
  return [node.id, ...node.children.flatMap(collectSubtreeIds)];
}

function removeTitleFromTree(nodes: TitleTree[], titleId: number): TitleTree[] {
  const result: TitleTree[] = [];
  for (const node of nodes) {
    if (node.id === titleId) continue;
    result.push({
      ...node,
      children: removeTitleFromTree(node.children, titleId),
    });
  }
  return result;
}

function titleContextLabel(title: Title): string | null {
  if (title.title_type === "episode" && title.episode_number) {
    return `Episode ${title.episode_number}`;
  }
  if (title.title_type === "season" && title.season_number != null) {
    return title.season_number === 0 ? "Specials" : `Season ${title.season_number}`;
  }
  return title.genres ?? null;
}

function displayHierarchyName(
  title: Title,
  seriesName?: string,
  seasonNumber?: number | null
): string {
  if (title.title_type === "season" && seriesName) {
    const label = title.season_number === 0 ? "Specials" : `Season ${title.season_number ?? 1}`;
    return `${seriesName}: ${label}`;
  }
  if (title.title_type === "episode") {
    return stripHierarchyPrefix(title.name);
  }
  return title.name;
}

function TitleMobileRow({
  node,
  depth = 0,
  seriesName,
  seasonNumber,
  opening,
  expandedIds,
  forceExpanded,
  onToggle,
  onEdit,
}: {
  node: TitleTree;
  depth?: number;
  seriesName?: string;
  seasonNumber?: number | null;
  opening: boolean;
  expandedIds: Set<number>;
  forceExpanded: boolean;
  onToggle: (id: number) => void;
  onEdit: (title: Title, tab?: "details" | "artwork") => void;
}) {
  const hasChildren = node.children.length > 0;
  const expanded = hasChildren && (forceExpanded || expandedIds.has(node.id));
  const displayName = displayHierarchyName(node, seriesName, seasonNumber);
  const childSeriesName = node.title_type === "series" ? node.name : seriesName;
  const childSeasonNumber = node.title_type === "season" ? node.season_number : seasonNumber;

  return (
    <>
      <div
        className="title-mobile-card-wrap"
        style={{ paddingLeft: `${depth * 12}px` }}
      >
        <div className="title-mobile-card-main">
          {hasChildren ? (
            <button
              type="button"
              className={`title-expand-toggle ${expanded ? "expanded" : ""}`}
              onClick={() => onToggle(node.id)}
              aria-label={expanded ? `Collapse ${node.name}` : `Expand ${node.name}`}
              aria-expanded={expanded}
            >
              <ChevronRight size={18} strokeWidth={2.25} aria-hidden />
            </button>
          ) : (
            <span className="title-expand-toggle-spacer" aria-hidden />
          )}
          <button
            type="button"
            className="title-mobile-card"
            disabled={opening}
            onClick={() => onEdit(node, "details")}
            aria-label={`Open ${displayName}`}
          >
            {node.poster_url ? (
              <TitleRowPoster url={node.poster_url} />
            ) : (
              <div className="title-row-poster title-row-poster-fallback" aria-hidden>
                {node.name.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="title-mobile-card-body">
              <strong title={displayName}>{displayName}</strong>
              <div className="title-mobile-card-meta">
                <TypeBadge value={node.title_type} />
                <StatusBadge value={node.status} />
                {node.release_year != null && <span>{node.release_year}</span>}
                <span className="title-mobile-card-id">{displayInternalId(node)}</span>
              </div>
            </div>
          </button>
        </div>
      </div>
      {expanded &&
        node.children.map((child) => (
          <TitleMobileRow
            key={child.id}
            node={child}
            depth={depth + 1}
            seriesName={childSeriesName}
            seasonNumber={childSeasonNumber}
            opening={opening}
            expandedIds={expandedIds}
            forceExpanded={forceExpanded}
            onToggle={onToggle}
            onEdit={onEdit}
          />
        ))}
    </>
  );
}

function TitleTableRow({
  node,
  depth = 0,
  seriesName,
  seasonNumber,
  opening,
  expandedIds,
  forceExpanded,
  onToggle,
  onEdit,
}: {
  node: TitleTree;
  depth?: number;
  seriesName?: string;
  seasonNumber?: number | null;
  opening: boolean;
  expandedIds: Set<number>;
  forceExpanded: boolean;
  onToggle: (id: number) => void;
  onEdit: (title: Title, tab?: "details" | "artwork") => void;
}) {
  const hasChildren = node.children.length > 0;
  const expanded = hasChildren && (forceExpanded || expandedIds.has(node.id));
  const context = titleContextLabel(node);
  const displayName = displayHierarchyName(node, seriesName, seasonNumber);
  const childSeriesName = node.title_type === "series" ? node.name : seriesName;
  const childSeasonNumber = node.title_type === "season" ? node.season_number : seasonNumber;

  return (
    <>
      <tr
        className={`title-table-row title-table-row-clickable title-depth-${Math.min(depth, 3)}`}
        onClick={() => {
          if (!opening) onEdit(node, "details");
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            if (!opening) onEdit(node, "details");
          }
        }}
        tabIndex={0}
        aria-label={`Open ${displayName}`}
      >
        <td>
          <div className="title-row-main" style={{ paddingLeft: `${depth * 16}px` }}>
            {hasChildren ? (
              <button
                type="button"
                className={`title-expand-toggle ${expanded ? "expanded" : ""}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggle(node.id);
                }}
                aria-label={expanded ? `Collapse ${node.name}` : `Expand ${node.name}`}
                aria-expanded={expanded}
              >
                <ChevronRight size={18} strokeWidth={2.25} aria-hidden />
              </button>
            ) : (
              <span className="title-expand-toggle-spacer" aria-hidden />
            )}
            {node.poster_url ? (
              <TitleRowPoster url={node.poster_url} />
            ) : (
              <div className="title-row-poster title-row-poster-fallback" aria-hidden>
                {node.name.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="title-row-text">
              <strong title={displayName}>{displayName}</strong>
              {context && <div className="title-row-meta">{context}</div>}
            </div>
          </div>
        </td>
        <td>
          <span className="table-meta-id" title={displayInternalId(node)}>
            {displayInternalId(node)}
          </span>
        </td>
        <td>
          <TypeBadge value={node.title_type} />
        </td>
        <td>
          <StatusBadge value={node.status} />
        </td>
        <td className="num">{node.release_year ?? "—"}</td>
        <td>
          <span className="table-truncate" title={node.studio ?? undefined}>
            {node.studio ?? "—"}
          </span>
        </td>
      </tr>
      {expanded &&
        node.children.map((child) => (
          <TitleTableRow
            key={child.id}
            node={child}
            depth={depth + 1}
            seriesName={childSeriesName}
            seasonNumber={childSeasonNumber}
            opening={opening}
            expandedIds={expandedIds}
            forceExpanded={forceExpanded}
            onToggle={onToggle}
            onEdit={onEdit}
          />
        ))}
    </>
  );
}

export function TitlesPage() {
  const [tree, setTree] = useState<TitleTree[]>([]);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(() => new Set());
  const [sheet, setSheet] = useState<"create" | "edit" | null>(null);
  const [editing, setEditing] = useState<Title | null>(null);
  const [formTab, setFormTab] = useState<"details" | "artwork">("details");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [formSessionKey, setFormSessionKey] = useState(0);
  const requestSeq = useRef(0);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(() => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    titlesApi
      .tree()
      .then((treeData) => {
        if (seq !== requestSeq.current) return;
        setTree(treeData);
      })
      .catch((e) => {
        if (seq !== requestSeq.current) return;
        const msg = e instanceof Error ? e.message : "Failed to load titles";
        const base = apiBaseUrl();
        setError(base ? `${msg} (API: ${base})` : msg);
      })
      .finally(() => {
        if (seq !== requestSeq.current) return;
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const closeSheet = () => {
    setSheet(null);
    setEditing(null);
    setFormTab("details");
    setSaving(false);
  };

  const openEdit = async (t: Title, tab: "details" | "artwork" = "details") => {
    setOpening(true);
    setError(null);
    try {
      const full = await titlesApi.get(t.id);
      setFormSessionKey((key) => key + 1);
      setEditing(full);
      setFormTab(tab);
      setSheet("edit");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load title");
    } finally {
      setOpening(false);
    }
  };

  const filteredTree = filterTree(tree, debouncedSearch, typeFilter);
  const parentOptions = flattenTitleTree(tree);
  const forceExpanded = Boolean(debouncedSearch || typeFilter);

  const toggleExpanded = (id: number) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDeleteTitle = async () => {
    if (!editing) return;
    const deletedId = editing.id;
    const treeNode = findTreeNode(tree, deletedId);
    const childCount = treeNode ? countChildTitles(treeNode) : 0;
    const message =
      childCount > 0
        ? `Delete "${editing.name}" and its ${childCount} child title${childCount === 1 ? "" : "s"}? This cannot be undone.`
        : `Delete "${editing.name}"? This cannot be undone.`;
    if (!confirm(message)) return;

    const removedIds = treeNode ? collectSubtreeIds(treeNode) : [deletedId];
    const snapshot = tree;

    setDeleting(true);
    setError(null);
    setTree((current) => removeTitleFromTree(current, deletedId));
    setExpandedIds((current) => {
      const next = new Set(current);
      for (const id of removedIds) next.delete(id);
      return next;
    });
    closeSheet();

    try {
      await titlesApi.delete(deletedId);
    } catch (e) {
      setTree(snapshot);
      setError(e instanceof Error ? e.message : "Failed to delete title");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Titles"
        description="Movies, series, seasons, and episodes with lifecycle and availability metadata."
        actions={
          <Button
            variant="primary"
            icon={<Plus size={16} />}
            onClick={() => {
              setError(null);
              setFormSessionKey((key) => key + 1);
              setEditing(null);
              setFormTab("details");
              setSheet("create");
            }}
          >
            New title
          </Button>
        }
      />

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <Button variant="ghost" onClick={load}>
            Retry
          </Button>
        </div>
      )}

      <div className="card titles-table-card">
        <div className="table-toolbar">
          <label className="table-toolbar-search">
            <Search size={16} aria-hidden />
            <input
              placeholder="Search name, slug, or internal ID…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search titles"
            />
          </label>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            aria-label="Filter by type"
          >
            <option value="">All types</option>
            <option value="movie">Movie</option>
            <option value="series">Series</option>
            <option value="season">Season</option>
            <option value="episode">Episode</option>
          </select>
        </div>

        {loading ? (
          <TableSkeleton rows={10} cols={6} />
        ) : filteredTree.length === 0 ? (
          <EmptyState
            icon={Film}
            title="No titles found"
            description={
              debouncedSearch || typeFilter
                ? "Try adjusting your search or filters."
                : "Create your first title to start building the catalog."
            }
            action={
              !debouncedSearch && !typeFilter ? (
                <Button
                  variant="primary"
                  onClick={() => {
                    setFormSessionKey((key) => key + 1);
                    setEditing(null);
                    setFormTab("details");
                    setSheet("create");
                  }}
                >
                  New title
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="titles-mobile-list mobile-only">
              {filteredTree.map((node) => (
                <TitleMobileRow
                  key={node.id}
                  node={node}
                  opening={opening}
                  expandedIds={expandedIds}
                  forceExpanded={forceExpanded}
                  onToggle={toggleExpanded}
                  onEdit={openEdit}
                />
              ))}
            </div>
            <div className="data-table-wrap titles-table-scroll desktop-only">
              <table className="data-table titles-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Internal ID</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th className="num">Year</th>
                    <th>Studio</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTree.map((node) => (
                    <TitleTableRow
                      key={node.id}
                      node={node}
                      opening={opening}
                      expandedIds={expandedIds}
                      forceExpanded={forceExpanded}
                      onToggle={toggleExpanded}
                      onEdit={openEdit}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {sheet && (
        <Sheet
          wide
          title={sheet === "create" ? "Create title" : "Edit title"}
          onClose={closeSheet}
          footer={
            <div className="sheet-footer-inner">
              {sheet === "edit" && editing ? (
                <Button
                  variant="danger"
                  disabled={saving || deleting}
                  onClick={handleDeleteTitle}
                >
                  {deleting ? "Deleting…" : "Delete title"}
                </Button>
              ) : null}
              <div className="sheet-footer-actions">
                <Button variant="ghost" onClick={closeSheet} disabled={deleting}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  type="submit"
                  form={TITLE_FORM_ID}
                  disabled={saving || deleting}
                >
                  {saving ? "Saving…" : "Save title"}
                </Button>
              </div>
            </div>
          }
        >
          <TitleForm
            key={formSessionKey}
            formId={TITLE_FORM_ID}
            hideActions
            onSavingChange={setSaving}
            initial={editing ?? undefined}
            titleId={editing?.id}
            isCreate={sheet === "create"}
            initialTab={formTab}
            parents={parentOptions.filter((t) => t.id !== editing?.id)}
            onCancel={closeSheet}
            onSaved={load}
            onTitlePersisted={(title) => {
              setEditing(title);
              setSheet("edit");
            }}
            onArtworkSaved={load}
            onSubmit={async (data, existingId) => {
              const id = existingId ?? editing?.id;
              if (id != null) {
                return await titlesApi.update(id, data);
              }
              if (sheet === "create") {
                return await titlesApi.create(data);
              }
              throw new Error(
                "Could not save — close the panel, reopen the title, and try again."
              );
            }}
          />
        </Sheet>
      )}
    </>
  );
}
