import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ExternalLink, Pencil, Trash2 } from "lucide-react";

import { ADMIN_TOKEN_SAVED_EVENT, storageApi } from "../api/client";
import type { StorageBrowse, StorageConfig, StorageObject } from "../types";

const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp"]);
const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "m4v", "webm"]);
const AUDIO_EXTENSIONS = new Set(["mp3", "m4a", "aac", "wav", "ogg", "flac"]);

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

function previewKind(name: string): "image" | "video" | "audio" | "other" {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (IMAGE_EXTENSIONS.has(ext)) return "image";
  if (VIDEO_EXTENSIONS.has(ext)) return "video";
  if (AUDIO_EXTENSIONS.has(ext)) return "audio";
  return "other";
}

export function StoragePage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const previewRequestRef = useRef(0);
  const [config, setConfig] = useState<StorageConfig | null>(null);
  const [browse, setBrowse] = useState<StorageBrowse | null>(null);
  const [prefix, setPrefix] = useState("");
  const [selected, setSelected] = useState<StorageObject | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [renameName, setRenameName] = useState("");
  const [checkedKeys, setCheckedKeys] = useState<Set<string>>(() => new Set());
  const [mutating, setMutating] = useState<"rename" | "delete" | "bulk-delete" | null>(null);
  const [bulkProgress, setBulkProgress] = useState<{ completed: number; total: number } | null>(null);
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
    previewRequestRef.current += 1;
    setError(null);
    setLoading(true);
    setPreviewLoading(false);
    setSelected(null);
    setCheckedKeys(new Set());
    setPreviewUrl(null);
    try {
      const [loadedConfig, loadedBrowse] = await Promise.all([
        storageApi.getConfig(),
        storageApi.browse(nextPrefix),
      ]);
      setConfig(loadedConfig);
      setBrowse(loadedBrowse);
      setPrefix(nextPrefix);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load bucket");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBrowse("");
  }, [loadBrowse]);

  useEffect(() => {
    const retry = () => void loadBrowse(prefix);
    window.addEventListener(ADMIN_TOKEN_SAVED_EVENT, retry);
    return () => window.removeEventListener(ADMIN_TOKEN_SAVED_EVENT, retry);
  }, [loadBrowse, prefix]);

  const openFolder = (nextPrefix: string) => {
    if (mutating || loading) return;
    void loadBrowse(nextPrefix);
  };

  const selectObject = async (object: StorageObject) => {
    const requestId = ++previewRequestRef.current;
    setSelected(object);
    setRenameName(object.name);
    setPreviewUrl(null);
    setPreviewLoading(true);
    setError(null);
    try {
      const presigned = await storageApi.presignDownload(object.key);
      if (previewRequestRef.current === requestId) {
        setPreviewUrl(presigned.download_url);
      }
    } catch (e) {
      if (previewRequestRef.current === requestId) {
        setError(e instanceof Error ? e.message : "Failed to load preview");
      }
    } finally {
      if (previewRequestRef.current === requestId) {
        setPreviewLoading(false);
      }
    }
  };

  const openSelected = async () => {
    if (!selected) return;
    const newTab = window.open("", "_blank");
    try {
      const presigned = await storageApi.presignDownload(selected.key);
      if (newTab) {
        newTab.opener = null;
        newTab.location.href = presigned.download_url;
      } else {
        window.location.assign(presigned.download_url);
      }
    } catch (e) {
      newTab?.close();
      setError(e instanceof Error ? e.message : "Failed to open object");
    }
  };

  const renameSelected = async () => {
    if (!selected || !renameName.trim() || renameName.trim() === selected.name) return;
    if (selected.size_bytes == null) {
      setError("Object size is unavailable. Refresh the browser and try again.");
      return;
    }
    setMutating("rename");
    setError(null);
    setUploadStatus(null);
    try {
      const renamed = await storageApi.renameObject({
        key: selected.key,
        new_name: renameName.trim(),
        expected_etag: selected.etag,
        expected_size: selected.size_bytes,
      });
      setUploadStatus(`Renamed to ${renamed.key.split("/").pop()}.`);
      await loadBrowse(prefix);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rename failed");
    } finally {
      setMutating(null);
    }
  };

  const deleteObject = async (object: StorageObject) => {
    const confirmed = window.confirm(
      `Permanently delete "${object.key}" from S3? This cannot be undone.`,
    );
    if (!confirmed) return;
    setMutating("delete");
    setError(null);
    setUploadStatus(null);
    try {
      await storageApi.deleteObject(object.key, object.etag);
      setUploadStatus(`Deleted ${object.name}.`);
      await loadBrowse(prefix);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setMutating(null);
    }
  };

  const deleteCheckedObjects = async () => {
    const objects = browse?.objects.filter((object) => checkedKeys.has(object.key)) ?? [];
    if (!objects.length) return;
    const names = objects
      .slice(0, 5)
      .map((object) => `• ${object.name}`)
      .join("\n");
    const remaining = objects.length > 5 ? `\n• …and ${objects.length - 5} more` : "";
    const scope = prefix || "S3 root";
    const confirmationMessage =
      `Permanently delete ${objects.length} object${objects.length === 1 ? "" : "s"} ` +
      `from "${scope}"?\n\n${names}${remaining}\n\nThis cannot be undone.`;
    const confirmed =
      objects.length >= 10
        ? window.prompt(
            `${confirmationMessage}\n\nType DELETE ${objects.length} to confirm.`,
          ) === `DELETE ${objects.length}`
        : window.confirm(confirmationMessage);
    if (!confirmed) return;

    setMutating("bulk-delete");
    setBulkProgress({ completed: 0, total: objects.length });
    setError(null);
    setUploadStatus(null);
    let deleted = 0;
    const failures: string[] = [];
    const failedKeys = new Set<string>();
    for (const object of objects) {
      try {
        await storageApi.deleteObject(object.key, object.etag);
        deleted += 1;
      } catch (e) {
        const message = e instanceof Error ? e.message : "Delete failed";
        failures.push(`${object.name}: ${message}`);
        failedKeys.add(object.key);
      }
      setBulkProgress({ completed: deleted + failures.length, total: objects.length });
    }

    try {
      await loadBrowse(prefix);
      setCheckedKeys(failedKeys);
      if (deleted) {
        setUploadStatus(`Deleted ${deleted} object${deleted === 1 ? "" : "s"}.`);
      }
      if (failures.length) {
        setError(
          `${failures.length} object${failures.length === 1 ? "" : "s"} could not be deleted: ${failures.join("; ")}`,
        );
      }
    } finally {
      setMutating(null);
      setBulkProgress(null);
    }
  };

  const toggleChecked = (key: string) => {
    setCheckedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleAllVisible = () => {
    const objects = browse?.objects ?? [];
    const allSelected = objects.length > 0 && objects.every((object) => checkedKeys.has(object.key));
    setCheckedKeys(allSelected ? new Set() : new Set(objects.map((object) => object.key)));
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
  const selectedPreviewKind = selected ? previewKind(selected.name) : "other";
  const visibleObjects = browse?.objects ?? [];
  const allVisibleChecked =
    visibleObjects.length > 0 && visibleObjects.every((object) => checkedKeys.has(object.key));
  const someVisibleChecked =
    !allVisibleChecked && visibleObjects.some((object) => checkedKeys.has(object.key));

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someVisibleChecked;
    }
  }, [someVisibleChecked]);

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
          {prefix && (
            <button
              className="btn btn-ghost"
              disabled={loading || Boolean(mutating)}
              onClick={() => void loadBrowse("")}
            >
              <ArrowLeft size={16} aria-hidden />
              Back to S3 root
            </button>
          )}
          <button
            className="btn btn-primary"
            disabled={uploading || loading || Boolean(mutating)}
            onClick={() => fileInputRef.current?.click()}
          >
            {uploading ? "Uploading…" : "Upload files"}
          </button>
          <button
            className="btn btn-ghost"
            disabled={loading || Boolean(mutating)}
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

      {error && <div className="error-banner" role="alert">{error}</div>}
      {uploadStatus && (
        <div className="storage-status-banner" role="status" aria-live="polite">
          {uploadStatus}
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
                  disabled={loading || Boolean(mutating) || crumb.prefix === prefix}
                  onClick={() => openFolder(crumb.prefix)}
                >
                  {crumb.label}
                </button>
              </span>
            ))}
          </nav>

          {checkedKeys.size > 0 && (
            <div className="storage-bulk-actions">
              <span>
                {checkedKeys.size} object{checkedKeys.size === 1 ? "" : "s"} selected
              </span>
              <button
                type="button"
                className="btn btn-danger"
                disabled={Boolean(mutating) || loading}
                onClick={() => void deleteCheckedObjects()}
              >
                <Trash2 size={16} aria-hidden />
                {mutating === "bulk-delete" && bulkProgress
                  ? `Deleting ${bulkProgress.completed}/${bulkProgress.total}…`
                  : "Delete selected"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={Boolean(mutating) || loading}
                onClick={() => setCheckedKeys(new Set())}
              >
                Clear
              </button>
            </div>
          )}

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
                  <th className="storage-select-cell">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      aria-label="Select all objects in this folder"
                      aria-checked={someVisibleChecked ? "mixed" : allVisibleChecked}
                      checked={allVisibleChecked}
                      disabled={visibleObjects.length === 0 || Boolean(mutating) || loading}
                      onChange={toggleAllVisible}
                    />
                  </th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Modified</th>
                  <th className="storage-actions-cell">Actions</th>
                </tr>
              </thead>
              <tbody>
                {browse.folders.map((folder) => (
                  <tr
                    key={folder.prefix}
                    className="storage-folder-row"
                    onClick={() => openFolder(folder.prefix)}
                  >
                    <td className="storage-select-cell" />
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
                    <td className="storage-actions-cell" />
                  </tr>
                ))}
                {browse.objects.map((object) => (
                  <tr
                    key={object.key}
                    className={`storage-file-row ${selected?.key === object.key ? "selected" : ""}`}
                    onClick={() => void selectObject(object)}
                  >
                    <td
                      className="storage-select-cell"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        aria-label={`Select ${object.name}`}
                        checked={checkedKeys.has(object.key)}
                        disabled={Boolean(mutating) || loading}
                        onChange={() => toggleChecked(object.key)}
                      />
                    </td>
                    <td className="mono">{object.name}</td>
                    <td>file</td>
                    <td>{formatBytes(object.size_bytes)}</td>
                    <td>{formatTimestamp(object.last_modified)}</td>
                    <td
                      className="storage-actions-cell"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <button
                        type="button"
                        className="storage-row-delete"
                        title={`Delete ${object.name}`}
                        aria-label={`Delete ${object.name}`}
                        disabled={Boolean(mutating) || loading}
                        onClick={() => void deleteObject(object)}
                      >
                        <Trash2 size={16} aria-hidden />
                      </button>
                    </td>
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

              {previewUrl && selectedPreviewKind === "image" ? (
                <img src={previewUrl} alt={selected.name} className="storage-preview-image" />
              ) : previewUrl && selectedPreviewKind === "video" ? (
                <video
                  src={previewUrl}
                  className="storage-preview-media"
                  controls
                  preload="metadata"
                />
              ) : previewUrl && selectedPreviewKind === "audio" ? (
                <audio src={previewUrl} className="storage-preview-audio" controls preload="metadata" />
              ) : previewLoading ? (
                <p className="empty">Loading preview…</p>
              ) : (
                <p className="storage-muted">
                  Inline preview is unavailable for this file type. Open it in a new tab to view
                  or download it.
                </p>
              )}

              <div className="storage-object-actions">
                <button
                  className="btn btn-ghost"
                  disabled={Boolean(mutating)}
                  onClick={() => void openSelected()}
                >
                  <ExternalLink size={16} aria-hidden />
                  Open object
                </button>
                <button
                  className="btn btn-danger"
                  disabled={Boolean(mutating)}
                  onClick={() => void deleteObject(selected)}
                >
                  <Trash2 size={16} aria-hidden />
                  {mutating === "delete" ? "Deleting…" : "Delete"}
                </button>
              </div>

              <form
                className="storage-rename-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void renameSelected();
                }}
              >
                <label htmlFor="storage-object-name">Object name</label>
                <div>
                  <input
                    id="storage-object-name"
                    value={renameName}
                    maxLength={255}
                    disabled={Boolean(mutating)}
                    onChange={(event) => setRenameName(event.target.value)}
                  />
                  <button
                    className="btn btn-ghost"
                    type="submit"
                    disabled={
                      Boolean(mutating) ||
                      !renameName.trim() ||
                      renameName.trim() === selected.name
                    }
                  >
                    <Pencil size={16} aria-hidden />
                    {mutating === "rename" ? "Renaming…" : "Rename"}
                  </button>
                </div>
                <span className="storage-muted">
                  Renaming copies the object to a new S3 key, then removes the old key.
                </span>
              </form>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
