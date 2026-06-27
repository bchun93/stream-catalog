import { useCallback, useEffect, useState } from "react";
import { Package, Plus } from "lucide-react";
import { deliveryApi } from "../api/client";
import { CreatePackageForm, deliveryModeLabel, monetizationLabel } from "../components/CreatePackageForm";
import { Modal } from "../components/Modal";
import { StatusBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { TableSkeleton } from "../components/ui/TableSkeleton";
import type { DeliveryMode, DeliveryPackage, MonetizationModel } from "../types";

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

export function DeliveryPage() {
  const [packages, setPackages] = useState<DeliveryPackage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    deliveryApi
      .list()
      .then(setPackages)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load packages"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreated = async (data: {
    name: string;
    buyer_slug: string;
    deal_date: string;
    delivery_mode: DeliveryMode;
    monetization: MonetizationModel;
  }) => {
    const created = await deliveryApi.create({
      name: data.name,
      buyer_slug: data.buyer_slug,
      deal_date: data.deal_date,
      delivery_mode: data.delivery_mode,
      monetization: data.monetization,
      status: "draft",
    });
    setPackages((current) => [created, ...current]);
    setCreateOpen(false);
  };

  return (
    <>
      <PageHeader
        title="Delivery"
        description="Assemble and track delivery packages for buyers."
        actions={
          <Button
            variant="primary"
            icon={<Plus size={16} />}
            onClick={() => setCreateOpen(true)}
          >
            Create a package
          </Button>
        }
      />

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <Button variant="ghost" onClick={load}>
            Retry
          </Button>
        </div>
      )}

      <div className="card">
        {loading ? (
          <TableSkeleton rows={6} cols={7} />
        ) : packages.length === 0 ? (
          <EmptyState
            icon={Package}
            title="No delivery packages yet"
            description="Create a package to start building a buyer delivery."
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
                  <th>Buyer</th>
                  <th>Deal date</th>
                  <th>Delivery</th>
                  <th>Monetization</th>
                  <th>Status</th>
                  <th>Slug</th>
                </tr>
              </thead>
              <tbody>
                {packages.map((pkg) => (
                  <tr key={pkg.id}>
                    <td>
                      <strong>{pkg.name}</strong>
                    </td>
                    <td>{pkg.buyer_slug ?? "—"}</td>
                    <td>{formatDealDate(pkg.deal_date)}</td>
                    <td>{deliveryModeLabel(pkg.delivery_mode)}</td>
                    <td>{monetizationLabel(pkg.monetization)}</td>
                    <td>
                      <StatusBadge value={pkg.status} />
                    </td>
                    <td>
                      <span className="table-meta-id" title={pkg.slug}>
                        {pkg.slug}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {createOpen && (
        <Modal title="Create a package" onClose={() => setCreateOpen(false)}>
          <CreatePackageForm
            onCancel={() => setCreateOpen(false)}
            onSubmit={handleCreated}
          />
        </Modal>
      )}
    </>
  );
}
