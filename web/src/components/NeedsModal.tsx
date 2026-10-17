import { useEffect, useState } from "react";
import { ClipboardList, Plus, Sparkles, Trash2, X } from "lucide-react";
import { post, type DocView, type Need, type NeedsView, type Profile } from "../api";
import { Callout, LoadingButton, Pill, Spinner } from "./ui";

type Row = Record<string, string>;
const CURRENCIES = ["USD", "INR", "BDT", "EUR", "GBP", "SGD", "AED"];
const ORDER_KEYS = new Set(["order_value", "delivery_day", "payment_terms_days", "advance_received"]);
const LISTS: Record<string, { cols: [string, string, string][]; blank: Row }> = {
  recurring: { cols: [["label", "What", "Payroll"], ["amount", "Amount each time", "7000"], ["days", "Due on days", "15, 45"]], blank: { label: "", amount: "", days: "" } },
  receivables: { cols: [["label", "Who owes you", "Northlake Stores"], ["amount", "Amount", "4000"], ["day", "Expected on day", "25"]], blank: { label: "", amount: "", day: "" } },
  offers: { cols: [["lender", "Lender", "Harbor Bank"], ["principal", "Loan amount", "10000"], ["fee_pct", "Flat fee %", "2"], ["monthly_rate_pct", "Interest % / month", "1.5"], ["repay_day", "Repay on day", "90"]],
    blank: { lender: "", principal: "", fee_pct: "0", monthly_rate_pct: "0", repay_day: "" } },
};
const LIST_KEY: Record<string, keyof typeof LISTS> = { recurring: "recurring", receivables: "receivables", loan_offers: "offers" };

/** Business facts the owner already gave (or the sample's), as form rows. */
function fromProfile(p: Profile | null, usable: boolean) {
  const scalars: Row = { business_name: "", currency: "USD", opening_cash: "", reserve: "", max_financing_cost: "0" };
  const lists: Record<string, Row[]> = { recurring: [{ label: "Payroll", amount: "", days: "" }], receivables: [], offers: [] };
  if (!p || !usable) return { scalars, lists };
  Object.assign(scalars, { business_name: p.name, currency: p.currency, opening_cash: p.opening_cash, reserve: p.reserve, max_financing_cost: p.max_financing_cost });
  const groups = new Map<string, Row>();
  for (const o of p.obligations.filter((x) => Number(x.amount) < 0)) {
    const key = `${o.label}|${Math.abs(Number(o.amount))}`;
    const g = groups.get(key);
    if (g) g.days += `, ${o.day}`; else groups.set(key, { label: o.label, amount: String(Math.abs(Number(o.amount))), days: String(o.day) });
  }
  lists.recurring = [...groups.values()];
  lists.receivables = p.obligations.filter((x) => Number(x.amount) > 0).map((o) => ({ label: o.counterparty || o.label, amount: String(Number(o.amount)), day: String(o.day) }));
  return { scalars, lists };
}

export function NeedsModal({ edits, onClose, onSaved }: {
  edits: Record<string, string>;
  onClose: () => void;
  onSaved: (view: DocView | null, orderAnswers: Record<string, string>) => void;
}) {
  const [nv, setNv] = useState<NeedsView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState<"save" | "example" | null>(null);
  const [scalars, setScalars] = useState<Row>({});
  const [lists, setLists] = useState<Record<string, Row[]>>({});

  useEffect(() => {
    post<NeedsView>("/api/needs", { edits }).then((r) => {
      const usable = r.profile_source !== "default";
      const init = fromProfile(r.profile, usable);
      setScalars({ ...init.scalars, ...edits });
      setLists(init.lists);
      setNv(r);
    }).catch((e) => setErr((e as Error).message));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const businessAsked = !!nv?.needs.some((n) => !ORDER_KEYS.has(n.key));
  const missingRequired = nv?.needs.filter((n) => n.required && (LIST_KEY[n.key]
    ? !(lists[LIST_KEY[n.key]] ?? []).some((r) => r.amount?.trim())
    : !String(scalars[n.key] ?? "").trim())) ?? [];

  async function save() {
    setSaving("save"); setErr(null);
    try {
      const orderAnswers: Row = {};
      for (const k of ORDER_KEYS) if (scalars[k] !== undefined && nv?.needs.some((n) => n.key === k)) orderAnswers[k] = scalars[k];
      let view: DocView | null = null;
      if (businessAsked) {
        const filled = (k: string) => (lists[k] ?? []).filter((r) => Object.values(r).some((v) => v.trim()) && r[LISTS[k].cols[1][0]]?.trim());
        view = await post<DocView>("/api/profile", {
          name: scalars.business_name || "My business", currency: scalars.currency || "USD",
          opening_cash: Number(scalars.opening_cash), reserve: Number(scalars.reserve),
          max_financing_cost: Number(scalars.max_financing_cost || 0),
          recurring: filled("recurring").map((r) => ({ label: r.label || "Payment", amount: Number(r.amount), days: r.days })),
          receivables: filled("receivables").map((r) => ({ label: r.label || "Customer", amount: Number(r.amount), day: Number(r.day) })),
          offers: filled("offers").map((r) => ({ lender: r.lender || "Lender", principal: Number(r.principal), fee_pct: Number(r.fee_pct || 0),
            monthly_rate_pct: Number(r.monthly_rate_pct || 0), repay_day: Number(r.repay_day) })),
        });
      }
      onSaved(view, orderAnswers);
    } catch (e) { setErr((e as Error).message); } finally { setSaving(null); }
  }

  async function useExample() {
    setSaving("example"); setErr(null);
    try { onSaved(await post<DocView>("/api/profile", { use_example: true }), {}); }
    catch (e) { setErr((e as Error).message); } finally { setSaving(null); }
  }

  const field = (n: Need) => {
    const list = LIST_KEY[n.key];
    if (list) {
      const spec = LISTS[list];
      const rows = lists[list] ?? [];
      const set = (rs: Row[]) => setLists({ ...lists, [list]: rs });
      return (
        <div className="space-y-2">
          {rows.map((r, i) => (
            <div key={i} className="grid items-end gap-2" style={{ gridTemplateColumns: `repeat(${spec.cols.length}, minmax(0,1fr)) 28px` }}>
              {spec.cols.map(([k, label, ph]) => (
                <label key={k} className="block"><span className="text-[11px] text-slate-500">{label}</span>
                  <input className="input mt-0.5" value={r[k] ?? ""} placeholder={ph} inputMode={k === "label" || k === "lender" || k === "days" ? undefined : "decimal"}
                    onChange={(e) => set(rows.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x))} /></label>
              ))}
              <button className="mb-2 text-slate-400 hover:text-rose-600" aria-label="Remove row" onClick={() => set(rows.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
          <button className="flex items-center gap-1 text-sm font-semibold text-brand-700" onClick={() => set([...rows, { ...spec.blank }])}><Plus className="h-4 w-4" /> Add a row</button>
        </div>
      );
    }
    if (n.widget === "currency") {
      return <select className="input" value={scalars.currency || "USD"} onChange={(e) => setScalars({ ...scalars, currency: e.target.value })}>
        {CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select>;
    }
    return <input className="input" value={scalars[n.key] ?? ""} inputMode={n.widget === "text" ? undefined : "decimal"}
      placeholder={n.widget === "day" ? "e.g. 30" : n.widget === "amount" ? (n.key === "advance_received" ? "0 if none" : "e.g. 30000") : ""}
      onChange={(e) => setScalars({ ...scalars, [n.key]: e.target.value })} />;
  };

  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 grid place-items-center bg-ink-950/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-6">
          <div className="flex gap-3">
            <div className="rounded-xl bg-brand-50 p-2 text-brand-700"><ClipboardList className="h-5 w-5" /></div>
            <div>
              <h3 className="text-lg font-bold text-slate-900">A few questions before SolvOrder decides</h3>
              <p className="text-sm text-slate-500">Your documents describe the order. To know if your cash can carry it, SolvOrder also needs your business's own numbers.</p>
            </div>
          </div>
          <button className="text-slate-400 hover:text-slate-700" aria-label="Close" onClick={onClose}><X className="h-5 w-5" /></button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          {!nv && !err && <div className="py-10"><Spinner text="Gemini is reading your documents to work out what else it needs…" /></div>}
          {nv && (
            <Callout tone={nv.mode === "gemini" ? "success" : "info"} title={nv.mode === "gemini" ? "Questions chosen by Gemini" : "Standard checklist"}>
              {nv.note} Gemini only picks and words the questions; your answers go straight into the cash engine.
            </Callout>
          )}
          {nv?.needs.map((n) => (
            <div key={n.key} className="rounded-2xl border border-slate-200 p-4">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{n.question}</span>
                {n.required ? <Pill tone="red">Required</Pill> : <Pill tone="slate">Optional</Pill>}
              </div>
              <p className="mb-3 flex items-start gap-1 text-xs text-slate-500">
                {n.source === "gemini" && <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-brand-600" />}{n.why}
              </p>
              {field(n)}
            </div>
          ))}
          {err && <Callout tone="critical">{err}</Callout>}
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
          {nv?.profile_source === "default"
            ? <LoadingButton className="btn-secondary" loading={saving === "example"} loadingText="Loading example…" disabled={!!saving} onClick={useExample}>Skip: use the example business's numbers</LoadingButton>
            : <span />}
          <div className="flex items-center gap-3">
            {missingRequired.length > 0 && <span className="text-xs text-rose-700">Fill in: {missingRequired.map((n) => n.key.replace(/_/g, " ")).join(", ")}</span>}
            <LoadingButton className="btn-primary" loading={saving === "save"} loadingText="Saving…" disabled={!nv || !!saving || missingRequired.length > 0} onClick={save}>Save answers</LoadingButton>
          </div>
        </div>
      </div>
    </div>
  );
}
