import { useCallback, useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { assetsApi, titlesApi } from "../api/client";
import { RekognitionQcTab } from "../components/RekognitionQcTab";
import { StatusBadge, TypeBadge } from "../components/ui/Badge";
import { CopyButton } from "../components/ui/CopyButton";
import type { MediaAsset, Title } from "../types";
import { assetPrimaryLabel } from "../utils/assetLabel";
import { formatBytes } from "../utils/format";

type Tab = "overview" | "qc";

export function AssetDetailPage() {
  const { assetId } = useParams<{ assetId: string }>();
  const id = Number(assetId);
  const [asset, setAsset] = useState<MediaAsset | null>(null);
  const [title, setTitle] = useState<Title | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!Number.isFinite(id)) {
      setError("Invalid asset id");
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const a = await assetsApi.get(id);
      setAsset(a);
      setError(null);
      try {
        setTitle(await titlesApi.get(a.title_id));
      } catch {
        setTitle(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load asset");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <div className="detail-back">
        <Link to="/assets" className="detail-back-link">
          <ArrowLeft size={15} aria-hidden /> Media assets
        </Link>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="empty">Loading asset…</p>
      ) : !asset ? (
        <p className="empty">Asset not found.</p>
      ) : (
        <>
          <header className="page-header">
            <div>
              <h1>{assetPrimaryLabel(asset.filename, asset.asset_type)}</h1>
              <p className="mono text-tertiary">{asset.filename}</p>
            </div>
            <div className="detail-header-badges">
              <TypeBadge value={asset.asset_type} />
              <StatusBadge value={asset.status} pulse={asset.status === "processing"} />
            </div>
          </header>

          <div className="detail-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "overview"}
              className={`detail-tab${tab === "overview" ? " active" : ""}`}
              onClick={() => setTab("overview")}
            >
              Overview
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "qc"}
              className={`detail-tab${tab === "qc" ? " active" : ""}`}
              onClick={() => setTab("qc")}
            >
              QC
            </button>
          </div>

          {tab === "overview" ? (
            <div className="card detail-overview">
              <dl className="detail-grid">
                <div>
                  <dt>Title</dt>
                  <dd>{title?.name ?? `#${asset.title_id}`}</dd>
                </div>
                <div>
                  <dt>Storage URI</dt>
                  <dd className="detail-storage">
                    <code className="mono" title={asset.storage_uri}>
                      {asset.storage_uri}
                    </code>
                    <CopyButton value={asset.storage_uri} label="Copy storage URI" />
                  </dd>
                </div>
                <div>
                  <dt>Codec</dt>
                  <dd>{asset.codec ?? "—"}</dd>
                </div>
                <div>
                  <dt>Resolution</dt>
                  <dd>{asset.resolution ?? "—"}</dd>
                </div>
                <div>
                  <dt>Duration</dt>
                  <dd>
                    {asset.duration_seconds != null
                      ? `${asset.duration_seconds}s`
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Size</dt>
                  <dd>{formatBytes(asset.size_bytes)}</dd>
                </div>
                <div>
                  <dt>Language</dt>
                  <dd>{asset.language ?? "—"}</dd>
                </div>
                <div>
                  <dt>MIME type</dt>
                  <dd className="mono">{asset.mime_type ?? "—"}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <RekognitionQcTab key={asset.id} asset={asset} />
          )}
        </>
      )}
    </>
  );
}
