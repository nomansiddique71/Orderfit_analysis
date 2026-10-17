import type { Plan } from "./api";

// INR uses lakh grouping (5,00,000); everything else western grouping.
export function money(n: number | null | undefined, currency = "USD", opts: { sign?: boolean } = {}) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const locale = currency === "INR" ? "en-IN" : "en-US";
  const s = new Intl.NumberFormat(locale, { maximumFractionDigits: Math.abs(n) % 1 ? 2 : 0 }).format(Math.abs(n));
  const sym = currency === "USD" ? "$" : currency === "INR" ? "₹" : `${currency} `;
  const sign = n < 0 ? "−" : opts.sign && n > 0 ? "+" : "";
  return `${sign}${sym}${s}`;
}

// Plain-language name for a plan (no internal IDs on screen).
export function planTitle(p: Plan, currency = "USD"): string {
  if (p.id === "decline") return "Decline the order";
  if (p.id === "accept-as-is") return "Accept as it is";
  const parts: string[] = [];
  if (p.advance_pct > 0) parts.push(`Ask the customer for ${Math.round(p.advance_pct * 100)}% upfront`);
  if (p.supplier_extension) parts.push("ask the supplier to be paid later");
  if (p.financing) {
    const sized = p.id.startsWith("minloan") ? " (smallest safe amount)" : "";
    parts.push(`borrow ${money(p.financing.principal, currency)} from ${p.financing.lender}${sized}`);
  }
  const s = parts.join(" + ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function pct(x: number) {
  return `${Math.round(x * 100)}%`;
}
