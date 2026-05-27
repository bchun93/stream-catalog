import { useCallback, useEffect, useRef, useState } from "react";
import { apiBaseUrl, titlesApi } from "../api/client";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import { TitleForm } from "../components/TitleForm";
import { TitleRowPoster } from "../components/TitleRowPoster";
import type { Title, TitleTree } from "../types";

function titleMetaLine(title: Title): string {
  return [
    title.title_type,
    title.release_year,
    title.rating,
    title.runtime_minutes ? `${title.runtime_minutes} min` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function displayInternalId(title: Pick<Title, "internal_id" | "slug">): string {
  return title.internal_id || "Pending";
}

function TitleModalSummary({ title }: { title: Title }) {
  return (
    <section className="title-modal-summary" aria-label="Title summary">
      {title.poster_url ? (
        <img
          src={title.poster_url}
          alt=""
          className="title-modal-poster"
          loading="lazy"
        />
      ) : (
        <div className="title-modal-poster title-modal-poster-empty" aria-hidden>
          ?
        </div>
      )}
      <div className="title-modal-summary-body">
        <div className="title-modal-kicker">Editing Title</div>
        <h3>{title.name}</h3>
        <p>{titleMetaLine(title) || "Basic title details"}</p>
        <div className="title-modal-pills">
          <Badge value={title.status} />
          <span className="title-modal-pill mono">{displayInternalId(title)}</span>
          {title.eidr && <span className="title-modal-pill mono">EIDR {title.eidr}</span>}
        </div>
      </div>
    </section>
  );
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

function titleContextLabel(title: Title): string | null {
  if (title.title_type === "episode" && title.episode_number) {
    return `Episode ${title.episode_number}`;
  }
  if (title.title_type === "season" && title.season_number != null) {
    return title.season_number === 0 ? "Specials" : `Season ${title.season_number}`;
  }
  return title.genres ?? null;
}

function stripHierarchyPrefix(name: string): string {
  const episodeMarker = ": Episode ";
  if (name.includes(episodeMarker)) {
    return name.split(episodeMarker).slice(1).join(episodeMarker).replace(/^\d+: /, "");
  }
  return name;
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
  if (title.title_type === "episode" && seriesName) {
    const seasonLabel =
      seasonNumber === 0 ? "Specials" : `Season ${seasonNumber ?? title.season_number ?? 1}`;
    const episodeLabel = `Episode ${title.episode_number ?? 1}`;
    return `${seriesName}: ${seasonLabel}: ${episodeLabel}: ${stripHierarchyPrefix(title.name)}`;
  }
  return title.name;
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
  onDelete,
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
  onDelete: (title: Title) => void;
}) {
  const hasChildren = node.children.length > 0;
  const expanded = hasChildren && (forceExpanded || expandedIds.has(node.id));
  const context = titleContextLabel(node);
  const displayName = displayHierarchyName(node, seriesName, seasonNumber);
  const childSeriesName =
    node.title_type === "series" ? node.name : seriesName;
  const childSeasonNumber =
    node.title_type === "season" ? node.season_number : seasonNumber;

  return (
    <>
      <tr className={`title-table-row title-depth-${Math.min(depth, 3)}`}>
        <td className="title-row-cell">
          <div className="title-row-main" style={{ paddingLeft: `${depth * 1.1}rem` }}>
            <button
              type="button"
              className={`title-expand-toggle ${expanded ? "expanded" : ""}`}
              disabled={!hasChildren}
              onClick={() => onToggle(node.id)}
              aria-label={expanded ? `Collapse ${node.name}` : `Expand ${node.name}`}
            >
              {hasChildren ? "›" : ""}
            </button>
            {node.poster_url ? (
              <TitleRowPoster url={node.poster_url} />
            ) : (
              <div className="title-row-poster title-row-poster-empty" aria-hidden>
                ?
              </div>
            )}
            <div className="title-row-text">
              <strong>{displayName}</strong>
              {context && <div className="title-row-genres">{context}</div>}
            </div>
          </div>
        </td>
        <td>
          <span className="mono table-internal-id">{displayInternalId(node)}</span>
        </td>
        <td>
          <Badge value={node.title_type} kind="type" />
        </td>
        <td>
          <Badge value={node.status} />
        </td>
        <td>{node.release_year ?? "—"}</td>
        <td className="title-studio-cell">{node.studio ?? "—"}</td>
        <td className="title-actions-cell">
          <button
            className="btn btn-ghost"
            style={{ marginRight: "0.35rem" }}
            disabled={opening}
            onClick={() => onEdit(node, "details")}
          >
            Edit
          </button>
          <button
            className="btn btn-ghost"
            style={{ marginRight: "0.35rem" }}
            disabled={opening}
            onClick={() => onEdit(node, "artwork")}
          >
            Artwork
          </button>
          <button className="btn btn-danger" onClick={() => onDelete(node)}>
            Delete
          </button>
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
              onDelete={onDelete}
            />
        ))}
    </>
  );
}

export function TitlesPage() {
  const [titles, setTitles] = useState<Title[]>([]);
  const [tree, setTree] = useState<TitleTree[]>([]);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(() => new Set());
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editing, setEditing] = useState<Title | null>(null);
  const [formTab, setFormTab] = useState<"details" | "artwork">("details");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const requestSeq = useRef(0);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(() => {
    const seq = ++requestSeq.current;
    const params: Record<string, string> = {};
    if (debouncedSearch) params.q = debouncedSearch;
    if (typeFilter) params.title_type = typeFilter;
    setLoading(true);
    setError(null);
    Promise.all([titlesApi.list(params), titlesApi.tree()])
      .then(([data, treeData]) => {
        if (seq !== requestSeq.current) return;
        setTitles(data);
        setTree(treeData);
        setError(null);
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
  }, [debouncedSearch, typeFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const closeModal = () => {
    setModal(null);
    setEditing(null);
    setFormTab("details");
  };

  const openEdit = async (t: Title, tab: "details" | "artwork" = "details") => {
    setOpening(true);
    setError(null);
    try {
      const full = await titlesApi.get(t.id);
      setEditing(full);
      setFormTab(tab);
      setModal("edit");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load title");
    } finally {
      setOpening(false);
    }
  };

  const handleDelete = async (t: Title) => {
    if (!confirm(`Delete "${t.name}" and its linked assets?`)) return;
    try {
      await titlesApi.delete(t.id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const filteredTree = filterTree(tree, debouncedSearch, typeFilter);
  const forceExpanded = Boolean(debouncedSearch || typeFilter);
  const toggleExpanded = (id: number) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Titles</h1>
          <p>Movies, series, seasons, and episodes with lifecycle and availability metadata.</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            setError(null);
            setEditing(null);
            setFormTab("details");
            setModal("create");
          }}
        >
          + New title
        </button>
      </header>

      {error && (
        <div className="error-banner">
          {error}
          <button
            type="button"
            className="btn btn-ghost"
            style={{ marginLeft: "0.75rem" }}
            onClick={load}
          >
            Retry
          </button>
        </div>
      )}

      <div className="toolbar">
        <input
          placeholder="Search name, slug, or internal ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          <option value="movie">Movie</option>
          <option value="series">Series</option>
          <option value="season">Season</option>
          <option value="episode">Episode</option>
        </select>
      </div>

      <div className="card titles-table-card">
        {loading ? (
          <p className="empty">Loading titles… Render may need a moment to wake up.</p>
        ) : filteredTree.length === 0 ? (
          <p className="empty">No titles match your filters.</p>
        ) : (
          <div className="titles-table-scroll">
            <table className="titles-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Internal ID</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Year</th>
                  <th>Studio</th>
                  <th>Actions</th>
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
                    onDelete={handleDelete}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modal && (
        <Modal
          wide
          title={modal === "create" ? "Create Title" : "Edit Title"}
          onClose={closeModal}
        >
          {modal === "edit" && editing && <TitleModalSummary title={editing} />}
          <TitleForm
            key={editing?.id ?? "new"}
            initial={editing ?? undefined}
            titleId={editing?.id}
            isCreate={modal === "create"}
            initialTab={formTab}
            parents={titles.filter((t) => t.id !== editing?.id)}
            onCancel={closeModal}
            onSaved={load}
            onArtworkSaved={load}
            onSubmit={async (data) => {
              if (modal === "create") {
                return await titlesApi.create(data);
              }
              const id = editing?.id;
              if (id == null) {
                throw new Error(
                  "Could not save — close the dialog, reopen the title, and try again."
                );
              }
              return await titlesApi.update(id, data);
            }}
          />
        </Modal>
      )}
    </>
  );
}
