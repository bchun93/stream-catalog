export function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "package";
}

export function suggestPackageName(buyerSlug: string, dealDate: string): string {
  const buyer = slugify(buyerSlug || "buyer");
  const when = dealDate || new Date().toISOString().slice(0, 10);
  return `${buyer}-${when}`;
}

export function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}
