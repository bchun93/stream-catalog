import { useCallback, useEffect, useState } from "react";
import { titlesApi } from "../api/client";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import { TitleForm } from "../components/TitleForm";
import { TitleRowPoster } from "../components/TitleRowPoster";
import type { Title } from "../types";

export function TitlesPage() {
  const [titles, setTitles] = useState<Title[]>([]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editing, setEditing] = useState<Title | null>(null);
  const [formTab, setFormTab] = useState<"details" | "artwork">("details");
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  const load = useCallback(() => {
    const params: Record<string, string> = {};
    if (search) params.q = search;
    if (typeFilter) params.title_type = typeFilter;
    titlesApi.list(params).then(setTitles).catch((e) => setError(e.message));
  }, [search, typeFilter]);

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
            setEditing(null);
            setFormTab("details");
            setModal("create");
          }}
        >
          + New title
        </button>
      </header>

      {error && <div className="error-banner">{error}</div>}

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
      </div>

      <div className="card">
        {titles.length === 0 ? (
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
                  <td className="mono">{t.slug}</td>
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
          title={modal === "create" ? "Create title" : "Edit title"}
          onClose={closeModal}
        >
          <TitleForm
            key={editing?.id ?? "new"}
            initial={editing ?? undefined}
            titleId={editing?.id}
            isCreate={modal === "create"}
            initialTab={formTab}
            parents={titles.filter((t) => t.id !== editing?.id)}
            onCancel={closeModal}
            onArtworkSaved={load}
            onSubmit={async (data) => {
              if (modal === "create") {
                const created = await titlesApi.create(data);
                load();
                closeModal();
                return created;
              }
              if (editing) {
                const updated = await titlesApi.update(editing.id, data);
                load();
                closeModal();
                return updated;
              }
            }}
          />
        </Modal>
      )}
    </>
  );
}
