import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { assetsApi, titlesApi } from "../api/client";
import type { MediaAsset, Title, TitleTree } from "../types";
import { Badge } from "../components/Badge";

function TreeNode({ node }: { node: TitleTree }) {
  return (
    <li>
      <div className="tree-item">
        <Badge value={node.title_type} kind="type" />
        <strong>{node.name}</strong>
        <Badge value={node.status} />
      </div>
      {node.children.length > 0 && (
        <ul>
          {node.children.map((c) => (
            <TreeNode key={c.id} node={c} />
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

  useEffect(() => {
    Promise.all([titlesApi.list(), assetsApi.list(), titlesApi.tree()]).then(
      ([t, a, tr]) => {
        setTitles(t);
        setAssets(a);
        setTree(tr);
      }
    );
  }, []);

  const published = titles.filter((t) => t.status === "published").length;
  const readyAssets = assets.filter((a) => a.status === "ready").length;

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
          {tree.length === 0 ? (
            <p className="empty">No titles yet.</p>
          ) : (
            <ul className="tree">
              {tree.map((n) => (
                <TreeNode key={n.id} node={n} />
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
