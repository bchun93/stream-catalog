import { useCallback, useEffect, useState } from "react";
import { assetsApi, titlesApi } from "../api/client";
import { AssetForm } from "../components/AssetForm";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import type { MediaAsset, Title } from "../types";

function formatBytes(n?: number | null) {
  if (!n) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${n} B`;
}

export function AssetsPage() {
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [titles, setTitles] = useState<Title[]>([]);
  const [titleFilter, setTitleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editing, setEditing] = useState<MediaAsset | null>(null);
  const [error, setError] = useState<string | null>(null);

  const titleMap = Object.fromEntries(titles.map((t) => [t.id, t.name]));

  const load = useCallback(() => {
    const params: Record<string, string> = {};
    if (titleFilter) params.title_id = titleFilter;
    if (statusFilter) params.status = statusFilter;
    Promise.all([assetsApi.list(params), titlesApi.list()])
      .then(([a, t]) => {
        setAssets(a);
        setTitles(t);
      })
      .catch((e) => setError(e.message));
  }, [titleFilter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const closeModal = () => {
    setModal(null);
    setEditing(null);
  };

  const handleDelete = async (a: MediaAsset) => {
    if (!confirm(`Delete asset "${a.filename}"?`)) return;
    try {
      await assetsApi.delete(a.id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Media assets</h1>
          <p>
            Masters, artwork, subtitles, and promos linked to titles with storage URIs and
            processing status.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            setEditing(null);
            setModal("create");
          }}
          disabled={titles.length === 0}
        >
          + Register asset
        </button>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="toolbar">
        <select value={titleFilter} onChange={(e) => setTitleFilter(e.target.value)}>
          <option value="">All titles</option>
          {titles.map((t) => (
            <option key={t.id} value={String(t.id)}>
              {t.name}
            </option>
          ))}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="uploaded">Uploaded</option>
          <option value="processing">Processing</option>
          <option value="ready">Ready</option>
          <option value="failed">Failed</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      <div className="card">
        {assets.length === 0 ? (
          <p className="empty">No assets registered.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Filename</th>
                <th>Title</th>
                <th>Type</th>
                <th>Status</th>
                <th>Storage</th>
                <th>Size</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.id}>
                  <td className="mono">{a.filename}</td>
                  <td>{titleMap[a.title_id] ?? a.title_id}</td>
                  <td>
                    <Badge value={a.asset_type} kind="asset" />
                  </td>
                  <td>
                    <Badge value={a.status} />
                  </td>
                  <td className="mono" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {a.storage_uri}
                  </td>
                  <td>{formatBytes(a.size_bytes)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button
                      className="btn btn-ghost"
                      style={{ marginRight: "0.35rem" }}
                      onClick={() => {
                        setEditing(a);
                        setModal("edit");
                      }}
                    >
                      Edit
                    </button>
                    <button className="btn btn-danger" onClick={() => handleDelete(a)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {modal && titles.length > 0 && (
        <Modal
          title={modal === "create" ? "Register asset" : "Edit asset"}
          onClose={closeModal}
        >
          <AssetForm
            titles={titles}
            initial={editing ?? undefined}
            onCancel={closeModal}
            onSubmit={async (data) => {
              if (modal === "create") await assetsApi.create(data);
              else if (editing) await assetsApi.update(editing.id, data);
              closeModal();
              load();
            }}
          />
        </Modal>
      )}
    </>
  );
}
