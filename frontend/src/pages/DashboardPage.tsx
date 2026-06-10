import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { assetsApi, titlesApi } from "../api/client";
import type { MediaAsset, Title, TitleTree } from "../types";
import { Badge } from "../components/Badge";

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
        <Badge value={node.title_type} kind="type" />
        <strong>{node.name}</strong>
        <Badge value={node.status} />
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

  const hierarchyRoots = useMemo(
    () => tree.filter(isHierarchyRoot),
    [tree]
  );

  const published = titles.filter((t) => t.status === "published").length;
  const readyAssets = assets.filter((a) => a.status === "ready").length;

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
      <header className="page-header">
        <div>
          <h1>Catalog overview</h1>
          <p>Title management and media asset inventory for your streaming library.</p>
        </div>
      </header>

      <div className="stats">
        <div className="stat-card">
          <strong>{titles.length}</strong>
          <span>Titles</span>
        </div>
        <div className="stat-card">
          <strong>{published}</strong>
          <span>Published</span>
        </div>
        <div className="stat-card">
          <strong>{assets.length}</strong>
          <span>Media assets</span>
        </div>
        <div className="stat-card">
          <strong>{readyAssets}</strong>
          <span>Ready for playback</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        <section className="card" style={{ padding: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem" }}>Title hierarchy</h3>
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
          <p style={{ marginTop: "1rem" }}>
            <Link to="/titles">Manage titles →</Link>
          </p>
        </section>

        <section className="card" style={{ padding: "1.25rem" }}>
          <h3 style={{ margin: "0 0 1rem" }}>Recent assets</h3>
          {assets.length === 0 ? (
            <p className="empty">No assets yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Type</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {assets.slice(0, 5).map((a) => (
                  <tr key={a.id}>
                    <td className="mono">{a.filename}</td>
                    <td>
                      <Badge value={a.asset_type} kind="asset" />
                    </td>
                    <td>
                      <Badge value={a.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p style={{ marginTop: "1rem" }}>
            <Link to="/assets">Manage assets →</Link>
          </p>
        </section>
      </div>
    </>
  );
}
