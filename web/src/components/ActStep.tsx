import { useEffect, useState } from "react";
import { Ban, BellRing, CheckCircle2, FileSignature, Landmark, ListTree, Mail, Send, ShieldCheck, Sparkles, X, XCircle } from "lucide-react";
import { get, post, type Analysis, type Approval, type ApprovedRecord, type Execution, type LogEntry } from "../api";
import { BreakdownModal } from "./Breakdown";
import type { Choice } from "./OptionsStep";
import { OperationLog, SandboxPanel, type SandboxTab } from "./Sandbox";
import { money, planTitle } from "../format";
import { BusyOverlay, Callout, Card, LoadingButton, Pill, SectionTitle, Updating } from "./ui";


/** "Notify my customer" (seller) / "Notify my supplier" (buyer): the deal's counterparty. */
function notifyLabel(a: Analysis, drafts: { party?: string; to_name: string }[] | null) {
  const first = drafts?.[0];
  const who = a.case.role === "buyer" ? "supplier" : "customer";
  const others = (drafts ?? []).slice(1).map((d) => d.party === "lender" ? "lender" : d.party ?? "").filter(Boolean);
  return `Notify my ${who}${first ? ` (${first.to_name})` : ""}${others.length ? ` + ${others.join(" + ")}` : ""}`;
}

function NotifyModal({ a, drafts, busy, onSend, onClose }: {
  a: Analysis; drafts: { to: string; to_name: string; subject: string; body: string; source: string }[];
  busy: boolean; onSend: () => void; onClose: () => void;
}) {
  const who = a.case.role === "buyer" ? "supplier" : "customer";
  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 grid place-items-center bg-ink-950/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-6">
          <div className="flex gap-3">
            <div className="rounded-xl bg-brand-50 p-2 text-brand-700"><BellRing className="h-5 w-5" /></div>
            <div>
              <h3 className="text-lg font-bold text-slate-900">Notify your {who} by mail?</h3>
              <p className="text-sm text-slate-500">SolvOrder wrote {drafts.length === 1 ? "this email" : `these ${drafts.length} emails`} from the plan you approved. Sending also books the plan in the sandbox bank and files it under Approved plans.</p>
            </div>
          </div>
          <button className="text-slate-400 hover:text-slate-700" aria-label="Close" onClick={onClose}><X className="h-5 w-5" /></button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-6">
          {drafts.map((d, i) => (
            <div key={i} className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">To: <b className="text-slate-700">{d.to_name}</b> &lt;{d.to}&gt;{d.source === "gemini" && " · Gemini-polished, numbers verified"}</div>
              <div className="px-3 pt-2 text-sm font-semibold text-slate-800">{d.subject}</div>
              <pre className="whitespace-pre-wrap p-3 font-sans text-sm text-slate-700">{d.body.split("\n").slice(2).join("\n")}</pre>
            </div>
          ))}
          <Callout tone="info">Demo: the email goes to SolvOrder's outbox and is not really delivered. No real email or payment leaves SolvOrder.</Callout>
        </div>
        <div className="flex justify-end gap-3 border-t border-slate-100 p-4">
          <button className="btn-secondary" disabled={busy} onClick={onClose}>Not now</button>
          <LoadingButton className="btn-primary" loading={busy} loadingText="Sending…" onClick={onSend}><Send className="h-4 w-4" /> Send {drafts.length === 1 ? "the email" : `${drafts.length} emails`}</LoadingButton>
        </div>
      </div>
    </div>
  );
}

export function ActStep({ a, refresh, choice, onSent, onOpenApproved }: {
  a: Analysis; refresh: () => Promise<void>; choice: Choice;
  onSent: (text: string) => void; onOpenApproved: () => void;
}) {
  const cur = a.case.currency;
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [record, setRecord] = useState<ApprovedRecord | null>(null);
  const [bd, setBd] = useState(false);
  const [approval, setApproval] = useState<Approval | null>(a.approval);
  const [exec, setExec] = useState<Execution | null>(a.executed);
  const [err, setErr] = useState<string | null>(null);
  type Draft = { body: string; to: string; to_name: string; subject: string; source: string; note?: string; party?: string };
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const feasibleIds = a.plans.filter((p) => p.feasible && p.id !== "decline").map((p) => p.id);
  const [planId, setPlanId] = useState(choice && !choice.override && feasibleIds.includes(choice.id) ? choice.id
    : feasibleIds.includes(a.verdict.winner) ? a.verdict.winner : feasibleIds[0] ?? "");
  const [ovr, setOvr] = useState({ open: !!choice?.override, plan: choice?.override ? choice.id : "", reason: "", ack: false });
  const [draftLoading, setDraftLoading] = useState(false);
  // The message always matches the plan about to be approved (the override plan
  // while the override panel is open).
  const overridable0 = a.plans.find((p) => !p.reserve_ok && p.violations.length === 0 && p.id !== "decline")?.id ?? "";
  const draftPlan = ovr.open ? (ovr.plan || overridable0) : planId;
  useEffect(() => {
    if (!draftPlan) return;
    setDraftLoading(true);
    post<{ messages: Draft[] }>("/api/draft", { plan_id: draftPlan })
      .then((d) => setDrafts(d.messages.map((m) => ({ ...m, source: "engine" })))).catch((e) => setErr((e as Error).message))
      .finally(() => setDraftLoading(false));
  }, [draftPlan]);
  const [t3, setT3] = useState<string | null>(null);
  const [t3Busy, setT3Busy] = useState<string | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [sbTab, setSbTab] = useState<SandboxTab>("outbox");
  const [sbVersion, setSbVersion] = useState(0);
  const openSandbox = (t: SandboxTab) => { setSbTab(t); document.getElementById("sandbox-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  const feasible = a.plans.filter((p) => p.feasible && p.id !== "decline");
  const overridable = a.plans.filter((p) => !p.reserve_ok && p.violations.length === 0 && p.id !== "decline");
  const ovrPlan = a.plans.find((p) => p.id === (ovr.plan || overridable[0]?.id));
  const loadLog = async () => {
    setLogLoading(true);
    try { setLog((await get<{ entries: LogEntry[] }>(`/api/log?session_id=${encodeURIComponent(sessionStorage.getItem("solvorder.sid") ?? "")}`)).entries); }
    finally { setLogLoading(false); }
  };
  useEffect(() => { loadLog().catch(() => undefined); setSbVersion((n) => n + 1); }, [approval, exec, t3]);

  async function act<T>(label: string, fn: () => Promise<T>, then: (r: T) => void) {
    setBusy(label); setErr(null);
    try { then(await fn()); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  }
  const blocked = a.verdict.execution_blocks.length > 0;

  return (
    <div className="space-y-6">
      <BusyOverlay show={busy === "notify"} title="Notifying and booking the approved plan"
        steps={["Sending the emails to the demo outbox", "Checking your approval and the fraud gate", "Booking payments in the simulated bank", "Filing the plan under Approved plans"]} />
      {notifyOpen && drafts && <NotifyModal a={a} drafts={drafts} busy={busy === "notify"} onClose={() => setNotifyOpen(false)}
        onSend={() => act("notify", () => post<{ approval: Approval; executed: Execution; record: ApprovedRecord }>("/api/notify", { polished: !!drafts?.some((d) => d.source === "gemini") }),
          async (r) => {
            setApproval(r.approval); setExec(r.executed); setRecord(r.record); setNotifyOpen(false);
            const sent = r.approval.messages.filter((m) => m.sent).map((m) => m.to_name);
            onSent(sent.length ? `Email sent to ${sent.join(", ")} (demo outbox). Saved under Approved plans.` : "No email could be sent: see the approval card.");
            await refresh();
          })} />}
      {bd && <BreakdownModal planId={draftPlan} title={planTitle(a.plans.find((p) => p.id === draftPlan)!, cur)} cur={cur} onClose={() => setBd(false)} />}
      {a.verdict.provisional && <Callout tone="warning" title="Confirm the provisional facts first">Approval is locked while a value that changes the result is unconfirmed. Use the Confirm buttons on the risk screen.</Callout>}
      {blocked && <Callout tone="critical" title="A fraud check is still open">{a.verdict.execution_blocks.join("; ")}. You can approve, but every payment step will be refused until you record the check on the facts screen.</Callout>}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-6">
          <SectionTitle icon={<Mail className="h-5 w-5" />} title="Message for this plan" sub="Drafted from the engine's numbers for the plan you selected. Gemini may reword it, never change a figure. After you approve, the Notify button sends it." />
          <Updating active={draftLoading}>
            {!drafts && <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">Loading the message…</div>}
            <div className="space-y-3">
              {drafts?.map((d, i) => (
                <div key={i} className="rounded-xl border border-slate-200">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                    <span>To: <b className="text-slate-700">{d.to_name}</b> &lt;{d.to}&gt;</span>
                    {d.source === "gemini" && <Pill tone="green">Gemini-polished · numbers verified</Pill>}
                  </div>
                  <pre className="whitespace-pre-wrap p-3 font-sans text-sm text-slate-800">{d.body}</pre>
                  {d.note && d.source !== "gemini" && <div className="px-3 pb-2 text-xs text-amber-700">{d.note}</div>}
                </div>
              ))}
            </div>
          </Updating>
          {drafts && drafts.length > 1 && <p className="mt-2 text-xs text-slate-500">This plan needs {drafts.length} parties to agree, so {drafts.length} messages go out.</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <LoadingButton className="btn-secondary" loading={busy === "polish"} loadingText="Gemini is polishing…" disabled={!!busy || !drafts}
              onClick={() => act("polish", () => Promise.all((drafts ?? []).map((_, i) =>
                post<{ text: string; source: string; note: string }>("/api/ai/polish", { plan_id: draftPlan, index: i }))),
                (rs) => setDrafts((drafts ?? []).map((d, i) => ({ ...d, body: rs[i].text, source: rs[i].source, note: rs[i].note }))))}>
              <Sparkles className="h-4 w-4" /> Polish with Gemini
            </LoadingButton>
          </div>
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<FileSignature className="h-5 w-5" />} title="Approve a plan" sub="Pick any safe plan: the recommended one is starred, but the choice is yours. After approving, notify the other side by mail." />
          <label className="label">Plan</label>
          <select className="input mt-1" value={planId} onChange={(e) => setPlanId(e.target.value)}>
            {feasible.map((p) => <option key={p.id} value={p.id}>{p.recommended ? "★ " : ""}{planTitle(p, cur)}</option>)}
          </select>
          <button className="mt-2 flex items-center gap-1 text-sm font-semibold text-brand-700" disabled={!draftPlan} onClick={() => setBd(true)}><ListTree className="h-4 w-4" /> See the money breakdown for this plan</button>
          <LoadingButton className="btn-primary mt-3 w-full" loading={busy === "approve"} loadingText="Recording your approval…"
            disabled={!!busy || a.verdict.provisional || !feasible.length}
            onClick={() => act("approve", () => post<{ approval: Approval }>("/api/approve", { plan_id: planId, polished: !!drafts?.some((d) => d.source === "gemini") }), (r) => { setApproval(r.approval); setExec(null); })}>
            <CheckCircle2 className="h-4 w-4" /> Approve this plan
          </LoadingButton>

          <div className="mt-4 border-t border-slate-100 pt-4">
            {!ovr.open ? (
              <button className="text-sm font-semibold text-rose-700 disabled:opacity-40" disabled={!overridable.length || a.verdict.provisional} onClick={() => setOvr({ ...ovr, open: true })}>
                Approve a plan that breaks the reserve (explicit override)…
              </button>
            ) : (
              <div className="space-y-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm">
                <select className="input" value={ovr.plan || overridable[0]?.id} onChange={(e) => setOvr({ ...ovr, plan: e.target.value })}>
                  {overridable.map((p) => <option key={p.id} value={p.id}>{planTitle(p, cur)} (low {money(p.min_balance, cur)}, day {p.min_day})</option>)}
                </select>
                <input className="input" placeholder="Reason (recorded in the log)" value={ovr.reason} maxLength={300} onChange={(e) => setOvr({ ...ovr, reason: e.target.value })} />
                {ovrPlan && <label className="flex items-start gap-2 text-rose-900"><input type="checkbox" className="mt-1 accent-rose-600" checked={ovr.ack} onChange={(e) => setOvr({ ...ovr, ack: e.target.checked })} />
                  I understand cash falls to {money(ovrPlan.min_balance, cur)} on day {ovrPlan.min_day}, below my {money(a.case.reserve, cur)} reserve.</label>}
                <LoadingButton className="btn-danger w-full" loading={busy === "override"} loadingText="Recording override…"
                  disabled={!ovr.ack || ovr.reason.trim().length < 5 || !!busy}
                  onClick={() => act("override", () => post<{ approval: Approval }>("/api/approve", { plan_id: ovr.plan || overridable[0].id, override: true, reason: ovr.reason, polished: !!drafts?.some((d) => d.source === "gemini") }), (r) => { setApproval(r.approval); setExec(null); })}>
                  Approve with reserve override
                </LoadingButton>
                <button className="w-full text-xs font-semibold text-slate-500 hover:text-slate-800" onClick={() => setOvr({ open: false, plan: "", reason: "", ack: false })}>Cancel the override</button>
              </div>
            )}
          </div>

          {approval && (
            <div className={`mt-4 rounded-xl p-4 ${approval.override ? "bg-rose-50 text-rose-900" : "bg-emerald-50 text-emerald-900"}`}>
              <div className="text-sm font-semibold">Approved <code className="rounded bg-white/70 px-1">{approval.id}</code></div>
              <div className="text-sm">{approval.label}</div>
              <div className="text-xs opacity-70">plan version {approval.version}{approval.reason && ` · reason: ${approval.reason}`}</div>
              {approval.messages.map((m, i) => (
                <div key={i} className={`mt-3 rounded-lg border p-3 text-sm ${m.sent ? "border-emerald-200 bg-white" : "border-rose-200 bg-white"}`}>
                  <div className="flex flex-wrap items-center gap-2 font-semibold"><Send className="h-4 w-4" />
                    {m.sent ? `Email sent to ${m.to_name}` : `Email to ${m.to_name} not sent`}
                    <Pill tone="violet">DEMO OUTBOX</Pill></div>
                  <div className="text-xs text-slate-500">{m.to} · {m.status}{m.source === "gemini" ? " · Gemini-polished, numbers verified" : ""}</div>
                  <div className="mt-1 text-xs font-medium text-slate-700">{m.subject}</div>
                </div>
              ))}
              {!approval.notified ? (
                <LoadingButton className="btn-primary mt-3 w-full" loading={busy === "notify"} loadingText="Sending…" disabled={!!busy || !drafts}
                  onClick={() => setNotifyOpen(true)}>
                  <BellRing className="h-4 w-4" /> {notifyLabel(a, drafts)}
                </LoadingButton>
              ) : (
                <button className="btn-secondary mt-3 w-full" onClick={onOpenApproved}>Open Approved plans{record ? ` (${record.id})` : ""}</button>
              )}
            </div>
          )}
          {err && <div className="mt-3"><Callout tone="critical">{err}</Callout></div>}
        </Card>
      </div>

      {exec && (
        <Card className="p-6">
          <SectionTitle icon={exec.ok ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />} title={`Execution report${exec.override ? " · [RESERVE OVERRIDE]" : ""}`}
            sub="Simulated bank, mock outbox and mock lender portal. Nothing real is sent or paid." />
          <ol className="space-y-2">
            {exec.steps.map((s, i) => (
              <li key={i} className="flex gap-2 text-sm">{exec.ok || i < exec.steps.length - 1 ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <Ban className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />}{s}</li>
            ))}
          </ol>
          {exec.consistency && <div className="mt-3"><Pill tone={exec.consistency === "passed" ? "green" : "red"}>Ledger matches the engine's prediction: {exec.consistency}</Pill></div>}
          {exec.ledger.length > 0 && (
            <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold"><Landmark className="mr-1 inline h-4 w-4" />Simulated bank ledger ({exec.ledger.length} movements)</summary>
              <table className="mt-2 w-full text-sm"><tbody>{exec.ledger.map((m, i) => <tr key={i} className="border-t border-slate-100"><td className="py-1 text-slate-500">day {m.day}</td><td>{m.label}</td><td className="text-right">{money(Number(m.amount), cur, { sign: true })}</td></tr>)}</tbody></table>
            </details>
          )}
        </Card>
      )}

      <SandboxPanel version={sbVersion} tab={sbTab} setTab={setSbTab} cur={cur} />

      <div className="grid gap-6 xl:grid-cols-[1fr_2fr]">
        <Card className="p-6">
          <SectionTitle icon={<ShieldCheck className="h-5 w-5" />} title="Try to make it misbehave" sub="These T3 actions have no code path. Every attempt is blocked and logged." />
          <div className="grid gap-2">
            {[["real_email", "Send a real email"], ["live_transfer", "Make a live bank transfer"], ["invent_terms", "Invent better loan terms"], ["edit_document", "Edit a source document"]].map(([k, l]) => (
              <LoadingButton key={k} className="btn-secondary justify-start" loading={t3Busy === k} loadingText="Trying…" disabled={!!t3Busy}
                onClick={() => { setT3Busy(k); post<{ reason: string }>("/api/t3", { action: k }).then((r) => setT3(r.reason)).finally(() => setT3Busy(null)); }}>
                <Ban className="h-4 w-4 text-rose-600" />{l}
              </LoadingButton>
            ))}
          </div>
          {t3 && <div className="mt-3"><Callout tone="critical" title="Blocked">{t3}</Callout></div>}
        </Card>
        <OperationLog log={log} loading={logLoading} onOpenSandbox={openSandbox} />
      </div>
    </div>
  );
}
