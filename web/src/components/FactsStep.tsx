import { useState } from "react";
import { ArrowRight, BadgeCheck, Building2, ClipboardList, Eye, FileText, Landmark, PhoneCall, ShieldAlert, TriangleAlert } from "lucide-react";
import { post, type DocView, type Fact, type Flag } from "../api";
import { money } from "../format";
import { BusyOverlay, Callout, Card, LoadingButton, Pill, SectionTitle } from "./ui";
import { CompanyCheck } from "./CompanyCheck";

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

export function FlagCard({ flag, onResolve }: { flag: Flag; onResolve?: (code: string, action: string, note: string) => Promise<void> }) {
  const [note, setNote] = useState(flag.decision?.note ?? "");
  const [choice, setChoice] = useState(flag.decision?.action ?? "");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const tone = flag.resolved ? "success" : flag.severity;
  const opt = flag.options.find((o) => o.id === choice);
  const canSave = !!opt && (!opt.needs_note || note.trim().length >= 5);
  return (
    <Callout tone={tone} title={
      <span className="flex flex-wrap items-center gap-2">
        {flag.title}
        {flag.category === "fraud" && <Pill tone="red">Fraud check</Pill>}
        {flag.blocks_execution && !flag.resolved && <Pill tone="red">Payments blocked</Pill>}
        {flag.resolved && <Pill tone="green">Handled</Pill>}
      </span>}
      action={onResolve && flag.options.length > 0 ? (
        open ? (
          <div className="space-y-2 rounded-xl bg-white/70 p-3">
            <div className="text-xs font-semibold text-slate-600">What do you want to do? SolvOrder suggests these options; you choose.</div>
            {flag.options.map((o) => (
              <label key={o.id} className="flex cursor-pointer items-start gap-2 text-sm text-slate-800">
                <input type="radio" name={`opt-${flag.code}`} className="mt-1 accent-teal-600" checked={choice === o.id} onChange={() => setChoice(o.id)} />
                <span>{o.label}{flag.blocks_execution && !o.clears && <span className="ml-1 text-xs text-rose-700">(payments stay blocked)</span>}</span>
              </label>
            ))}
            <input className="input" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)}
              placeholder={opt?.needs_note ? "Required: how did you check? e.g. called Brightwave on our saved number" : "Optional note for the log"} />
            <div className="flex gap-2">
              <LoadingButton className={flag.blocks_execution ? "btn-danger" : "btn-primary"} loading={saving} loadingText="Recording…" disabled={!canSave}
                onClick={async () => { setSaving(true); try { await onResolve(flag.code, choice, note); setOpen(false); } finally { setSaving(false); } }}>Save my choice</LoadingButton>
              <button className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <button className="btn-secondary" onClick={() => setOpen(true)}><PhoneCall className="h-4 w-4" /> {flag.decision ? "Change my choice" : "Choose what to do"}</button>
        )) : undefined}>
      {flag.message}
      {flag.decision && <div className="mt-1 text-xs"><b>Your choice:</b> {flag.decision.label}{flag.decision.note && ` (${flag.decision.note})`}</div>}
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

const PROFILE_SOURCE: Record<string, [string, "blue" | "green" | "amber" | "slate"]> = {
  sample: ["Sample business", "slate"], owner: ["Your numbers", "green"],
  example: ["Example numbers", "amber"], default: ["Not given yet", "amber"],
};

const ROLE_SOURCE: Record<string, string> = {
  profile: "from your company profile", documents: "read from the documents", owner: "you chose it for this deal",
  sample: "this sample's business", default: "SolvOrder's default",
};

/** Which side of the deal the owner is on, why SolvOrder thinks so, and a one-click switch. */
function RoleBanner({ view, setView, onOpenNeeds }: { view: DocView; setView: (v: DocView) => void; onOpenNeeds: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const other = view.role === "seller" ? "buyer" : "seller";
  const g = view.role_guess;
  const conflict = !!g.role && g.role !== view.role;
  async function flip() {
    setBusy(true); setErr(null);
    try { const v = await post<DocView>("/api/role", { role: other }); setView(v); if (v.questions > 0) onOpenNeeds(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <Callout tone={conflict ? "warning" : "info"}
      title={<>In this deal you are the <b>{view.role === "seller" ? "seller" : "buyer"}</b> <span className="font-normal text-slate-500">({ROLE_SOURCE[view.role_source]})</span></>}
      action={view.role_source !== "sample" ? <LoadingButton className="btn-secondary" loading={busy} loadingText="Switching…" onClick={flip}>I am the {other} here</LoadingButton> : undefined}>
      {view.role === "seller"
        ? "A customer ordered from you. SolvOrder weighs their payment against what you pay your supplier, and after approval notifies your customer."
        : "A supplier offered you goods. SolvOrder weighs what you pay them against the income you expect from the goods, and after approval notifies your supplier."}
      {g.evidence && <div className="mt-1 text-xs">{conflict ? "Check this: " : ""}{g.evidence}</div>}
      {err && <div className="mt-1 text-xs text-rose-700">{err}</div>}
    </Callout>
  );
}

export function FactsStep({ view, setView, state, setState, onNext, analysing, onOpenNeeds }: {
  view: DocView; setView: (v: DocView) => void; state: FactState; setState: (s: FactState) => void;
  onNext: () => void; analysing: boolean; onOpenNeeds: () => void;
}) {
  const [showDocs, setShowDocs] = useState(false);
  const cur = view.profile?.currency ?? "USD";
  const flags = [...view.flags].sort((a, b) => ({ critical: 0, warning: 1, info: 2 }[a.severity] - { critical: 0, warning: 1, info: 2 }[b.severity]));
  const openBlocks = flags.filter((f) => f.blocks_execution && !f.resolved);
  const pays = state.payEdits ?? view.supplier_payments.map((p) => ({ label: p.label, amount: p.amount.value, day: p.day.value, paid: p.paid }));

  async function resolve(code: string, action: string, note: string) {
    setView(await post<DocView>("/api/flags/resolve", { code, action, note }));
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

      <RoleBanner view={view} setView={setView} onOpenNeeds={onOpenNeeds} />

      {view.profile_source === "default" && (
        <Callout tone="warning" title="SolvOrder still needs your business's numbers"
          action={<button className="btn-primary" onClick={onOpenNeeds}><ClipboardList className="h-4 w-4" /> Answer SolvOrder's questions</button>}>
          Your documents describe the order, not your cash, payroll or bills. Gemini has a short list of questions for you.
        </Callout>
      )}

      {flags.length > 0 && (
        <Card className="p-6">
          <SectionTitle icon={<ShieldAlert className="h-5 w-5" />} title="Fraud & document checks"
            sub={openBlocks.length ? "Critical issues block every payment until you choose a safe way to handle them." : "Checks run on every document. Choose how to handle each one."} />
          <div className="space-y-3">{flags.map((f, i) => <FlagCard key={f.code + i} flag={f} onResolve={resolve} />)}</div>
        </Card>
      )}
      {flags.length === 0 && view.documents.length > 0 && (
        <Callout tone="success" title="No fraud or consistency problems found">Bank details, payees, amounts and terms are consistent across the documents, and no hidden instructions were found.</Callout>
      )}

      <CompanyCheck buyer={view.role === "buyer"} refreshKey={view.facts.filter((f) => /customer_|supplier_/.test(f.key)).map((f) => f.value).join("|") + view.documents.map((d) => d.doc_id).join()} />

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
            sub="Cash today, your safety reserve and existing payments. SolvOrder adds the order on top of these."
            right={<div className="flex shrink-0 items-center gap-2"><Pill tone={PROFILE_SOURCE[view.profile_source][1]}>{PROFILE_SOURCE[view.profile_source][0]}</Pill>
              <button className="btn-secondary" onClick={onOpenNeeds}><ClipboardList className="h-4 w-4" /> {view.profile_source === "owner" ? "Edit my numbers" : "Ask me what you need"}</button></div>} />
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
