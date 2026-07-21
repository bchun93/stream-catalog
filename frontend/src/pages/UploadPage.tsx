import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { CheckCircle2, FileUp, Loader2, Upload, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { storageApi } from "../api/client";
import { PageHeader } from "../components/ui/PageHeader";
import type { StorageConfig } from "../types";

type UploadStatus = "pending" | "uploading" | "done" | "error";

interface UploadItem {
  id: string;
  file: File;
  status: UploadStatus;
  storageUri?: string;
  error?: string;
}

function formatBytes(n: number) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} KB`;
  return `${n} B`;
}

export function UploadPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const [config, setConfig] = useState<StorageConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    storageApi
      .getConfig()
      .then((loaded) => {
        if (!cancelled) {
          setConfig(loaded);
          setConfigError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setConfigError(e instanceof Error ? e.message : "Failed to load storage config");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const updateItem = useCallback((id: string, patch: Partial<UploadItem>) => {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }, []);

  const uploadFiles = useCallback(
    async (files: File[]) => {
      if (!files.length) return;

      const newItems: UploadItem[] = files.map((file) => ({
        id: `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`,
        file,
        status: "pending",
      }));

      setItems((prev) => [...newItems, ...prev]);
      setUploading(true);

      try {
        for (const item of newItems) {
          updateItem(item.id, { status: "uploading", error: undefined });
          try {
            const presigned = await storageApi.presignUpload({
              prefix: "",
              filename: item.file.name,
              content_type: item.file.type || undefined,
            });
            const response = await fetch(presigned.upload_url, {
              method: presigned.method,
              headers: presigned.headers,
              body: item.file,
            });
            if (!response.ok) {
              throw new Error(`Upload failed (${response.status})`);
            }
            updateItem(item.id, {
              status: "done",
              storageUri: presigned.storage_uri,
            });
          } catch (e) {
            updateItem(item.id, {
              status: "error",
              error: e instanceof Error ? e.message : "Upload failed",
            });
          }
        }
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [updateItem],
  );

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList?.length) return;
    void uploadFiles(Array.from(fileList));
  };

  const onDragEnter = (event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current += 1;
    setDragActive(true);
  };

  const onDragLeave = (event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current -= 1;
    if (dragDepthRef.current <= 0) {
      dragDepthRef.current = 0;
      setDragActive(false);
    }
  };

  const onDragOver = (event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepthRef.current = 0;
    setDragActive(false);
    handleFiles(event.dataTransfer.files);
  };

  const bucketLabel = config
    ? config.root_prefix
      ? `s3://${config.bucket}/${config.root_prefix}/`
      : `s3://${config.bucket}/`
    : null;

  return (
    <>
      <PageHeader
        title="Upload"
        description="Drop files into Amazon S3 (ingest bucket). They stay there until you process them later."
      />

      {configError && <div className="error-banner">{configError}</div>}
      {config?.token_required && !import.meta.env.VITE_INGEST_OPERATOR_TOKEN && (
        <div className="error-banner">
          Set <code>VITE_INGEST_OPERATOR_TOKEN</code> in <code>frontend/.env.local</code> to match
          Render <code>INGEST_OPERATOR_TOKEN</code>.
        </div>
      )}

      {bucketLabel && (
        <p className="upload-bucket-label mono">{bucketLabel}</p>
      )}

      <button
        type="button"
        className={`upload-dropzone${dragActive ? " is-active" : ""}${uploading ? " is-busy" : ""}`}
        onClick={() => fileInputRef.current?.click()}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
        disabled={uploading}
        aria-label="Drop files here or click to browse"
      >
        <span className="upload-dropzone-icon" aria-hidden>
          <Upload size={32} strokeWidth={1.5} />
        </span>
        <span className="upload-dropzone-title">
          {uploading ? "Uploading…" : "Drop files here"}
        </span>
        <span className="upload-dropzone-hint">
          or click to browse. Files are stored as-is in Amazon S3.
        </span>
      </button>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        onChange={(event) => handleFiles(event.target.files)}
      />

      {items.length > 0 && (
        <section className="upload-queue" aria-label="Upload queue">
          <h2 className="upload-queue-title">Uploads</h2>
          <ul className="upload-queue-list">
            {items.map((item) => (
              <li key={item.id} className={`upload-queue-item status-${item.status}`}>
                <span className="upload-queue-icon" aria-hidden>
                  {item.status === "pending" && <FileUp size={18} strokeWidth={1.75} />}
                  {item.status === "uploading" && (
                    <Loader2 size={18} strokeWidth={1.75} className="upload-spin" />
                  )}
                  {item.status === "done" && <CheckCircle2 size={18} strokeWidth={1.75} />}
                  {item.status === "error" && <XCircle size={18} strokeWidth={1.75} />}
                </span>
                <div className="upload-queue-body">
                  <div className="upload-queue-name">{item.file.name}</div>
                  <div className="upload-queue-meta">
                    <span>{formatBytes(item.file.size)}</span>
                    {item.status === "pending" && <span>Waiting…</span>}
                    {item.status === "uploading" && <span>Uploading…</span>}
                    {item.status === "done" && item.storageUri && (
                      <span className="mono upload-queue-uri">{item.storageUri}</span>
                    )}
                    {item.status === "error" && (
                      <span className="upload-queue-error">{item.error}</span>
                    )}
                  </div>
                  {item.status === "done" && item.storageUri && (
                    <div className="upload-queue-actions">
                      <Link
                        className="btn btn-subtle"
                        to={`/assets?register=1&uri=${encodeURIComponent(item.storageUri)}&filename=${encodeURIComponent(item.file.name)}&size=${item.file.size}`}
                      >
                        Link to title
                      </Link>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
