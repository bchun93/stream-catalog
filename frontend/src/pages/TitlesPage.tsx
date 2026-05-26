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
          <span className="title-modal-pill mono">{title.slug}</span>
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
    node.slug.toLowerCase().includes(needle);
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

function HierarchyNode({
  node,
  depth = 0,
  opening,
  onEdit,
  onArtwork,
}: {
  node: TitleTree;
  depth?: number;
  opening: boolean;
  onEdit: (title: Title, tab?: "details" | "artwork") => void;
  onArtwork: (title: Title) => void;
}) {
  return (
    <li className="title-hierarchy-node">
      <div className="title-hierarchy-row" style={{ paddingLeft: `${depth * 1.25}rem` }}>
        <div className="title-row-main">
          {node.poster_url ? (
            <TitleRowPoster url={node.poster_url} />
          ) : (
            <div className="title-row-poster title-row-poster-empty" aria-hidden>
              ?
            </div>
          )}
          <div className="title-row-text">
            <strong>{node.name}</strong>
            <div className="title-row-genres">
              {node.title_type === "episode" && node.episode_number
                ? `Episode ${node.episode_number}`
                : node.title_type === "season" && node.season_number != null
                  ? node.season_number === 0
                    ? "Specials"
                    : `Season ${node.season_number}`
                  : node.release_year ?? "—"}
            </div>
          </div>
        </div>
        <Badge value={node.title_type} kind="type" />
        <Badge value={node.status} />
        <div className="title-hierarchy-actions">
          <button
            className="btn btn-ghost"
            disabled={opening}
            onClick={() => onEdit(node, "details")}
          >
            Edit
          </button>
          <button
            className="btn btn-ghost"
            disabled={opening}
            onClick={() => onArtwork(node)}
          >
            Artwork
          </button>
        </div>
      </div>
      {node.children.length > 0 && (
        <ul>
          {node.children.map((child) => (
            <HierarchyNode
              key={child.id}
              node={child}
              depth={depth + 1}
              opening={opening}
              onEdit={onEdit}
              onArtwork={onArtwork}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function TitlesPage() {
  const [titles, setTitles] = useState<Title[]>([]);
  const [tree, setTree] = useState<TitleTree[]>([]);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [viewMode, setViewMode] = useState<"table" | "hierarchy">("table");
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
          placeholder="Search name or slug…"
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
        <select value={viewMode} onChange={(e) => setViewMode(e.target.value as "table" | "hierarchy")}>
          <option value="table">Table view</option>
          <option value="hierarchy">Hierarchy view</option>
        </select>
      </div>

      <div className="card">
        {loading ? (
          <p className="empty">Loading titles… Render may need a moment to wake up.</p>
        ) : viewMode === "hierarchy" ? (
          filteredTree.length === 0 ? (
            <p className="empty">No titles match your filters.</p>
          ) : (
            <ul className="title-hierarchy">
              {filteredTree.map((node) => (
                <HierarchyNode
                  key={node.id}
                  node={node}
                  opening={opening}
                  onEdit={openEdit}
                  onArtwork={(title) => openEdit(title, "artwork")}
                />
              ))}
            </ul>
          )
        ) : titles.length === 0 ? (
          <p className="empty">No titles match your filters.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Slug</th>
                <th>Type</th>
                <th>Status</th>
                <th>Year</th>
                <th>Studio</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {titles.map((t) => (
                <tr key={t.id}>
                  <td className="title-row-cell">
                    <div className="title-row-main">
                      {t.poster_url ? (
                        <TitleRowPoster url={t.poster_url} />
                      ) : (
                        <div className="title-row-poster title-row-poster-empty" aria-hidden>
                          ?
                        </div>
                      )}
                      <div className="title-row-text">
                        <strong>{t.name}</strong>
                        {t.genres && (
                          <div className="title-row-genres">{t.genres}</div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className="mono table-slug">{t.slug}</span>
                  </td>
                  <td>
                    <Badge value={t.title_type} kind="type" />
                  </td>
                  <td>
                    <Badge value={t.status} />
                  </td>
                  <td>{t.release_year ?? "—"}</td>
                  <td style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {t.studio ?? "—"}
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button
                      className="btn btn-ghost"
                      style={{ marginRight: "0.35rem" }}
                      disabled={opening}
                      onClick={() => openEdit(t, "details")}
                    >
                      Edit
                    </button>
                    <button
                      className="btn btn-ghost"
                      style={{ marginRight: "0.35rem" }}
                      disabled={opening}
                      onClick={() => openEdit(t, "artwork")}
                    >
                      Artwork
                    </button>
                    <button className="btn btn-danger" onClick={() => handleDelete(t)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
