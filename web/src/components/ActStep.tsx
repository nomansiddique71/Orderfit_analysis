import { Ban, BellRing, CheckCircle2, FileSignature, Landmark, ListTree, Mail, Send, ShieldCheck, Sparkles, X, XCircle } from "lucide-react";
import type { Analysis } from "../api";
import { useActStep, useDeclineStep, type Draft } from "../hooks/useActStep";
import { BreakdownModal } from "./Breakdown";
import type { Choice } from "./OptionsStep";
import { OperationLog, SandboxPanel } from "./Sandbox";
import { money, planTitle } from "../format";
import { plainT3Reason } from "../logText";
import { BusyOverlay, Callout, Card, LoadingButton, Pill, SectionTitle, Updating } from "./ui";

/** "Notify my customer" (seller) / "Notify my supplier" (buyer): the deal's counterparty. */
function notifyLabel(a: Analysis, drafts: { party?: string; to_name: string }[] | null) {
  const first = drafts?.[0];
  const who = a.case.role === "buyer" ? "supplier" : "customer";
  const others = (drafts ?? []).slice(1).map((d) => d.party === "lender" ? "lender" : d.party ?? "").filter(Boolean);
  return `Notify my ${who}${first ? ` (${first.to_name})` : ""}${others.length ? ` + ${others.join(" + ")}` : ""}`;
}

/** An email as the recipient would see it: who it goes to, the subject, then the body. */
function MailPreview({ to, name, subject, body, polished, note }: { to: string; name: string; subject?: string; body: string; polished?: boolean; note?: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5 text-xs text-slate-500">
        <span className="min-w-0">To <b className="text-slate-800">{name}</b> <span className="break-all">&lt;{to}&gt;</span></span>
        {polished && <Pill tone="green">Reworded by Gemini · numbers checked</Pill>}
      </div>
      {subject && <div className="px-4 pt-3 text-sm font-semibold text-slate-900">{subject}</div>}
      <pre className="whitespace-pre-wrap px-4 pt-2 pb-4 font-sans text-sm leading-relaxed text-slate-700">{body}</pre>
      {note && <div className="px-4 pb-3 text-xs text-amber-800">{note}</div>}
    </div>
  );
}

function NotifyModal({ a, drafts, busy, onSend, onClose, title, intro }: {
  a: Analysis; drafts: { to: string; to_name: string; subject: string; body: string; source: string }[];
  busy: boolean; onSend: () => void; onClose: () => void; title?: string; intro?: string;
}) {
  const who = a.case.role === "buyer" ? "supplier" : "customer";
  return (
    <div role="dialog" aria-modal="true" aria-label={title ?? `Notify your ${who}`} className="fixed inset-0 z-40 grid place-items-center bg-ink-950/45 p-3 sm:p-4">
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5 sm:p-6">
          <div className="flex gap-3">
            <BellRing className="mt-1 h-5 w-5 shrink-0 text-brand-600" />
            <div>
              <h3 className="text-xl font-semibold text-slate-900">{title ?? `Notify your ${who} by mail?`}</h3>
              <p className="mt-1 text-sm leading-relaxed text-slate-500">{intro ?? `SolvOrder wrote ${drafts.length === 1 ? "this email" : `these ${drafts.length} emails`} from the plan you approved. Sending also books the plan in the sandbox bank and files it under Approved / declined plans.`}</p>
            </div>
          </div>
          <button className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close" onClick={onClose}><X className="h-5 w-5" /></button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-5 sm:p-6">
          {drafts.map((d, i) => <MailPreview key={i} to={d.to} name={d.to_name} subject={d.subject} body={d.body.split("\n").slice(2).join("\n")} polished={d.source === "gemini"} />)}
          <Callout tone="info">Demo: the email goes to SolvOrder's outbox and is not really delivered. No real email or payment leaves SolvOrder.</Callout>
        </div>
        <div className="flex flex-col-reverse gap-2 border-t border-slate-200 p-4 sm:flex-row sm:justify-end sm:gap-3">
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
  const s = useActStep({ a, refresh, choice, onSent });
  const { busy, drafts, approval, exec, ovr, setOvr, ovrPlan, overridable, feasible } = s;

  return (
    <div className="space-y-6">
      <BusyOverlay show={busy === "notify"} title="Notifying and booking the approved plan"
        steps={["Sending the emails to the demo outbox", "Checking your approval and the fraud gate", "Booking payments in the simulated bank", "Filing the plan under Approved / declined plans"]} />
      {s.notifyOpen && drafts && <NotifyModal a={a} drafts={drafts} busy={busy === "notify"} onClose={() => s.setNotifyOpen(false)} onSend={s.sendNotify} />}
      {s.bd && <BreakdownModal planId={s.draftPlan} title={planTitle(a.plans.find((p) => p.id === s.draftPlan)!, cur)} cur={cur} onClose={() => s.setBd(false)} />}
      {a.verdict.provisional && <Callout tone="warning" title="Confirm the uncertain facts first">Approval is locked while a value that changes the result is unconfirmed. Use the Confirm buttons on the See the cash risk screen.</Callout>}
      {s.blocked && <Callout tone="critical" title="A fraud check is still open">{a.verdict.execution_blocks.join("; ")}. You can approve, but every payment will be refused until you record the check on the Check the facts screen.</Callout>}

      <div className="grid items-start gap-6 xl:grid-cols-[1fr_1.15fr]">
        <Card className="p-6">
          <SectionTitle icon={<FileSignature className="h-5 w-5" />} title="Approve a plan" sub="Pick any safe plan. The recommended one is starred, but the choice is yours. Then let the other side know by email." />
          <label className="block">
            <span className="label">Plan</span>
            <select className="input mt-1.5" value={s.planId} onChange={(e) => s.setPlanId(e.target.value)}>
              {feasible.map((p) => <option key={p.id} value={p.id}>{p.recommended ? "★ " : ""}{planTitle(p, cur)}</option>)}
            </select>
          </label>
          {!feasible.length && <p className="mt-2 text-xs text-slate-500">No plan keeps your reserve, so there is nothing safe to approve here.</p>}
          <button className="btn-quiet -ml-2 mt-1" disabled={!s.draftPlan} onClick={() => s.setBd(true)}><ListTree className="h-4 w-4" /> See the money breakdown for this plan</button>
          <LoadingButton className={`${approval ? "btn-secondary" : "btn-primary py-2.5"} mt-3 w-full`} loading={busy === "approve"} loadingText="Recording your approval…"
            disabled={!!busy || a.verdict.provisional || !feasible.length} onClick={s.approve}>
            <CheckCircle2 className="h-4 w-4" /> Approve this plan
          </LoadingButton>

          {approval && (
            <div className={`mt-5 rounded-lg border-l-[3px] p-4 ${approval.override ? "border-rose-500 bg-rose-50 text-rose-900" : "border-emerald-500 bg-emerald-50 text-emerald-900"}`}>
              <div className="flex items-center gap-2 text-sm font-semibold"><CheckCircle2 className="h-4 w-4" /> You approved this plan{approval.override && " (reserve override)"}</div>
              <div className="mt-0.5 text-sm">{approval.label}</div>
              {approval.reason && <div className="mt-0.5 text-xs opacity-80">Your reason: {approval.reason}</div>}
              <details className="mt-1 text-xs opacity-70"><summary className="cursor-pointer">Reference</summary>Approval {approval.id} · plan version {approval.version}</details>
              {approval.messages.map((m, i) => (
                <div key={i} className={`mt-3 rounded-md border bg-white p-3 text-sm text-slate-800 ${m.sent ? "border-emerald-200" : "border-rose-200"}`}>
                  <div className="flex flex-wrap items-center gap-2 font-semibold">
                    {m.sent ? <Send className="h-4 w-4 text-emerald-700" /> : <XCircle className="h-4 w-4 text-rose-600" />}
                    {m.sent ? `Email sent to ${m.to_name}` : `Email to ${m.to_name} not sent`}
                    <Pill tone="violet">Demo outbox</Pill></div>
                  <div className="text-xs text-slate-500">{m.to} · {m.status}{m.source === "gemini" ? " · reworded by Gemini, numbers checked" : ""}</div>
                  <div className="mt-1 text-xs font-medium text-slate-700">{m.subject}</div>
                </div>
              ))}
              {!approval.notified ? (
                <LoadingButton className="btn-primary mt-4 w-full py-2.5" loading={busy === "notify"} loadingText="Sending…" disabled={!!busy || !drafts}
                  onClick={() => s.setNotifyOpen(true)}>
                  <BellRing className="h-4 w-4" /> {notifyLabel(a, drafts)}
                </LoadingButton>
              ) : (
                <button className="btn-secondary mt-4 w-full" onClick={onOpenApproved}>Open Approved / declined plans{s.record ? ` (${s.record.id})` : ""}</button>
              )}
            </div>
          )}
          {s.err && <div className="mt-3"><Callout tone="critical" title="That didn't work">{s.err} Please try again.</Callout></div>}

          <div className="mt-5 border-t border-slate-200 pt-4">
            {!ovr.open ? (
              <button className="text-sm font-semibold text-rose-700 hover:underline disabled:opacity-40 disabled:no-underline" disabled={!overridable.length || a.verdict.provisional} onClick={() => setOvr({ ...ovr, open: true })}>
                Approve a plan that breaks the reserve (override)…
              </button>
            ) : (
              <div className="space-y-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm">
                <div className="font-semibold text-rose-900">Override: approve a plan that dips below your reserve</div>
                <select className="input" aria-label="Plan to approve with an override" value={ovr.plan || overridable[0]?.id} onChange={(e) => setOvr({ ...ovr, plan: e.target.value })}>
                  {overridable.map((p) => <option key={p.id} value={p.id}>{planTitle(p, cur)} (low {money(p.min_balance, cur)}, day {p.min_day})</option>)}
                </select>
                <input className="input" aria-label="Reason" placeholder="Why? (at least 5 characters, kept in the log)" value={ovr.reason} maxLength={300} onChange={(e) => setOvr({ ...ovr, reason: e.target.value })} />
                {ovrPlan && <label className="flex items-start gap-2 text-rose-900"><input type="checkbox" className="mt-1 accent-rose-600" checked={ovr.ack} onChange={(e) => setOvr({ ...ovr, ack: e.target.checked })} />
                  I understand cash falls to {money(ovrPlan.min_balance, cur)} on day {ovrPlan.min_day}, below my {money(a.case.reserve, cur)} reserve.</label>}
                <LoadingButton className="btn-danger w-full" loading={busy === "override"} loadingText="Recording override…"
                  disabled={!ovr.ack || ovr.reason.trim().length < 5 || !!busy} onClick={s.approveOverride}>
                  Approve with reserve override
                </LoadingButton>
                <button className="w-full text-xs font-semibold text-slate-500 hover:text-slate-800" onClick={() => setOvr({ open: false, plan: "", reason: "", ack: false })}>Cancel the override</button>
              </div>
            )}
          </div>
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<Mail className="h-5 w-5" />} title="The email for this plan" sub="Written from SolvOrder's numbers for the plan you selected. Gemini can reword it but never change a figure. It is sent when you press Notify after approving." />
          <Updating active={s.draftLoading}>
            {!drafts && <div className="rounded-lg bg-slate-50 p-4"><span className="text-sm text-slate-500">Writing the email…</span></div>}
            <div className="space-y-3">
              {drafts?.map((d: Draft, i) => <MailPreview key={i} to={d.to} name={d.to_name} body={d.body} polished={d.source === "gemini"} note={d.note && d.source !== "gemini" ? d.note : undefined} />)}
            </div>
          </Updating>
          {drafts && drafts.length > 1 && <p className="mt-2 text-xs text-slate-500">This plan needs {drafts.length} parties to agree, so {drafts.length} emails go out.</p>}
          <div className="mt-3">
            <LoadingButton className="btn-secondary" loading={busy === "polish"} loadingText="Gemini is polishing…" disabled={!!busy || !drafts} onClick={s.polish}>
              <Sparkles className="h-4 w-4" /> Polish with Gemini
            </LoadingButton>
          </div>
        </Card>
      </div>

      {exec && (
        <Card className="p-6">
          <SectionTitle icon={exec.ok ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />} title={`What happened after you pressed Notify${exec.override ? " (reserve override)" : ""}`}
            sub="In the practice bank, demo outbox and practice lender. Nothing real is sent or paid." />
          <ol className="space-y-2">
            {exec.steps.map((st, i) => {
              const good = exec.ok || i < exec.steps.length - 1;
              return <li key={i} className="flex gap-2 text-sm">{good ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <Ban className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />}<span><span className="sr-only">{good ? "Done: " : "Stopped: "}</span>{st}</span></li>;
            })}
          </ol>
          {exec.consistency && <div className="mt-3"><Pill tone={exec.consistency === "passed" ? "green" : "red"}>{exec.consistency === "passed" ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />} Practice bank matches SolvOrder's calculation: {exec.consistency}</Pill></div>}
          {exec.ledger.length > 0 && (
            <details className="mt-4"><summary className="cursor-pointer text-sm font-semibold text-slate-800"><Landmark className="mr-1 inline h-4 w-4" />Payments booked in the practice bank ({exec.ledger.length})</summary>
              <table className="mt-2 w-full text-sm"><tbody>{exec.ledger.map((m, i) => <tr key={i} className="border-t border-slate-100"><td className="py-1.5 text-slate-500">Day {m.day}</td><td>{m.label}</td><td className="text-right">{money(Number(m.amount), cur, { sign: true })}</td></tr>)}</tbody></table>
            </details>
          )}
        </Card>
      )}

      <SandboxPanel version={s.sbVersion} tab={s.sbTab} setTab={s.setSbTab} cur={cur} />

      <div className="grid items-start gap-6 xl:grid-cols-[1fr_2fr]">
        <Card className="p-6">
          <SectionTitle icon={<ShieldCheck className="h-5 w-5" />} title="Try to make it misbehave" sub="SolvOrder has no way to do any of these. Each attempt is blocked and written to the log." />
          <div className="grid gap-2">
            {[["real_email", "Send a real email"], ["live_transfer", "Make a real bank transfer"], ["invent_terms", "Invent better loan terms"], ["edit_document", "Edit a source document"]].map(([k, l]) => (
              <LoadingButton key={k} className="btn-secondary justify-start" loading={s.t3Busy === k} loadingText="Trying…" disabled={!!s.t3Busy} onClick={() => s.tryT3(k)}>
                <Ban className="h-4 w-4 text-rose-600" />{l}
              </LoadingButton>
            ))}
          </div>
          {s.t3 && <div className="mt-3"><Callout tone="critical" title="Blocked">SolvOrder refused: {plainT3Reason(s.t3)}</Callout></div>}
        </Card>
        <OperationLog log={s.log} loading={s.logLoading} onOpenSandbox={s.openSandbox} />
      </div>
    </div>
  );
}

/** No way of accepting keeps the reserve: send the polite, justified decline and file it. */
export function DeclineStep({ a, onSent, onOpenApproved }: { a: Analysis; onSent: (text: string) => void; onOpenApproved: () => void }) {
  const cur = a.case.currency;
  const who = a.case.role === "buyer" ? "supplier" : "customer";
  const s = useDeclineStep(onSent);
  const { drafts, busy, done } = s;
  const declinePlan = a.plans.find((p) => p.id === "decline")!;
  return (
    <div className="space-y-6">
      {s.bd && <BreakdownModal planId="decline" title={planTitle(declinePlan, cur)} cur={cur} onClose={() => s.setBd(false)} />}
      {s.open && drafts && (
        <NotifyModal a={a} drafts={drafts} busy={busy === "send"} title={`Decline politely and tell your ${who}?`}
          intro="SolvOrder wrote this email from its own numbers: why the deal cannot work for your cash and, if one exists, the change that would let you accept. Sending files it under Approved / declined plans. No payment is booked."
          onClose={() => s.setOpen(false)} onSend={s.send} />
      )}
      <Callout tone="warning" title={`Recommended: decline the ${a.case.deal}`}>
        No way of accepting keeps your cash above your {money(a.case.reserve, cur)} reserve, so SolvOrder recommends a polite no, with the reasons.{" "}
        <button className="link" onClick={() => s.setBd(true)}>See the full breakdown</button>
      </Callout>
      <Card className="p-6">
        <SectionTitle icon={<Mail className="h-5 w-5" />} title={`Your email to the ${who}`} sub="Written from SolvOrder's numbers. Gemini can reword it but never change a figure." />
        {!drafts && !s.err && <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">Writing the email…</div>}
        <div className="space-y-3">
          {drafts?.map((d, i) => <MailPreview key={i} to={d.to} name={d.to_name} body={d.body} polished={d.source === "gemini"} />)}
        </div>
        <div className="mt-5 flex flex-col-reverse gap-3 border-t border-slate-200 pt-4 sm:flex-row sm:items-center sm:justify-between">
          {!done ? <>
            <LoadingButton className="btn-secondary" loading={busy === "polish"} loadingText="Gemini is polishing…" disabled={!!busy || !drafts} onClick={s.polish}>
              <Sparkles className="h-4 w-4" /> Polish with Gemini
            </LoadingButton>
            <button className="btn-danger py-2.5" disabled={!!busy || !drafts} onClick={() => s.setOpen(true)}>
              <Send className="h-4 w-4" /> Decline and notify my {who}{drafts?.[0] ? ` (${drafts[0].to_name})` : ""}
            </button>
          </> : <>
            <Pill tone="green"><CheckCircle2 className="h-3 w-3" /> Sent to {done.counterparty}</Pill>
            <button className="btn-secondary" onClick={onOpenApproved}>Open Approved / declined plans</button>
          </>}
        </div>
        {s.err && <div className="mt-3"><Callout tone="critical" title="That didn't work">{s.err} Please try again.</Callout></div>}
      </Card>
    </div>
  );
}
