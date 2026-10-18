import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, ChevronDown, FolderCheck, Mail, ThumbsDown, ThumbsUp, XCircle } from "lucide-react";
import { approvedPlans, type ApprovedRecord } from "../api";
import { money } from "../format";
import { Callout, Card, EmptyState, Pill, Spinner } from "./ui";

function RecordCard({ r, open: initial }: { r: ApprovedRecord; open: boolean }) {
  const [open, setOpen] = useState(initial);
  const n = r.numbers;
  return (
    <Card className="p-0">
      <button className="flex w-full flex-col items-start justify-between gap-3 p-5 text-left sm:flex-row sm:gap-4" aria-expanded={open} onClick={() => setOpen(!open)}>
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            {r.status === "declined" ? <Pill tone="red">Declined</Pill> : <Pill tone="green">Approved</Pill>}
            <Pill tone={r.role === "buyer" ? "blue" : "slate"}>{r.role === "buyer" ? "You were the buyer" : "You were the seller"}</Pill>
            {r.override && <Pill tone="red">Reserve override</Pill>}
            <span className="text-xs text-slate-500">{r.time}</span>
          </div>
          <div className="font-serif text-lg font-semibold leading-snug text-slate-900">{r.plan}</div>
          <div className="text-sm text-slate-500">{r.case} · notified {r.counterparty}</div>
        </div>
        <div className="flex shrink-0 items-center gap-5 text-sm sm:text-right">
          <div><div className="text-xs text-slate-500">Lowest cash</div><div className="font-semibold">{money(n.low, r.currency)} <span className="text-xs font-normal text-slate-500">day {n.low_day}</span></div></div>
          {r.status !== "declined" && <div><div className="text-xs text-slate-500">Net profit</div><div className="font-semibold">{money(n.net_profit, r.currency)}</div></div>}
          <ChevronDown className={`h-5 w-5 text-slate-400 transition ${open ? "rotate-180" : ""}`} />
        </div>
      </button>
      {open && (
        <div className="space-y-4 border-t border-slate-100 p-5">
          <p className="text-sm font-semibold text-slate-800">{r.summary}{r.reason && <span className="font-normal text-slate-500"> · your reason: {r.reason}</span>}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border-l-[3px] border-emerald-500 bg-emerald-50/70 p-3 text-sm">
              <div className="mb-1 flex items-center gap-1 font-semibold text-emerald-800"><ThumbsUp className="h-4 w-4" /> {r.status === "declined" ? "Why you declined" : "Why you accepted"}</div>
              <ul className="list-disc space-y-1 pl-5">{r.reasons_for.map((t, i) => <li key={i}>{t}</li>)}</ul>
            </div>
            <div className="rounded-lg border-l-[3px] border-rose-500 bg-rose-50/70 p-3 text-sm">
              <div className="mb-1 flex items-center gap-1 font-semibold text-rose-800"><ThumbsDown className="h-4 w-4" /> {r.status === "declined" ? "What declining costs you" : "What it depends on"}</div>
              {r.reasons_against.length ? <ul className="list-disc space-y-1 pl-5">{r.reasons_against.map((t, i) => <li key={i}>{t}</li>)}</ul> : <p className="text-slate-500">Nothing.</p>}
            </div>
          </div>
          <div>
            <div className="mb-2 flex items-center gap-1 text-sm font-bold text-slate-900"><Mail className="h-4 w-4" /> Emails sent with this plan</div>
            <div className="space-y-2">
              {r.mails.map((m, i) => (
                <details key={i} className="rounded-lg border border-slate-200" open={i === 0}>
                  <summary className="cursor-pointer px-3 py-2 text-sm"><b>{m.to_name}</b> &lt;{m.to}&gt; · {m.subject} <span className="text-xs text-slate-500">· {m.status}</span></summary>
                  <pre className="whitespace-pre-wrap border-t border-slate-100 p-3 font-sans text-sm text-slate-700">{m.body}</pre>
                </details>
              ))}
            </div>
          </div>
          <div className="text-xs text-slate-400">Reference {r.id}</div>
          {r.sandbox ? (
            <div className="text-xs text-slate-500">
              {r.sandbox.ok ? <CheckCircle2 className="mr-1 inline h-3.5 w-3.5 text-emerald-600" /> : <XCircle className="mr-1 inline h-3.5 w-3.5 text-rose-600" />}
              Practice bank: {r.sandbox.ok ? `payments booked; balance matches SolvOrder's calculation (${r.sandbox.consistency})` : r.sandbox.steps[r.sandbox.steps.length - 1]}
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm text-slate-500"><FolderCheck className="h-4 w-4 shrink-0" /> Kept for this demo account until the server restarts.</div>
        <button className="btn-secondary" onClick={onBack}><ArrowLeft className="h-4 w-4" /> Back to the case</button>
      </div>
      {err && <Callout tone="critical">{err}</Callout>}
      {!plans && !err && <div className="py-10"><Spinner text="Loading your approved and declined plans…" /></div>}
      {plans?.length === 0 && <EmptyState icon={<FolderCheck className="h-5 w-5" />} title="Nothing here yet">Approve a plan and press Notify, or decline a deal that can't work. It will appear here with the email that was sent.</EmptyState>}
      {plans?.map((r, i) => <RecordCard key={r.id + r.time} r={r} open={i === 0} />)}
    </div>
  );
}
