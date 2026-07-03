import { useCallback, useEffect, useMemo, useState } from "react";
import { Film, Folder } from "lucide-react";

import { storageApi } from "../api/client";
import type { StorageBrowse } from "../types";
import { Button } from "./ui/Button";
import { formatBytes } from "../utils/format";

const VIDEO_EXTENSIONS = new Set(["mp4", "mov"]);

function isVideo(name: string): boolean {
  return VIDEO_EXTENSIONS.has(name.split(".").pop()?.toLowerCase() ?? "");
}

interface Props {
  onPick: (key: string) => void;
  onCancel: () => void;
}

/** Minimal S3 browser scoped to MP4/MOV objects, for choosing a proxy to analyze. */
export function RekognitionVideoPicker({ onPick, onCancel }: Props) {
  const [browse, setBrowse] = useState<StorageBrowse | null>(null);
  const [prefix, setPrefix] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const videoObjects = (browse?.objects ?? []).filter((o) => isVideo(o.name));

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
      ) : browse.folders.length === 0 && videoObjects.length === 0 ? (
        <p className="empty">No folders or MP4/MOV files in this folder.</p>
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
          {videoObjects.map((object) => (
            <li key={object.key}>
              <button
                type="button"
                className="reko-picker-row reko-picker-file"
                onClick={() => onPick(object.key)}
                title={object.key}
              >
                <Film size={15} aria-hidden />
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
