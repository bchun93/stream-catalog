import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { storageApi } from "../api/client";
import type { StorageBrowse, StorageConfig, StorageObject } from "../types";

const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp"]);

function formatBytes(n?: number | null) {
  if (!n) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} KB`;
  return `${n} B`;
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function isImageFile(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return IMAGE_EXTENSIONS.has(ext);
}

export function StoragePage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [config, setConfig] = useState<StorageConfig | null>(null);
  const [browse, setBrowse] = useState<StorageBrowse | null>(null);
  const [prefix, setPrefix] = useState("");
  const [selected, setSelected] = useState<StorageObject | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const breadcrumbs = useMemo(() => {
    const segments = prefix ? prefix.split("/").filter(Boolean) : [];
    const crumbs = [{ label: "root", prefix: "" }];
    segments.forEach((segment, index) => {
      crumbs.push({
        label: segment,
        prefix: segments.slice(0, index + 1).join("/"),
      });
    });
    return crumbs;
  }, [prefix]);

  const loadBrowse = useCallback(async (nextPrefix: string) => {
    setError(null);
    setLoading(true);
    try {
      const [loadedConfig, loadedBrowse] = await Promise.all([
        storageApi.getConfig(),
        storageApi.browse(nextPrefix),
      ]);
      setConfig(loadedConfig);
      setBrowse(loadedBrowse);
      setPrefix(nextPrefix);
      setSelected(null);
      setPreviewUrl(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load bucket");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBrowse("");
  }, [loadBrowse]);

  const openFolder = (nextPrefix: string) => {
    void loadBrowse(nextPrefix);
  };

  const selectObject = async (object: StorageObject) => {
    setSelected(object);
    setPreviewUrl(null);
    if (!isImageFile(object.name)) return;
    try {
      const presigned = await storageApi.presignDownload(object.key);
      setPreviewUrl(presigned.download_url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load preview");
    }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    setUploadStatus(null);
    setError(null);
    const uploaded: string[] = [];
    try {
      for (const file of Array.from(files)) {
        setUploadStatus(`Uploading ${file.name}…`);
        const presigned = await storageApi.presignUpload({
          prefix,
          filename: file.name,
          content_type: file.type || undefined,
        });
        const response = await fetch(presigned.upload_url, {
          method: presigned.method,
          headers: presigned.headers,
          body: file,
        });
        if (!response.ok) {
          throw new Error(`Upload failed for ${file.name} (${response.status})`);
        }
        uploaded.push(presigned.storage_uri);
      }
      setUploadStatus(`Uploaded ${uploaded.length} file${uploaded.length === 1 ? "" : "s"}.`);
      await loadBrowse(prefix);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const bucketLabel = config
    ? config.root_prefix
      ? `s3://${config.bucket}/${config.root_prefix}/`
      : `s3://${config.bucket}/`
    : "S3 bucket";

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Storage</h1>
          <p>
            Upload delivery files to your ingest bucket and browse what is already stored in S3.
          </p>
        </div>
        <div className="storage-header-actions">
          <button
            className="btn btn-primary"
            disabled={uploading || loading}
            onClick={() => fileInputRef.current?.click()}
          >
            {uploading ? "Uploading…" : "Upload files"}
          </button>
          <button
            className="btn btn-ghost"
            disabled={loading}
            onClick={() => void loadBrowse(prefix)}
          >
            Refresh
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={(event) => void handleUpload(event.target.files)}
          />
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}
      {uploadStatus && <div className="storage-status-banner">{uploadStatus}</div>}
      {config?.token_required && !import.meta.env.VITE_INGEST_OPERATOR_TOKEN && (
        <div className="error-banner">
          Set <code>VITE_INGEST_OPERATOR_TOKEN</code> in <code>frontend/.env.local</code> to match
          Render <code>INGEST_OPERATOR_TOKEN</code>.
        </div>
      )}

      <div className="storage-layout">
        <section className="card storage-browser-card">
          <div className="storage-browser-header">
            <div>
              <h3>Bucket browser</h3>
              <p className="storage-muted mono">{bucketLabel}</p>
            </div>
            {browse?.truncated && (
              <span className="storage-muted">Showing first 500 objects in this folder.</span>
            )}
          </div>

          <nav className="storage-breadcrumbs" aria-label="Bucket path">
            {breadcrumbs.map((crumb, index) => (
              <span key={crumb.prefix || "root"} className="storage-breadcrumb-item">
                {index > 0 && <span className="storage-breadcrumb-sep">/</span>}
                <button
                  type="button"
                  className="storage-breadcrumb-link"
                  disabled={loading || crumb.prefix === prefix}
                  onClick={() => openFolder(crumb.prefix)}
                >
                  {crumb.label}
                </button>
              </span>
            ))}
          </nav>

          {loading ? (
            <p className="empty">Loading bucket…</p>
          ) : !browse ? (
            <p className="empty">Bucket unavailable.</p>
          ) : browse.folders.length === 0 && browse.objects.length === 0 ? (
            <p className="empty">This folder is empty. Upload files to get started.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Modified</th>
                </tr>
              </thead>
              <tbody>
                {browse.folders.map((folder) => (
                  <tr
                    key={folder.prefix}
                    className="storage-folder-row"
                    onClick={() => openFolder(folder.prefix)}
                  >
                    <td>
                      <button
                        type="button"
                        className="storage-folder-link"
                        onClick={(event) => {
                          event.stopPropagation();
                          openFolder(folder.prefix);
                        }}
                      >
                        <span aria-hidden>📁</span> {folder.name}
                      </button>
                    </td>
                    <td>folder</td>
                    <td>—</td>
                    <td>—</td>
                  </tr>
                ))}
                {browse.objects.map((object) => (
                  <tr
                    key={object.key}
                    className={`storage-file-row ${selected?.key === object.key ? "selected" : ""}`}
                    onClick={() => void selectObject(object)}
                  >
                    <td className="mono">{object.name}</td>
                    <td>file</td>
                    <td>{formatBytes(object.size_bytes)}</td>
                    <td>{formatTimestamp(object.last_modified)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="card storage-preview-card">
          <h3>Preview</h3>
          {!selected ? (
            <p className="empty">Select a file to inspect its storage URI or preview images.</p>
          ) : (
            <div className="storage-preview-body">
              <div className="storage-preview-meta">
                <div>
                  <span className="storage-muted">File</span>
                  <strong>{selected.name}</strong>
                </div>
                <div>
                  <span className="storage-muted">Size</span>
                  <strong>{formatBytes(selected.size_bytes)}</strong>
                </div>
                <div>
                  <span className="storage-muted">Modified</span>
                  <strong>{formatTimestamp(selected.last_modified)}</strong>
                </div>
                <div>
                  <span className="storage-muted">Storage URI</span>
                  <code className="storage-uri">{selected.storage_uri}</code>
                </div>
              </div>

              {previewUrl ? (
                <img src={previewUrl} alt={selected.name} className="storage-preview-image" />
              ) : isImageFile(selected.name) ? (
                <p className="empty">Loading preview…</p>
              ) : (
                <p className="storage-muted">
                  Preview is available for image files. Use download for other asset types.
                </p>
              )}

              <button
                className="btn btn-ghost"
                onClick={async () => {
                  try {
                    const presigned = await storageApi.presignDownload(selected.key);
                    window.open(presigned.download_url, "_blank", "noopener,noreferrer");
                  } catch (e) {
                    setError(e instanceof Error ? e.message : "Download failed");
                  }
                }}
              >
                Download
              </button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
