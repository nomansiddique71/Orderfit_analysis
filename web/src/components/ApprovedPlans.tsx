import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, ChevronDown, FolderCheck, Mail, ThumbsDown, ThumbsUp } from "lucide-react";
import { approvedPlans, type ApprovedRecord } from "../api";
import { money } from "../format";
import { Callout, Card, Pill, Spinner } from "./ui";

function RecordCard({ r, open: initial }: { r: ApprovedRecord; open: boolean }) {
  const [open, setOpen] = useState(initial);
  const n = r.numbers;
  return (
    <Card className="p-0">
      <button className="flex w-full items-start justify-between gap-4 p-5 text-left" onClick={() => setOpen(!open)}>
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <code className="rounded bg-slate-100 px-1.5 text-xs">{r.id}</code>
            {r.status === "declined" ? <Pill tone="red">Declined</Pill> : <Pill tone="green">Approved</Pill>}
            <Pill tone={r.role === "buyer" ? "blue" : "slate"}>{r.role === "buyer" ? "You were the buyer" : "You were the seller"}</Pill>
            {r.override && <Pill tone="red">Reserve override</Pill>}
            <span className="text-xs text-slate-500">{r.time}</span>
          </div>
          <div className="font-bold text-slate-900">{r.plan}</div>
          <div className="text-sm text-slate-500">{r.case} · notified {r.counterparty}</div>
        </div>
        <div className="flex shrink-0 items-center gap-4 text-right text-sm">
          <div><div className="text-xs text-slate-500">Lowest cash</div><div className="font-semibold">{money(n.low, r.currency)} <span className="text-xs text-slate-400">d{n.low_day}</span></div></div>
          {r.status !== "declined" && <div><div className="text-xs text-slate-500">Net profit</div><div className="font-semibold">{money(n.net_profit, r.currency)}</div></div>}
          <ChevronDown className={`h-5 w-5 text-slate-400 transition ${open ? "rotate-180" : ""}`} />
        </div>
      </button>
      {open && (
        <div className="space-y-4 border-t border-slate-100 p-5">
          <p className="text-sm font-semibold text-slate-800">{r.summary}{r.reason && <span className="font-normal text-slate-500"> · your reason: {r.reason}</span>}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-xl bg-emerald-50/60 p-3 text-sm">
              <div className="mb-1 flex items-center gap-1 font-semibold text-emerald-800"><ThumbsUp className="h-4 w-4" /> {r.status === "declined" ? "Why you declined" : "Why you accepted"}</div>
              <ul className="list-disc space-y-1 pl-5">{r.reasons_for.map((t, i) => <li key={i}>{t}</li>)}</ul>
            </div>
            <div className="rounded-xl bg-rose-50/60 p-3 text-sm">
              <div className="mb-1 flex items-center gap-1 font-semibold text-rose-800"><ThumbsDown className="h-4 w-4" /> {r.status === "declined" ? "What declining costs you" : "What it depends on"}</div>
              {r.reasons_against.length ? <ul className="list-disc space-y-1 pl-5">{r.reasons_against.map((t, i) => <li key={i}>{t}</li>)}</ul> : <p className="text-slate-500">Nothing.</p>}
            </div>
          </div>
          <div>
            <div className="mb-2 flex items-center gap-1 text-sm font-bold text-slate-900"><Mail className="h-4 w-4" /> Emails sent with this plan</div>
            <div className="space-y-2">
              {r.mails.map((m, i) => (
                <details key={i} className="rounded-xl border border-slate-200" open={i === 0}>
                  <summary className="cursor-pointer px-3 py-2 text-sm"><b>{m.to_name}</b> &lt;{m.to}&gt; · {m.subject} <span className="text-xs text-slate-500">· {m.status}</span></summary>
                  <pre className="whitespace-pre-wrap border-t border-slate-100 p-3 font-sans text-sm text-slate-700">{m.body}</pre>
                </details>
              ))}
            </div>
          </div>
          {r.sandbox ? (
            <div className="text-xs text-slate-500">
              <CheckCircle2 className={`mr-1 inline h-3.5 w-3.5 ${r.sandbox.ok ? "text-emerald-600" : "text-rose-600"}`} />
              Sandbox bank: {r.sandbox.ok ? `payments booked; ledger matches the engine (${r.sandbox.consistency})` : r.sandbox.steps[r.sandbox.steps.length - 1]}
            </div>
          ) : <div className="text-xs text-slate-500">Declined: no payment was booked.</div>}
        </div>
      )}
    </Card>
  );
}

/** Every plan the owner approved and notified, with the emails that went out. */
export function ApprovedPlans({ onBack }: { onBack: () => void }) {
  const [plans, setPlans] = useState<ApprovedRecord[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { approvedPlans().then(setPlans).catch((e) => setErr((e as Error).message)); }, []);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-slate-500"><FolderCheck className="h-4 w-4" /> Kept in server memory for this demo account; cleared when the server restarts.</div>
        <button className="btn-secondary" onClick={onBack}><ArrowLeft className="h-4 w-4" /> Back to the case</button>
      </div>
      {err && <Callout tone="critical">{err}</Callout>}
      {!plans && !err && <div className="py-10"><Spinner text="Loading your approved and declined plans…" /></div>}
      {plans?.length === 0 && <Callout tone="info" title="Nothing here yet">Approve a plan and press Notify, or decline a deal that cannot work. It appears here with the email that was sent.</Callout>}
      {plans?.map((r, i) => <RecordCard key={r.id + r.time} r={r} open={i === 0} />)}
    </div>
  );
}
