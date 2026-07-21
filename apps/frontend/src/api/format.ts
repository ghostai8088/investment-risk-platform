/**
 * Render a governed value VERBATIM. Decimal values arrive from the API as JSON **strings** and must
 * never be re-parsed — a `Number()` / `parseFloat` here would silently corrupt the exact decimal
 * (OQ-FE-1-7; the FE-2 exhaustive decimal-contract guard exists precisely to keep this true). This
 * is the single renderer the whole read surface uses so the contract holds on every screen.
 */
export function verbatim(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : String(value);
}

/** A short, hover-expandable form of a long id for provenance strips (full id via `title`). */
export function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}
