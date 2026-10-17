import { useEffect, useState } from "react";
import { Ban, CheckCircle2, Download, FileSignature, Landmark, Mail, Play, ScrollText, ShieldCheck, Sparkles, XCircle } from "lucide-react";
import { get, logUrl, post, type Analysis, type Approval, type Execution, type LogEntry } from "../api";
import { money, planTitle } from "../format";
import { BusyOverlay, Callout, Card, LoadingButton, Pill, SectionTitle } from "./ui";

const TIER: Record<string, string> = { T0: "bg-slate-200 text-slate-700", T1: "bg-sky-100 text-sky-800", T2: "bg-emerald-100 text-emerald-800", T3: "bg-rose-100 text-rose-800" };

export function ActStep({ a, refresh }: { a: Analysis; refresh: () => Promise<void> }) {
  const cur = a.case.currency;
  const [approval, setApproval] = useState<Approval | null>(a.approval);
  const [exec, setExec] = useState<Execution | null>(a.executed);
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ text: string; source: string; note?: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [planId, setPlanId] = useState(a.verdict.winner);
  const [ovr, setOvr] = useState({ open: false, plan: "", reason: "", ack: false });
  const [t3, setT3] = useState<string | null>(null);
  const [t3Busy, setT3Busy] = useState<string | null>(null);
  const [logLoading, setLogLoading] = useState(false);

  const feasible = a.plans.filter((p) => p.feasible && p.id !== "decline");
  const overridable = a.plans.filter((p) => !p.reserve_ok && p.violations.length === 0 && p.id !== "decline");
  const ovrPlan = a.plans.find((p) => p.id === (ovr.plan || overridable[0]?.id));
  const loadLog = async () => {
    setLogLoading(true);
    try { setLog((await get<{ entries: LogEntry[] }>(`/api/log?session_id=${encodeURIComponent(sessionStorage.getItem("solvorder.sid") ?? "")}`)).entries); }
    finally { setLogLoading(false); }
  };
  useEffect(() => { loadLog().catch(() => undefined); }, [approval, exec, t3]);

  async function act<T>(label: string, fn: () => Promise<T>, then: (r: T) => void) {
    setBusy(label); setErr(null);
    try { then(await fn()); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  }
  const blocked = a.verdict.execution_blocks.length > 0;

  return (
    <div className="space-y-6">
      <BusyOverlay show={busy === "execute"} title="Executing the approved plan"
        steps={["Checking your approval and the fraud gate", "Sending the message to the mock outbox", "Booking payments in the simulated bank", "Comparing the ledger with the engine"]} />
      {a.verdict.provisional && <Callout tone="warning" title="Confirm the provisional facts first">Approval is locked while a value that changes the result is unconfirmed. Use the Confirm buttons on the risk screen.</Callout>}
      {blocked && <Callout tone="critical" title="A fraud check is still open">{a.verdict.execution_blocks.join("; ")}. You can approve, but every payment step will be refused until you record the check on the facts screen.</Callout>}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-6">
          <SectionTitle icon={<Mail className="h-5 w-5" />} title="Message to send" sub="Drafted from the engine's numbers. Gemini may reword it, never change a figure." />
          <pre className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4 font-sans text-sm text-slate-800">{draft?.source === "gemini" ? draft.text : a.draft}</pre>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <LoadingButton className="btn-secondary" loading={busy === "polish"} loadingText="Gemini is polishing…" disabled={!!busy}
              onClick={() => act("polish", () => post<{ text: string; source: string; note: string }>("/api/ai/polish"), setDraft)}>
              <Sparkles className="h-4 w-4" /> Polish with Gemini
            </LoadingButton>
            {draft && <span className={`text-xs ${draft.source === "gemini" ? "text-emerald-700" : "text-amber-700"}`}>{draft.note}</span>}
          </div>
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<FileSignature className="h-5 w-5" />} title="Approve a plan" sub="Your approval is bound to this exact plan version. Changing any input voids it." />
          <label className="label">Plan</label>
          <select className="input mt-1" value={planId} onChange={(e) => setPlanId(e.target.value)}>
            {feasible.map((p) => <option key={p.id} value={p.id}>{p.recommended ? "★ " : ""}{planTitle(p, cur)}</option>)}
          </select>
          <LoadingButton className="btn-primary mt-3 w-full" loading={busy === "approve"} loadingText="Recording your approval…"
            disabled={!!busy || a.verdict.provisional || !feasible.length}
            onClick={() => act("approve", () => post<{ approval: Approval }>("/api/approve", { plan_id: planId }), (r) => { setApproval(r.approval); setExec(null); })}>
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
                  onClick={() => act("override", () => post<{ approval: Approval }>("/api/approve", { plan_id: ovr.plan || overridable[0].id, override: true, reason: ovr.reason }), (r) => { setApproval(r.approval); setExec(null); })}>
                  Approve with reserve override
                </LoadingButton>
              </div>
            )}
          </div>

          {approval && (
            <div className={`mt-4 rounded-xl p-4 ${approval.override ? "bg-rose-50 text-rose-900" : "bg-emerald-50 text-emerald-900"}`}>
              <div className="text-sm font-semibold">Approved <code className="rounded bg-white/70 px-1">{approval.id}</code></div>
              <div className="text-sm">{approval.label}</div>
              <div className="text-xs opacity-70">plan version {approval.version}{approval.reason && ` · reason: ${approval.reason}`}</div>
              <LoadingButton className="btn-primary mt-3 w-full" loading={busy === "execute"} loadingText="Executing in the sandbox…" disabled={!!busy}
                onClick={() => act("execute", () => post<Execution>("/api/execute"), async (r) => { setExec(r); await refresh(); })}>
                <Play className="h-4 w-4" /> Execute in the sandbox
              </LoadingButton>
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
        <Card className="p-6">
          <SectionTitle icon={<ScrollText className="h-5 w-5" />} title="Operation log" sub={logLoading ? "Refreshing…" : "Every tool call: time, tool, permission tier, input hash, approval ID, result."}
            right={<button className="btn-secondary" onClick={async () => { window.location.href = await logUrl(); }}><Download className="h-4 w-4" /> Export JSON</button>} />
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white text-left text-slate-500"><tr><th className="py-1">Time</th><th>Tier</th><th>Tool</th><th>Result</th></tr></thead>
              <tbody>
                {[...log].reverse().map((e, i) => (
                  <tr key={i} className="border-t border-slate-100 align-top">
                    <td className="py-1.5 font-mono text-slate-500">{e.time}</td>
                    <td><span className={`chip ${TIER[e.tier] ?? ""}`}>{e.tier}</span></td>
                    <td className="font-mono">{e.tool}<div className="text-slate-400">in:{e.input_hash}{e.approval_id && ` · ${e.approval_id}`}</div></td>
                    <td className={e.result === "BLOCKED" ? "font-semibold text-rose-700" : ""}>{e.result}{e.blocked_reason && <div className="font-normal text-rose-600">{e.blocked_reason}</div>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
