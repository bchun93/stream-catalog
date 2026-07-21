import { useCallback, useEffect, useMemo, useState } from "react";
import { File, Folder } from "lucide-react";

import { storageApi } from "../api/client";
import type { StorageBrowse, StorageObject } from "../types";
import { formatBytes } from "../utils/format";
import { Button } from "./ui/Button";

export interface PickedStorageObject {
  key: string;
  name: string;
  storage_uri: string;
  size_bytes?: number | null;
}

interface Props {
  /** Lowercase extensions without dot, e.g. ["mp4","mov"]. Empty = all files. */
  acceptExtensions?: string[];
  emptyMessage?: string;
  onPick: (object: PickedStorageObject) => void;
  onCancel: () => void;
}

function extensionOf(name: string): string {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

/** Browse the ingest S3 bucket and pick an object (folders navigate; files select). */
export function StorageObjectPicker({
  acceptExtensions,
  emptyMessage = "No folders or files in this folder.",
  onPick,
  onCancel,
}: Props) {
  const [browse, setBrowse] = useState<StorageBrowse | null>(null);
  const [prefix, setPrefix] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const accept = useMemo(
    () => new Set((acceptExtensions ?? []).map((e) => e.toLowerCase())),
    [acceptExtensions],
  );

  const load = useCallback(async (nextPrefix: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await storageApi.browse(nextPrefix);
      setBrowse(result);
      setPrefix(nextPrefix);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to browse S3");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load("");
  }, [load]);

  const breadcrumbs = useMemo(() => {
    const segments = prefix ? prefix.split("/").filter(Boolean) : [];
    const crumbs = [{ label: "root", prefix: "" }];
    segments.forEach((segment, index) => {
      crumbs.push({ label: segment, prefix: segments.slice(0, index + 1).join("/") });
    });
    return crumbs;
  }, [prefix]);

  const objects = (browse?.objects ?? []).filter((o) => {
    if (accept.size === 0) return true;
    return accept.has(extensionOf(o.name));
  });

  const pick = (object: StorageObject) => {
    onPick({
      key: object.key,
      name: object.name,
      storage_uri: object.storage_uri,
      size_bytes: object.size_bytes,
    });
  };

  return (
    <div className="reko-picker">
      <nav className="storage-breadcrumbs" aria-label="Bucket path">
        {breadcrumbs.map((crumb, index) => (
          <span key={crumb.prefix || "root"} className="storage-breadcrumb-item">
            {index > 0 && <span className="storage-breadcrumb-sep">/</span>}
            <button
              type="button"
              className="storage-breadcrumb-link"
              disabled={loading || crumb.prefix === prefix}
              onClick={() => void load(crumb.prefix)}
            >
              {crumb.label}
            </button>
          </span>
        ))}
      </nav>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="empty">Loading bucket…</p>
      ) : !browse ? (
        <p className="empty">Bucket unavailable.</p>
      ) : browse.folders.length === 0 && objects.length === 0 ? (
        <p className="empty">{emptyMessage}</p>
      ) : (
        <ul className="reko-picker-list">
          {browse.folders.map((folder) => (
            <li key={folder.prefix}>
              <button
                type="button"
                className="reko-picker-row"
                onClick={() => void load(folder.prefix)}
              >
                <Folder size={15} aria-hidden />
                <span>{folder.name}</span>
              </button>
            </li>
          ))}
          {objects.map((object) => (
            <li key={object.key}>
              <button
                type="button"
                className="reko-picker-row reko-picker-file"
                onClick={() => pick(object)}
                title={object.storage_uri}
              >
                <File size={15} aria-hidden />
                <span className="mono">{object.name}</span>
                <span className="text-tertiary">{formatBytes(object.size_bytes)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="reko-picker-actions">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
