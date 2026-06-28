import { useCallback, useEffect, useState } from "react";
import { HardDrive, Image, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { assetsApi, titlesApi } from "../api/client";
import { AssetForm } from "../components/AssetForm";
import { StatusBadge, TypeBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { CopyButton } from "../components/ui/CopyButton";
import { EmptyState } from "../components/ui/EmptyState";
import { Modal } from "../components/Modal";
import { OverflowMenu } from "../components/ui/OverflowMenu";
import { PageHeader } from "../components/ui/PageHeader";
import { TableSkeleton } from "../components/ui/TableSkeleton";
import type { MediaAsset, Title } from "../types";
import { assetPrimaryLabel, isImageUri } from "../utils/assetLabel";
import { formatBytes, truncateMiddle } from "../utils/format";

function AssetThumb({ uri, label }: { uri: string; label: string }) {
  const [failed, setFailed] = useState(false);
  if (!isImageUri(uri) || failed) {
    return (
      <div className="asset-thumb asset-thumb-fallback" aria-hidden>
        <Image size={16} />
      </div>
    );
  }
  return (
    <img
      src={uri}
      alt=""
      className="asset-thumb"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

export function AssetsPage() {
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [titles, setTitles] = useState<Title[]>([]);
  const [titleFilter, setTitleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editing, setEditing] = useState<MediaAsset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const titleMap = Object.fromEntries(titles.map((t) => [t.id, t.name]));

  const load = useCallback(() => {
    const params: Record<string, string> = {};
    if (titleFilter) params.title_id = titleFilter;
    if (statusFilter) params.status = statusFilter;
    setLoading(true);
    Promise.all([assetsApi.list(params), titlesApi.list()])
      .then(([a, t]) => {
        setAssets(a);
        setTitles(t);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [titleFilter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const closeModal = () => {
    setModal(null);
    setEditing(null);
  };

  const handleDelete = async (a: MediaAsset) => {
    if (!confirm(`Delete asset "${assetPrimaryLabel(a.filename, a.asset_type)}"?`)) return;
    try {
      await assetsApi.delete(a.id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <>
      <PageHeader
        title="Media assets"
        description="Masters, artwork, subtitles, and promos linked to titles with storage URIs and processing status."
        actions={
          <Button
            variant="primary"
            icon={<Plus size={16} />}
            disabled={titles.length === 0}
            onClick={() => {
              setEditing(null);
              setModal("create");
            }}
          >
            Register asset
          </Button>
        }
      />

      {error && <div className="error-banner">{error}</div>}

      <div className="card">
        <div className="table-toolbar">
          <select
            value={titleFilter}
            onChange={(e) => setTitleFilter(e.target.value)}
            aria-label="Filter by title"
          >
            <option value="">All titles</option>
            {titles.map((t) => (
              <option key={t.id} value={String(t.id)}>
                {t.name}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            <option value="uploaded">Uploaded</option>
            <option value="processing">Processing</option>
            <option value="ready">Ready</option>
            <option value="failed">Failed</option>
            <option value="archived">Archived</option>
          </select>
        </div>

        {loading ? (
          <TableSkeleton rows={6} cols={6} />
        ) : assets.length === 0 ? (
          <EmptyState
            icon={HardDrive}
            title="No assets registered"
            description={
              titleFilter || statusFilter
                ? "No assets match the current filters."
                : "Register artwork, masters, or subtitles and link them to a title."
            }
            action={
              titles.length > 0 ? (
                <Button variant="primary" onClick={() => setModal("create")}>
                  Register asset
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="assets-mobile-list mobile-only">
              {assets.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  className="asset-mobile-card"
                  onClick={() => {
                    setEditing(a);
                    setModal("edit");
                  }}
                >
                  <AssetThumb
                    uri={a.storage_uri}
                    label={assetPrimaryLabel(a.filename, a.asset_type)}
                  />
                  <div className="asset-mobile-card-body">
                    <strong>{assetPrimaryLabel(a.filename, a.asset_type)}</strong>
                    <span className="asset-mobile-card-title">
                      {titleMap[a.title_id] ?? `Title #${a.title_id}`}
                    </span>
                    <div className="asset-mobile-card-badges">
                      <TypeBadge value={a.asset_type} />
                      <StatusBadge
                        value={a.status}
                        pulse={a.status === "processing"}
                      />
                    </div>
                    <span className="asset-mobile-card-meta">
                      {formatBytes(a.size_bytes)} · {truncateMiddle(a.storage_uri, 28)}
                    </span>
                  </div>
                </button>
              ))}
            </div>
            <div className="data-table-wrap desktop-only">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Storage</th>
                    <th className="num">Size</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {assets.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <div className="asset-row-main">
                          <AssetThumb
                            uri={a.storage_uri}
                            label={assetPrimaryLabel(a.filename, a.asset_type)}
                          />
                          <div className="asset-row-label">
                            <strong>{assetPrimaryLabel(a.filename, a.asset_type)}</strong>
                            <span className="mono" title={a.filename}>
                              {a.filename}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td>{titleMap[a.title_id] ?? a.title_id}</td>
                      <td>
                        <TypeBadge value={a.asset_type} />
                      </td>
                      <td>
                        <StatusBadge
                          value={a.status}
                          pulse={a.status === "processing"}
                        />
                      </td>
                      <td>
                        <div className="storage-cell">
                          <span className="storage-uri-text" title={a.storage_uri}>
                            {truncateMiddle(a.storage_uri, 32)}
                          </span>
                          <CopyButton value={a.storage_uri} label="Copy storage URI" />
                        </div>
                      </td>
                      <td className="num text-tertiary">{formatBytes(a.size_bytes)}</td>
                      <td className="actions-cell">
                        <div className="row-actions">
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setEditing(a);
                              setModal("edit");
                            }}
                          >
                            Edit
                          </Button>
                          <OverflowMenu
                            label={`Actions for ${a.filename}`}
                            items={[
                              {
                                label: "Open detail / QC",
                                onClick: () => navigate(`/assets/${a.id}`),
                              },
                              {
                                label: "Delete",
                                danger: true,
                                onClick: () => handleDelete(a),
                              },
                            ]}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {modal && titles.length > 0 && (
        <Modal
          title={modal === "create" ? "Register asset" : "Edit asset"}
          onClose={closeModal}
        >
          <AssetForm
            key={editing?.id ?? "new"}
            titles={titles}
            initial={editing ?? undefined}
            onCancel={closeModal}
            onSubmit={async (data) => {
              if (modal === "create") {
                await assetsApi.create(data);
              } else {
                const id = editing?.id;
                if (id == null) {
                  throw new Error(
                    "Could not save — close the dialog, reopen the asset, and try again."
                  );
                }
                await assetsApi.update(id, data);
              }
              load();
            }}
          />
        </Modal>
      )}
    </>
  );
}
