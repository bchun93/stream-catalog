import { useCallback, useEffect, useState } from "react";
import { Package, Plus, ShieldCheck } from "lucide-react";
import { deliveryApi, titlesApi } from "../api/client";
import {
  CreatePackageForm,
  type CreatePackagePayload,
  deliveryModeLabel,
  monetizationLabel,
} from "../components/CreatePackageForm";
import { Modal } from "../components/Modal";
import { StatusBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { Sheet } from "../components/ui/Sheet";
import { TableSkeleton } from "../components/ui/TableSkeleton";
import type {
  DeliveryPackage,
  DeliveryProfile,
  DeliveryProfileSummary,
  PackageValidationResponse,
  Title,
  ValidationFinding,
} from "../types";

type DeliveryTab = "packages" | "profiles";

function formatDealDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function findingStatusClass(status: ValidationFinding["status"]): string {
  if (status === "pass") return "validation-status pass";
  if (status === "fail") return "validation-status fail";
  return "validation-status skip";
}

function summaryLabel(summary: PackageValidationResponse["summary"]): string {
  if (summary === "pass") return "Pass";
  if (summary === "fail") return "Fail";
  return "Incomplete";
}

function SpecSection({ title, value }: { title: string; value: unknown }) {
  if (value == null) return null;
  return (
    <section className="profile-spec-section">
      <h3>{title}</h3>
      <pre className="profile-spec-pre">{JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}

export function DeliveryPage() {
  const [tab, setTab] = useState<DeliveryTab>("packages");
  const [packages, setPackages] = useState<DeliveryPackage[]>([]);
  const [profiles, setProfiles] = useState<DeliveryProfileSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [catalogTitles, setCatalogTitles] = useState<Title[]>([]);
  const [titlesLoading, setTitlesLoading] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<DeliveryProfile | null>(null);
  const [profileDetailLoading, setProfileDetailLoading] = useState(false);
  const [validation, setValidation] = useState<PackageValidationResponse | null>(null);
  const [validatingId, setValidatingId] = useState<number | null>(null);

  const loadPackages = useCallback(() => {
    setLoading(true);
    setError(null);
    deliveryApi
      .list()
      .then(setPackages)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load packages"))
      .finally(() => setLoading(false));
  }, []);

  const loadProfiles = useCallback(() => {
    setProfilesLoading(true);
    deliveryApi
      .listProfiles(true)
      .then(setProfiles)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load profiles"))
      .finally(() => setProfilesLoading(false));
  }, []);

  useEffect(() => {
    loadPackages();
    loadProfiles();
  }, [loadPackages, loadProfiles]);

  useEffect(() => {
    if (!createOpen) return;
    setTitlesLoading(true);
    Promise.all([
      titlesApi.list({ title_type: "movie", limit: "500" }),
      titlesApi.list({ title_type: "series", limit: "500" }),
    ])
      .then(([movies, series]) => setCatalogTitles([...movies, ...series]))
      .catch(() => setCatalogTitles([]))
      .finally(() => setTitlesLoading(false));
  }, [createOpen]);

  const handleCreated = async (data: CreatePackagePayload) => {
    const created = await deliveryApi.create({
      name: data.name,
      profile_id: data.profile_id,
      buyer_slug: data.buyer_slug,
      deal_date: data.deal_date,
      delivery_mode: data.delivery_mode,
      monetization: data.monetization,
      title_ids: data.title_ids,
      status: "draft",
    });
    setPackages((current) => [created, ...current]);
    setCreateOpen(false);
  };

  const openProfile = async (id: number) => {
    setProfileDetailLoading(true);
    setSelectedProfile(null);
    try {
      const detail = await deliveryApi.getProfile(id);
      setSelectedProfile(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load profile");
    } finally {
      setProfileDetailLoading(false);
    }
  };

  const runValidate = async (pkg: DeliveryPackage) => {
    setValidatingId(pkg.id);
    setError(null);
    try {
      const result = await deliveryApi.validate(pkg.id);
      setValidation(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Validation failed");
    } finally {
      setValidatingId(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Delivery"
        description="Delivery profiles define platform contracts. Packages assemble titles against a profile and can be validated before transform."
        actions={
          tab === "packages" ? (
            <Button
              variant="primary"
              icon={<Plus size={16} />}
              onClick={() => setCreateOpen(true)}
            >
              Create a package
            </Button>
          ) : null
        }
      />

      <div className="delivery-tabs" role="tablist" aria-label="Delivery sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "packages"}
          className={tab === "packages" ? "delivery-tab active" : "delivery-tab"}
          onClick={() => setTab("packages")}
        >
          Packages
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "profiles"}
          className={tab === "profiles" ? "delivery-tab active" : "delivery-tab"}
          onClick={() => setTab("profiles")}
        >
          Profiles
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <Button
            variant="ghost"
            onClick={() => {
              loadPackages();
              loadProfiles();
            }}
          >
            Retry
          </Button>
        </div>
      )}

      {tab === "packages" ? (
        <div className="card">
          {loading ? (
            <TableSkeleton rows={6} cols={9} />
          ) : packages.length === 0 ? (
            <EmptyState
              icon={Package}
              title="No delivery packages yet"
              description="Create a package against a delivery profile to start assembling a buyer delivery."
              action={
                <Button variant="primary" onClick={() => setCreateOpen(true)}>
                  Create a package
                </Button>
              }
            />
          ) : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Package</th>
                    <th>Profile</th>
                    <th>Buyer</th>
                    <th>Deal date</th>
                    <th>Titles</th>
                    <th>Delivery</th>
                    <th>Monetization</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {packages.map((pkg) => (
                    <tr key={pkg.id}>
                      <td>
                        <strong>{pkg.name}</strong>
                      </td>
                      <td>{pkg.profile?.name ?? "—"}</td>
                      <td>{pkg.buyer_slug ?? "—"}</td>
                      <td>{formatDealDate(pkg.deal_date)}</td>
                      <td className="num">{pkg.title_count ?? pkg.titles?.length ?? 0}</td>
                      <td>{deliveryModeLabel(pkg.delivery_mode)}</td>
                      <td>{monetizationLabel(pkg.monetization)}</td>
                      <td>
                        <StatusBadge value={pkg.status} />
                      </td>
                      <td>
                        <Button
                          variant="subtle"
                          icon={<ShieldCheck size={14} />}
                          disabled={validatingId === pkg.id || !pkg.profile_id}
                          onClick={() => runValidate(pkg)}
                        >
                          {validatingId === pkg.id ? "Validating…" : "Validate"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="card">
          {profilesLoading ? (
            <TableSkeleton rows={4} cols={5} />
          ) : profiles.length === 0 ? (
            <EmptyState
              icon={ShieldCheck}
              title="No delivery profiles"
              description="Profiles are seeded from YAML on API migrate (e.g. Amazon Prime Video SVOD)."
            />
          ) : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Profile</th>
                    <th>Platform</th>
                    <th>Channel</th>
                    <th>Version</th>
                    <th>Slug</th>
                  </tr>
                </thead>
                <tbody>
                  {profiles.map((profile) => (
                    <tr
                      key={profile.id}
                      className="clickable-row"
                      onClick={() => openProfile(profile.id)}
                    >
                      <td>
                        <strong>{profile.name}</strong>
                        {profile.description ? (
                          <div className="table-meta">{profile.description}</div>
                        ) : null}
                      </td>
                      <td>{profile.platform}</td>
                      <td>{profile.channel.toUpperCase()}</td>
                      <td className="num">v{profile.version}</td>
                      <td>
                        <span className="table-meta-id">{profile.slug}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {createOpen && (
        <Modal title="Create a package" wide onClose={() => setCreateOpen(false)}>
          <CreatePackageForm
            titles={catalogTitles}
            titlesLoading={titlesLoading}
            profiles={profiles}
            profilesLoading={profilesLoading}
            onCancel={() => setCreateOpen(false)}
            onSubmit={handleCreated}
          />
        </Modal>
      )}

      {(selectedProfile || profileDetailLoading) && (
        <Sheet
          wide
          title={selectedProfile?.name ?? "Delivery profile"}
          onClose={() => setSelectedProfile(null)}
        >
          {profileDetailLoading || !selectedProfile ? (
            <p className="empty">Loading profile…</p>
          ) : (
            <div className="profile-detail">
              <p className="field-hint">
                {selectedProfile.platform} · {selectedProfile.channel.toUpperCase()} · v
                {selectedProfile.version}
              </p>
              {selectedProfile.description ? <p>{selectedProfile.description}</p> : null}
              <SpecSection title="Video" value={selectedProfile.spec.video} />
              <SpecSection title="Audio" value={selectedProfile.spec.audio} />
              <SpecSection title="Loudness" value={selectedProfile.spec.loudness} />
              <SpecSection title="Integrity" value={selectedProfile.spec.integrity} />
              <SpecSection title="Manifest" value={selectedProfile.spec.manifest} />
            </div>
          )}
        </Sheet>
      )}

      {validation && (
        <Modal
          title={`Validation — ${summaryLabel(validation.summary)}`}
          wide
          onClose={() => setValidation(null)}
        >
          <div className="validation-summary">
            <span className={`validation-pill ${validation.summary}`}>
              {summaryLabel(validation.summary)}
            </span>
            <span>
              {validation.pass_count} pass · {validation.fail_count} fail ·{" "}
              {validation.skip_count} skip
            </span>
            <span className="table-meta-id">{validation.profile_slug}</span>
          </div>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Rule</th>
                  <th>Title</th>
                  <th>Message</th>
                  <th>Observed</th>
                  <th>Expected</th>
                </tr>
              </thead>
              <tbody>
                {validation.findings.map((finding, index) => (
                  <tr key={`${finding.rule_id}-${finding.asset_id ?? "x"}-${index}`}>
                    <td>
                      <span className={findingStatusClass(finding.status)}>
                        {finding.status}
                      </span>
                    </td>
                    <td>
                      <code>{finding.rule_id}</code>
                    </td>
                    <td>{finding.title_name ?? "—"}</td>
                    <td>{finding.message}</td>
                    <td className="mono">{finding.observed ?? "—"}</td>
                    <td className="mono">{finding.expected ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
    </>
  );
}
