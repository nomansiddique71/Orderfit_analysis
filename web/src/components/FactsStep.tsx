import { useState } from "react";
import { ArrowRight, BadgeCheck, Building2, Eye, FileText, Landmark, PhoneCall, ShieldAlert, TriangleAlert } from "lucide-react";
import { post, type DocView, type Fact, type Flag } from "../api";
import { money } from "../format";
import { BusyOverlay, Callout, Card, LoadingButton, Pill, SectionTitle } from "./ui";

export interface FactState {
  edits: Record<string, string>;
  payEdits: { label: string; amount: string; day: string; paid: boolean }[] | null;
  confirmed: Set<string>;
  reserve: number | null;
  openingCash: number | null;
  maxFin: number | null;
}

const MODE_TEXT: Record<string, string> = {
  gemini: "Read by Google Gemini. Every quoted span was checked against the document text.",
  "gemini-pdf": "Read by Google Gemini, including scanned PDFs (those values need your confirmation).",
  parser: "Read by the built-in parser (Gemini unavailable). Please check every value.",
  manual: "Entered by you. No AI was used.",
};

// Shown even when the documents don't mention them, so the owner can fill them in.
const ALWAYS_SHOWN = new Set(["advance_received"]);
const PLACEHOLDER: Record<string, string> = { advance_received: "0 if the customer has not paid anything yet" };

export function payKey(i: number, label: string, amount: string, day: string) {
  return `Supplier payment ${i + 1}: ${label}=${amount} on ${day}`;
}

export function FlagCard({ flag, onResolve }: { flag: Flag; onResolve?: (code: string, note: string) => Promise<void> }) {
  const [note, setNote] = useState("");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const tone = flag.resolved ? "success" : flag.severity;
  return (
    <Callout tone={tone} title={
      <span className="flex flex-wrap items-center gap-2">
        {flag.title}
        {flag.category === "fraud" && <Pill tone="red">Fraud check</Pill>}
        {flag.blocks_execution && !flag.resolved && <Pill tone="red">Payments blocked</Pill>}
        {flag.resolved && <Pill tone="green">Resolved</Pill>}
      </span>}
      action={flag.blocks_execution && !flag.resolved && onResolve ? (
        open ? (
          <div className="flex flex-col gap-2 sm:flex-row">
            <input className="input" value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Called Brightwave on our saved number; they confirmed no change" />
            <LoadingButton className="btn-danger shrink-0" loading={saving} loadingText="Recording…" disabled={note.trim().length < 5}
              onClick={async () => { setSaving(true); try { await onResolve(flag.code, note); } finally { setSaving(false); } }}>Record check</LoadingButton>
          </div>
        ) : (
          <button className="btn-secondary" onClick={() => setOpen(true)}><PhoneCall className="h-4 w-4" /> I verified this with the supplier</button>
        )) : undefined}>
      {flag.message}
      {flag.resolved && <div className="mt-1 text-xs">Owner note: {flag.resolution_note}</div>}
    </Callout>
  );
}

function SourceQuote({ f, docs }: { f: Fact; docs: DocView["documents"] }) {
  if (!f.span) return null;
  const doc = docs.find((d) => d.doc_id === f.source);
  return (
    <div className="mt-1 text-xs text-slate-500">
      <span className="font-semibold text-slate-600">{doc ? doc.filename : f.source}</span>: “{f.span}”
    </div>
  );
}

function Status({ f }: { f: Fact }) {
  if (f.source === "OWNER") return <Pill tone="blue">Entered by you</Pill>;
  if (!f.value) return <Pill tone="slate">Not in the documents</Pill>;
  if (f.verified && f.confidence >= 0.7) return <Pill tone="green"><BadgeCheck className="h-3 w-3" /> Verified · {Math.round(f.confidence * 100)}%</Pill>;
  return <Pill tone="amber"><TriangleAlert className="h-3 w-3" /> Needs your check · {Math.round(f.confidence * 100)}%</Pill>;
}

export function FactsStep({ view, setView, state, setState, onNext, analysing }: {
  view: DocView; setView: (v: DocView) => void; state: FactState; setState: (s: FactState) => void;
  onNext: () => void; analysing: boolean;
}) {
  const [showDocs, setShowDocs] = useState(false);
  const cur = view.profile?.currency ?? "USD";
  const flags = [...view.flags].sort((a, b) => ({ critical: 0, warning: 1, info: 2 }[a.severity] - { critical: 0, warning: 1, info: 2 }[b.severity]));
  const openBlocks = flags.filter((f) => f.blocks_execution && !f.resolved);
  const pays = state.payEdits ?? view.supplier_payments.map((p) => ({ label: p.label, amount: p.amount.value, day: p.day.value, paid: p.paid }));

  async function resolve(code: string, note: string) {
    setView(await post<DocView>("/api/flags/resolve", { code, note }));
  }
  const toggle = (key: string) => {
    const c = new Set(state.confirmed);
    if (c.has(key)) c.delete(key); else c.add(key);
    setState({ ...state, confirmed: c });
  };

  return (
    <div className="space-y-6">
      <BusyOverlay show={analysing} title="Analysing your cash"
        steps={["Rebuilding your cash day by day", "Simulating every option", "Stress-testing late payment", "Ranking the safe plans"]} />
      <Callout tone={view.mode.startsWith("gemini") ? "success" : "info"} title={view.mode.startsWith("gemini") ? "Documents read by Gemini" : "Documents read without AI"}>
        {MODE_TEXT[view.mode] ?? view.note}
        {/scanned|could not read/i.test(view.note) && <div className="mt-1 text-xs opacity-80">{view.note}</div>}
      </Callout>

      {flags.length > 0 && (
        <Card className="p-6">
          <SectionTitle icon={<ShieldAlert className="h-5 w-5" />} title="Fraud & document checks"
            sub={openBlocks.length ? "Critical issues block every payment until you record how you checked them." : "Checks run on every document. Review anything below."} />
          <div className="space-y-3">{flags.map((f, i) => <FlagCard key={f.code + i} flag={f} onResolve={resolve} />)}</div>
        </Card>
      )}
      {flags.length === 0 && view.documents.length > 0 && (
        <Callout tone="success" title="No fraud or consistency problems found">Bank details, payees, amounts and terms are consistent across the documents, and no hidden instructions were found.</Callout>
      )}

      <Card className="p-6">
        <SectionTitle icon={<FileText className="h-5 w-5" />} title="What SolvOrder read from your documents"
          sub="Edit any value that is wrong. Values marked 'Needs your check' change the result, so confirm them."
          right={view.documents.length > 0 && <button className="btn-secondary" onClick={() => setShowDocs(!showDocs)}><Eye className="h-4 w-4" /> {showDocs ? "Hide" : "Show"} documents</button>} />
        <div className="divide-y divide-slate-100">
          {view.facts.filter((f) => f.value || state.edits[f.key] !== undefined || ALWAYS_SHOWN.has(f.key)).map((f) => {
            const value = state.edits[f.key] ?? f.value;
            const key = `${f.label}=${f.value}`;
            const edited = state.edits[f.key] !== undefined && state.edits[f.key] !== f.value;
            return (
              <div key={f.key} className="grid gap-3 py-3 md:grid-cols-[220px_1fr_auto] md:items-start">
                <div>
                  <div className="text-sm font-semibold text-slate-800">{f.label}</div>
                  {f.simulation && <div className="text-[11px] text-slate-400">changes the cash result</div>}
                </div>
                <div>
                  <input className="input" value={value} placeholder={PLACEHOLDER[f.key]} onChange={(e) => setState({ ...state, edits: { ...state.edits, [f.key]: e.target.value } })} />
                  <SourceQuote f={f} docs={view.documents} />
                  {f.note && <div className="mt-1 text-xs text-amber-700">{f.note}</div>}
                </div>
                <div className="flex flex-col items-end gap-2">
                  {edited ? <Pill tone="blue">Edited by you</Pill> : <Status f={f} />}
                  {f.needs_review && !edited && (
                    <label className="flex cursor-pointer items-center gap-2 text-xs font-semibold text-slate-700">
                      <input type="checkbox" checked={state.confirmed.has(key)} onChange={() => toggle(key)} className="h-4 w-4 accent-teal-600" />
                      I confirm this value
                    </label>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-6">
          <div className="label mb-2">What you pay the supplier (and shipping)</div>
          <div className="overflow-hidden rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-3 py-2">Payment</th><th className="px-3 py-2">Amount</th><th className="px-3 py-2">Due</th><th className="px-3 py-2" title="Paid before today: already out of your cash, so it is not a future payment">Already paid?</th><th className="px-3 py-2">Source</th><th /></tr></thead>
              <tbody>
                {pays.map((p, i) => {
                  const orig = view.supplier_payments[i];
                  const key = orig ? payKey(i, orig.label, orig.amount.value, orig.day.value) : "";
                  const needs = orig && (!orig.amount.verified || !orig.day.verified || orig.amount.confidence < 0.7) && orig.amount.source !== "OWNER";
                  const set = (patch: Partial<typeof p>) => setState({ ...state, payEdits: pays.map((x, j) => j === i ? { ...x, ...patch } : x) });
                  return (
                    <tr key={i} className="border-t border-slate-100 align-top">
                      <td className="px-3 py-2"><input className="input" value={p.label} onChange={(e) => set({ label: e.target.value })} /></td>
                      <td className="px-3 py-2"><input className="input" value={p.amount} onChange={(e) => set({ amount: e.target.value })} /></td>
                      <td className="px-3 py-2"><input className="input" value={p.day} disabled={p.paid} onChange={(e) => set({ day: e.target.value })} /></td>
                      <td className="px-3 py-2 text-center"><input type="checkbox" className="h-4 w-4 accent-teal-600" checked={p.paid} onChange={(e) => set({ paid: e.target.checked })} /></td>
                      <td className="px-3 py-2 text-xs text-slate-500">{orig?.amount.span ? `“${orig.amount.span}”` : "you"}{orig?.amount.note && <div className="text-amber-700">{orig.amount.note}</div>}</td>
                      <td className="px-3 py-2">{needs && state.payEdits === null && (
                        <label className="flex items-center gap-1 text-xs"><input type="checkbox" className="accent-teal-600" checked={state.confirmed.has(key)} onChange={() => toggle(key)} />confirm</label>)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <button className="mt-2 text-sm font-semibold text-brand-700" onClick={() => setState({ ...state, payEdits: [...pays, { label: "Payment", amount: "", day: "day 0", paid: false }] })}>+ Add payment</button>
        </div>

        {view.bank_details.length > 0 && (
          <div className="mt-6">
            <div className="label mb-2 flex items-center gap-1"><Landmark className="h-3.5 w-3.5" /> Bank details found</div>
            <div className="grid gap-2 md:grid-cols-2">
              {view.bank_details.map((b, i) => (
                <div key={i} className="rounded-xl border border-slate-200 p-3 text-sm">
                  <div className="font-semibold">{b.payee || "Payee not stated"}</div>
                  <div className="text-slate-600">{b.bank} · <span className="font-mono">{b.account}</span></div>
                  <div className="text-xs text-slate-400">{view.documents.find((d) => d.doc_id === b.source)?.filename ?? b.source}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {showDocs && (
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {view.documents.map((d) => (
              <div key={d.doc_id} className="rounded-xl border border-slate-200">
                <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs">
                  <span className="font-semibold">{d.doc_id} · {d.filename}</span><Pill tone="slate">{d.kind.replace("_", " ")}</Pill>
                </div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap p-3 font-mono text-[11px] text-slate-700">{d.scanned ? "[Scanned PDF: no text layer]" : d.text}</pre>
              </div>
            ))}
          </div>
        )}
      </Card>

      {view.profile && (
        <Card className="p-6">
          <SectionTitle icon={<Building2 className="h-5 w-5" />} title={`Your business: ${view.profile.name}`}
            sub="Cash today, your safety reserve and existing payments. SolvOrder adds the order on top of these." />
          <div className="grid gap-4 md:grid-cols-3">
            {([["openingCash", "Cash in the bank today", view.profile.opening_cash], ["reserve", "Minimum cash reserve (never go below)", view.profile.reserve],
              ["maxFin", "Most you'd pay for financing", view.profile.max_financing_cost]] as const).map(([k, label, def]) => (
              <label key={k} className="block"><span className="label">{label}</span>
                <input type="number" className="input mt-1" value={state[k] ?? Number(def)}
                  onChange={(e) => setState({ ...state, [k]: e.target.value === "" ? null : Number(e.target.value) })} />
                <span className="text-xs text-slate-400">{cur}</span></label>
            ))}
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <div className="label mb-1">Existing payments and receipts</div>
              <ul className="space-y-1 text-sm">
                {view.profile.obligations.map((o, i) => (
                  <li key={i} className="flex justify-between rounded-lg bg-slate-50 px-3 py-1.5">
                    <span>Day {o.day} · {o.label}</span>
                    <span className={Number(o.amount) < 0 ? "text-rose-700" : "text-emerald-700"}>{money(Number(o.amount), cur, { sign: true })}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <div className="label mb-1">Financing offers on file (terms cannot be changed by the AI)</div>
              <ul className="space-y-1 text-sm">
                {view.profile.offers.map((o) => (
                  <li key={o.id} className="rounded-lg bg-slate-50 px-3 py-1.5">
                    <span className="font-semibold">{o.lender}</span> · {money(Number(o.principal), cur)} · {o.terms} · day {o.draw_day}→{o.repay_day}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>
      )}

      <div className="flex justify-end">
        <LoadingButton className="btn-primary px-6 py-3 text-base" loading={analysing} loadingText="Analysing your cash…" onClick={onNext}>Analyse my cash <ArrowRight className="h-5 w-5" /></LoadingButton>
      </div>
    </div>
  );
}
