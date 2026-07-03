import { useEffect, useMemo, useState } from "react";
import type { DeliveryMode, MonetizationModel, Title, TitleType } from "../types";
import { TypeBadge } from "./ui/Badge";
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
  title_ids: number[];
}

interface CreatePackageFormProps {
  titles: Title[];
  titlesLoading?: boolean;
  onCancel: () => void;
  onSubmit: (data: CreatePackagePayload) => Promise<void>;
}

const PACKAGE_PICKER_TITLE_TYPES = new Set<TitleType>(["movie", "series"]);

function isPackagePickerTitle(title: Title): boolean {
  return PACKAGE_PICKER_TITLE_TYPES.has(title.title_type);
}

function titleMatchesSearch(title: Title, query: string): boolean {
  const haystack = [
    title.name,
    title.internal_id ?? "",
    title.slug,
    title.studio ?? "",
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function displayTitleId(title: Pick<Title, "internal_id" | "slug">): string {
  return title.internal_id?.trim() || title.slug;
}

export function CreatePackageForm({
  titles,
  titlesLoading = false,
  onCancel,
  onSubmit,
}: CreatePackageFormProps) {
  const [buyerSlug, setBuyerSlug] = useState("");
  const [dealDate, setDealDate] = useState(todayIsoDate);
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("vod");
  const [monetization, setMonetization] = useState<MonetizationModel>("svod");
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [selectedTitleIds, setSelectedTitleIds] = useState<Set<number>>(() => new Set());
  const [titleSearch, setTitleSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recommendation = suggestPackageName(buyerSlug, dealDate);
  const normalizedSearch = titleSearch.trim().toLowerCase();

  const filteredTitles = useMemo(() => {
    const eligible = titles.filter(isPackagePickerTitle);
    const sorted = [...eligible].sort((a, b) => a.name.localeCompare(b.name));
    if (!normalizedSearch) return sorted;
    return sorted.filter((title) => titleMatchesSearch(title, normalizedSearch));
  }, [titles, normalizedSearch]);

  useEffect(() => {
    if (!nameTouched) {
      setName(recommendation);
    }
  }, [recommendation, nameTouched]);

  const toggleTitle = (titleId: number) => {
    setSelectedTitleIds((current) => {
      const next = new Set(current);
      if (next.has(titleId)) {
        next.delete(titleId);
      } else {
        next.add(titleId);
      }
      return next;
    });
  };

  const selectFilteredTitles = () => {
    setSelectedTitleIds((current) => {
      const next = new Set(current);
      for (const title of filteredTitles) {
        next.add(title.id);
      }
      return next;
    });
  };

  const clearSelectedTitles = () => {
    setSelectedTitleIds(new Set());
  };

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
        title_ids: [...selectedTitleIds],
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

        <div className="form-span-2 package-title-picker">
          <div className="package-title-picker-header">
            <div>
              <span className="package-title-picker-label">Titles</span>
              <span className="field-hint">
                Optional — choose movies or series to include in this package.
              </span>
            </div>
            <span className="package-title-picker-count">
              {selectedTitleIds.size} selected
            </span>
          </div>

          <div className="package-title-picker-toolbar">
            <input
              type="search"
              value={titleSearch}
              onChange={(e) => setTitleSearch(e.target.value)}
              placeholder="Search titles…"
              aria-label="Search titles"
            />
            <button
              type="button"
              className="btn btn-ghost"
              onClick={selectFilteredTitles}
              disabled={titlesLoading || filteredTitles.length === 0}
            >
              Select shown
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={clearSelectedTitles}
              disabled={titlesLoading || selectedTitleIds.size === 0}
            >
              Clear
            </button>
          </div>

          <div className="package-title-picker-list" aria-busy={titlesLoading}>
            {titlesLoading ? (
              <p className="empty">Loading titles…</p>
            ) : titles.filter(isPackagePickerTitle).length === 0 ? (
              <p className="empty">No movies or series in the catalog yet.</p>
            ) : filteredTitles.length === 0 ? (
              <p className="empty">No titles match your search.</p>
            ) : (
              <ul>
                {filteredTitles.map((title) => {
                  const checked = selectedTitleIds.has(title.id);
                  return (
                    <li key={title.id}>
                      <label className="package-title-picker-row">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleTitle(title.id)}
                        />
                        <span className="package-title-picker-row-main">
                          <strong>{title.name}</strong>
                          <span className="package-title-picker-row-meta">
                            <TypeBadge value={title.title_type} />
                            <span className="table-meta-id">{displayTitleId(title)}</span>
                            {title.release_year ? (
                              <span>{title.release_year}</span>
                            ) : null}
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
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
