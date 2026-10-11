import type { LucideIcon } from "lucide-react";
import {
  Cloud,
  Database,
  Film,
  GitBranch,
  HardDrive,
  KeyRound,
  Layers,
  Monitor,
  Package,
  ScanSearch,
  Server,
} from "lucide-react";
import { PageHeader } from "../components/ui/PageHeader";

interface ArchNode {
  icon: LucideIcon;
  name: string;
  detail: string;
}

const CLIENT: ArchNode = {
  icon: Monitor,
  name: "Amplify",
  detail: "React admin UI",
};

const API: ArchNode = {
  icon: Server,
  name: "Render",
  detail: "FastAPI REST API",
};

const DATA_SERVICES: ArchNode[] = [
  { icon: Database, name: "Neon Postgres", detail: "Titles, assets, packages" },
  { icon: Cloud, name: "S3 ingest bucket", detail: "Uploads, masters, MEC XML" },
  { icon: Film, name: "TMDB", detail: "Metadata import" },
];

const QC_PIPELINE: ArchNode[] = [
  { icon: ScanSearch, name: "Rekognition", detail: "Async video QC" },
  { icon: Layers, name: "SNS / SQS", detail: "Completion fan-out" },
  { icon: Database, name: "DynamoDB", detail: "Jobs and detections" },
];

const FLOWS = [
  {
    name: "Catalog CRUD",
    path: "UI → /api/v1/titles · /assets → Postgres",
    detail: "List and view are unauthenticated. Create, update, and delete require the admin token.",
  },
  {
    name: "Metadata import",
    path: "UI → /api/v1/metadata → TMDB → title write",
    detail: "Search and preview pull TMDB. Applying a hierarchy writes titles with the admin token.",
  },
  {
    name: "S3 ingest / upload",
    path: "UI → /api/v1/storage · /ingest → S3",
    detail: "Browse, upload, and ingest jobs use the ingest operator token.",
  },
  {
    name: "MEC delivery",
    path: "UI → generate package → XML in S3",
    detail: "Package records live in Postgres. Generated MEC XML is written to the ingest bucket.",
  },
  {
    name: "Rekognition QC",
    path: "UI → analyze → Rekognition → SNS/SQS → consumer → DynamoDB",
    detail: "Analyze and drain require the admin token. The scheduled consumer uses a separate secret.",
  },
] as const;

const AUTH_TIERS = [
  {
    tier: "Public reads",
    header: "none",
    protects: "List and get titles, assets, metadata search, delivery profiles",
  },
  {
    tier: "Admin",
    header: "X-Admin-Token",
    protects: "Catalog mutations, artwork AI, Rekognition analyze / drain",
  },
  {
    tier: "Ingest operator",
    header: "X-Ingest-Token",
    protects: "S3 browse, upload, object mutations, ingest jobs",
  },
  {
    tier: "Rekognition consumer",
    header: "X-Rekognition-Consumer-Secret",
    protects: "Scheduled SQS drain that writes detections",
  },
] as const;

const DOMAIN_LAYERS = [
  {
    layer: "Titles",
    icon: Film,
    responsibility:
      "Slug, metadata, lifecycle (draft → published), parent/child hierarchy, territories, availability windows",
  },
  {
    layer: "Media assets",
    icon: HardDrive,
    responsibility:
      "Typed assets (video master, poster, subtitle, …), storage URI, technical metadata, processing status",
  },
  {
    layer: "Delivery",
    icon: Package,
    responsibility:
      "Partner profiles, packages, validation findings, and generated MEC XML",
  },
  {
    layer: "API",
    icon: Server,
    responsibility: "CRUD, search/filter, title tree, ingest, storage, and QC endpoints under /api/v1",
  },
  {
    layer: "UI",
    icon: Monitor,
    responsibility: "Internal catalog tool: dashboard, title editor, asset registry, S3 browser, delivery",
  },
] as const;

function ArchCard({ node, variant = "default" }: { node: ArchNode; variant?: "default" | "hub" }) {
  const Icon = node.icon;
  return (
    <div className={`arch-node${variant === "hub" ? " arch-node-hub" : ""}`}>
      <span className="arch-node-icon" aria-hidden>
        <Icon size={18} strokeWidth={1.75} />
      </span>
      <strong>{node.name}</strong>
      <span>{node.detail}</span>
    </div>
  );
}

export function ArchitecturePage() {
  return (
    <div className="arch-page">
      <PageHeader
        title="System architecture"
        description="How Relay is deployed and how requests move through the catalog, ingest, and QC stack."
      />

      <section className="card card-padded">
        <div className="panel-header">
          <h3>Deploy topology</h3>
        </div>
        <p className="arch-source">
          <GitBranch size={14} strokeWidth={1.75} aria-hidden />
          <span>
            GitHub <span className="mono">main</span> deploys the UI to Amplify and the API to Render.
          </span>
        </p>
        <div
          className="arch-topo"
          role="img"
          aria-label="Amplify React UI talks to a Render FastAPI service, which uses Neon Postgres, S3, TMDB, and a Rekognition QC pipeline."
        >
          <div className="arch-topo-lane">
            <span className="arch-lane-label">Client</span>
            <ArchCard node={CLIENT} />
          </div>
          <div className="arch-connector" aria-hidden>
            →
          </div>
          <div className="arch-topo-lane">
            <span className="arch-lane-label">API</span>
            <ArchCard node={API} variant="hub" />
          </div>
          <div className="arch-connector" aria-hidden>
            →
          </div>
          <div className="arch-topo-lane">
            <span className="arch-lane-label">Data and services</span>
            <div className="arch-node-stack">
              {DATA_SERVICES.map((node) => (
                <ArchCard key={node.name} node={node} />
              ))}
              <div className="arch-qc">
                <span className="arch-lane-label">QC pipeline</span>
                <div className="arch-chain">
                  {QC_PIPELINE.map((node, index) => (
                    <div key={node.name} className="arch-chain-item">
                      {index > 0 && (
                        <span className="arch-chain-arrow" aria-hidden>
                          →
                        </span>
                      )}
                      <ArchCard node={node} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
        <p className="arch-note">
          Local development uses SQLite instead of Neon. S3, TMDB, and Rekognition only appear when their
          environment variables are set.
        </p>
      </section>

      <section className="card card-padded">
        <div className="panel-header">
          <h3>Request flows</h3>
        </div>
        <ol className="arch-flows">
          {FLOWS.map((flow) => (
            <li key={flow.name} className="arch-flow">
              <div className="arch-flow-name">{flow.name}</div>
              <div className="arch-flow-body">
                <p className="arch-flow-path mono">{flow.path}</p>
                <p className="arch-flow-detail">{flow.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="card card-padded">
        <div className="panel-header">
          <h3>
            <span className="arch-section-title">
              <KeyRound size={16} strokeWidth={1.75} aria-hidden />
              Auth tiers
            </span>
          </h3>
        </div>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Tier</th>
                <th>Header</th>
                <th>Protects</th>
              </tr>
            </thead>
            <tbody>
              {AUTH_TIERS.map((row) => (
                <tr key={row.tier}>
                  <td>{row.tier}</td>
                  <td>
                    <span className="mono">{row.header}</span>
                  </td>
                  <td className="text-secondary">{row.protects}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card card-padded">
        <div className="panel-header">
          <h3>Domain layers</h3>
        </div>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Layer</th>
                <th>Responsibility</th>
              </tr>
            </thead>
            <tbody>
              {DOMAIN_LAYERS.map((row) => {
                const Icon = row.icon;
                return (
                  <tr key={row.layer}>
                    <td>
                      <span className="arch-layer-name">
                        <Icon size={16} strokeWidth={1.75} aria-hidden />
                        {row.layer}
                      </span>
                    </td>
                    <td className="text-secondary">{row.responsibility}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
