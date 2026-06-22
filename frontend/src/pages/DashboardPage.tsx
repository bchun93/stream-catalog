import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Film, HardDrive, Play } from "lucide-react";
import { assetsApi, titlesApi } from "../api/client";
import type { MediaAsset, Title, TitleTree } from "../types";
import { StatusBadge, TypeBadge } from "../components/ui/Badge";
import { PageHeader } from "../components/ui/PageHeader";
import { StatCard } from "../components/ui/StatCard";
import { assetPrimaryLabel, isImageUri } from "../utils/assetLabel";

function isHierarchyRoot(node: TitleTree): boolean {
  return node.title_type === "series" || node.title_type === "movie";
}

function TreeNode({
  node,
  expandedIds,
  onToggle,
}: {
  node: TitleTree;
  expandedIds: Set<number>;
  onToggle: (id: number) => void;
}) {
  const hasChildren = node.children.length > 0;
  const expanded = hasChildren && expandedIds.has(node.id);

  return (
    <li>
      <div className="tree-item">
        {hasChildren ? (
          <button
            type="button"
            className={`title-expand-toggle ${expanded ? "expanded" : ""}`}
            onClick={() => onToggle(node.id)}
            aria-label={expanded ? `Collapse ${node.name}` : `Expand ${node.name}`}
          >
            ›
          </button>
        ) : (
          <span className="title-expand-toggle-spacer" aria-hidden />
        )}
        <TypeBadge value={node.title_type} />
        <strong title={node.name}>{node.name}</strong>
        <StatusBadge value={node.status} />
      </div>
      {expanded && (
        <ul>
          {node.children.map((c) => (
            <TreeNode
              key={c.id}
              node={c}
              expandedIds={expandedIds}
              onToggle={onToggle}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function DashboardPage() {
  const [titles, setTitles] = useState<Title[]>([]);
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [tree, setTree] = useState<TitleTree[]>([]);
  const [treeLoading, setTreeLoading] = useState(true);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(() => new Set());

  useEffect(() => {
    titlesApi.list().then(setTitles).catch(() => setTitles([]));
    assetsApi.list().then(setAssets).catch(() => setAssets([]));
    setTreeLoading(true);
    titlesApi
      .tree()
      .then(setTree)
      .catch(() => setTree([]))
      .finally(() => setTreeLoading(false));
  }, []);

  const hierarchyRoots = useMemo(() => tree.filter(isHierarchyRoot), [tree]);
  const published = titles.filter((t) => t.status === "published").length;
  const readyAssets = assets.filter((a) => a.status === "ready").length;
  const recentAssets = assets.slice(0, 5);

  const toggleExpanded = (id: number) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <>
      <PageHeader
        title="Overview"
        description="Title management and media asset inventory for your streaming library."
      />

      <div className="stats">
        <StatCard
          icon={Film}
          value={titles.length}
          label="Titles"
          context="Across all types"
        />
        <StatCard
          icon={CheckCircle2}
          value={published}
          label="Published"
          context={published === 0 ? "None live yet" : "Live in catalog"}
          attention={published === 0}
        />
        <StatCard
          icon={HardDrive}
          value={assets.length}
          label="Media assets"
          context="Linked to titles"
        />
        <StatCard
          icon={Play}
          value={readyAssets}
          label="Ready for playback"
          context={
            assets.length > 0
              ? `${readyAssets} of ${assets.length} processed`
              : "No assets yet"
          }
        />
      </div>

      <div className="dashboard-grid">
        <section className="card card-padded">
          <div className="panel-header">
            <h3>Title hierarchy</h3>
            <Link to="/titles" className="panel-link">
              Manage titles →
            </Link>
          </div>
          {treeLoading ? (
            <p className="empty">Loading hierarchy…</p>
          ) : hierarchyRoots.length === 0 ? (
            <p className="empty">No series or movies yet.</p>
          ) : (
            <ul className="tree">
              {hierarchyRoots.map((n) => (
                <TreeNode
                  key={n.id}
                  node={n}
                  expandedIds={expandedIds}
                  onToggle={toggleExpanded}
                />
              ))}
            </ul>
          )}
        </section>

        <section className="card card-padded">
          <div className="panel-header">
            <h3>Recent assets</h3>
            <Link to="/assets" className="panel-link">
              Manage assets →
            </Link>
          </div>
          {recentAssets.length === 0 ? (
            <p className="empty">No assets yet.</p>
          ) : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Type</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {recentAssets.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <div className="asset-row-main">
                          {isImageUri(a.storage_uri) ? (
                            <img
                              src={a.storage_uri}
                              alt=""
                              className="asset-thumb"
                              loading="lazy"
                            />
                          ) : (
                            <div className="asset-thumb asset-thumb-fallback" aria-hidden>
                              <HardDrive size={16} />
                            </div>
                          )}
                          <div className="asset-row-label">
                            <strong>{assetPrimaryLabel(a.filename, a.asset_type)}</strong>
                            <span className="mono" title={a.filename}>
                              {a.filename}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <TypeBadge value={a.asset_type} />
                      </td>
                      <td>
                        <StatusBadge
                          value={a.status}
                          pulse={a.status === "processing"}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
