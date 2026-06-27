import { useEffect, useState } from "react";
import type { DeliveryMode, MonetizationModel } from "../types";
import { slugify, suggestPackageName, todayIsoDate } from "../utils/slug";

export const DELIVERY_MODE_OPTIONS: { value: DeliveryMode; label: string }[] = [
  { value: "vod", label: "VOD" },
  { value: "linear", label: "Linear" },
];

export const MONETIZATION_OPTIONS: { value: MonetizationModel; label: string }[] = [
  { value: "svod", label: "SVOD" },
  { value: "avod", label: "AVOD" },
  { value: "tvod", label: "TVOD" },
  { value: "fast", label: "FAST" },
];

export interface CreatePackagePayload {
  name: string;
  buyer_slug: string;
  deal_date: string;
  delivery_mode: DeliveryMode;
  monetization: MonetizationModel;
}

interface CreatePackageFormProps {
  onCancel: () => void;
  onSubmit: (data: CreatePackagePayload) => Promise<void>;
}

export function CreatePackageForm({ onCancel, onSubmit }: CreatePackageFormProps) {
  const [buyerSlug, setBuyerSlug] = useState("");
  const [dealDate, setDealDate] = useState(todayIsoDate);
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("vod");
  const [monetization, setMonetization] = useState<MonetizationModel>("svod");
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recommendation = suggestPackageName(buyerSlug, dealDate);

  useEffect(() => {
    if (!nameTouched) {
      setName(recommendation);
    }
  }, [recommendation, nameTouched]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Package name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        name: trimmedName,
        buyer_slug: slugify(buyerSlug || "buyer"),
        deal_date: dealDate,
        delivery_mode: deliveryMode,
        monetization,
      });
      onCancel();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create package");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="package-form" onSubmit={handleSubmit}>
      {error && <div className="error-banner">{error}</div>}

      <div className="form-grid">
        <label className="form-span-2">
          Buyer slug
          <input
            value={buyerSlug}
            onChange={(e) => setBuyerSlug(e.target.value)}
            placeholder="acme-streaming"
            autoFocus
          />
          <span className="field-hint">
            Short identifier for the buyer (letters, numbers, hyphens).
          </span>
        </label>

        <label>
          Deal date
          <input
            type="date"
            value={dealDate}
            onChange={(e) => setDealDate(e.target.value)}
          />
        </label>

        <label>
          Delivery
          <select
            value={deliveryMode}
            onChange={(e) => setDeliveryMode(e.target.value as DeliveryMode)}
          >
            {DELIVERY_MODE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Monetization
          <select
            value={monetization}
            onChange={(e) => setMonetization(e.target.value as MonetizationModel)}
          >
            {MONETIZATION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="form-span-2">
          Package name
          <input
            value={name}
            onChange={(e) => {
              setNameTouched(true);
              setName(e.target.value);
            }}
            placeholder={recommendation}
          />
          <span className="field-hint">
            Recommended: <strong>{recommendation}</strong> — buyer slug plus deal date.
          </span>
        </label>
      </div>

      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Creating…" : "Create package"}
        </button>
      </div>
    </form>
  );
}

export function deliveryModeLabel(value: DeliveryMode): string {
  return DELIVERY_MODE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

export function monetizationLabel(value: MonetizationModel): string {
  return MONETIZATION_OPTIONS.find((option) => option.value === value)?.label ?? value;
}
