import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CircleX, Film, HardDrive, Package } from "lucide-react";
import { assetsApi, titlesApi } from "../api/client";
import type { Title, TitleTree } from "../types";
import { StatusBadge, TypeBadge } from "../components/ui/Badge";
import { PageHeader } from "../components/ui/PageHeader";
import { StatCard } from "../components/ui/StatCard";
import { TitlesByTypeStatCard } from "../components/ui/TitlesByTypeStatCard";
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

/** Cleared for handoff — scheduled or already published. */
function isReadyForDelivery(status: Title["status"]): boolean {
  return status === "scheduled" || status === "published";
}

/** Terminal non-delivery state — archived titles. */
function isRejected(status: Title["status"]): boolean {
  return status === "archived";
}

export function DashboardPage() {
  const [titles, setTitles] = useState<Title[]>([]);
  const [assets, setAssets] = useState<Awaited<ReturnType<typeof assetsApi.list>>>([]);
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
  const readyForDelivery = useMemo(
    () => titles.filter((t) => isReadyForDelivery(t.status)).length,
    [titles]
  );
  const rejected = useMemo(
    () => titles.filter((t) => isRejected(t.status)).length,
    [titles]
  );
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
        <TitlesByTypeStatCard icon={Film} titles={titles} />
        <StatCard
          icon={Package}
          value={readyForDelivery}
          label="Titles ready for delivery"
          context={
            readyForDelivery === 0
              ? "No scheduled or published titles"
              : "Scheduled or published"
          }
          attention={readyForDelivery === 0}
        />
        <StatCard
          icon={CircleX}
          value={rejected}
          label="Rejected titles"
          context={rejected === 0 ? "None archived" : "Archived / rejected"}
          attention={rejected > 0}
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
