import { useEffect, useState } from "react";
import { AlertTriangle, Bot, Box, Building2, Calculator, CheckCircle2, ChevronRight, Download, Inbox, Landmark, ScrollText, ShieldX, User, XCircle } from "lucide-react";
import { get, logUrl, session, type LogEntry } from "../api";
import { describe, friendlyTime, type LogStatus } from "../logText";
import { money } from "../format";
import { Card, EmptyState, Pill, SectionTitle, Segmented, Spinner } from "./ui";

export interface SandboxView {
  outbox: { to: string; subject: string; body: string; status: string; time: string; approval_id: string }[];
  bank: { approval_id: string; opening: number | null; rows: { day: number; label: string; amount: number; balance: number }[] };
  lender: { offer: string; lender: string; terms: Record<string, string | number>; status: string; approval_id: string }[];
}
export type SandboxTab = "outbox" | "bank" | "lender";

export const WHERE: Record<LogEntry["where"], { label: string; cls: string; icon: React.ReactNode }> = {
  sandbox: { label: "Practice systems", cls: "bg-violet-50 text-violet-800 ring-1 ring-inset ring-violet-200", icon: <Box className="h-3 w-3" /> },
  gemini: { label: "Gemini", cls: "bg-sky-50 text-sky-800 ring-1 ring-inset ring-sky-200", icon: <Bot className="h-3 w-3" /> },
  engine: { label: "SolvOrder", cls: "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-200", icon: <Calculator className="h-3 w-3" /> },
  owner: { label: "You", cls: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200", icon: <User className="h-3 w-3" /> },
  blocked: { label: "Blocked", cls: "bg-rose-50 text-rose-800 ring-1 ring-inset ring-rose-200", icon: <ShieldX className="h-3 w-3" /> },
};
const SANDBOX_TAB: Record<string, SandboxTab> = { "outbox.send": "outbox", "bank.post": "bank", "lender.accept": "lender", "consistency_check": "bank" };

/** What the sandbox actually holds: the mock outbox, simulated bank and mock lender portal. */
export function SandboxPanel({ version, tab, setTab, cur }: { version: number; tab: SandboxTab; setTab: (t: SandboxTab) => void; cur: string }) {
  const [v, setV] = useState<SandboxView | null>(null);
  useEffect(() => {
    session().then((sid) => get<SandboxView>(`/api/sandbox?session_id=${encodeURIComponent(sid)}`)).then(setV).catch(() => undefined);
  }, [version]);
  return (
    <Card className="p-6">
      <div id="sandbox-panel" />
      <SectionTitle icon={<Box className="h-5 w-5" />} title="Inside the sandbox"
        sub="Exactly what SolvOrder did for you, in practice versions of an outbox, a bank and a lender. No email leaves, no money moves, no loan is signed." />
      <Segmented value={tab} onChange={setTab} options={[
        { value: "outbox", label: `Demo outbox (${v?.outbox.length ?? 0})` },
        { value: "bank", label: `Practice bank (${v?.bank.rows.length ?? 0})` },
        { value: "lender", label: `Practice lender (${v?.lender.length ?? 0})` },
      ]} />
      <div className="mt-4">
        {!v && <Spinner text="Opening the sandbox…" />}
        {v && tab === "outbox" && (v.outbox.length === 0
          ? <EmptyState icon={<Inbox className="h-5 w-5" />} title="No emails yet">Approve a plan and press Notify: its emails land here instead of being really sent.</EmptyState>
          : <div className="space-y-3">{v.outbox.map((m, i) => (
            <div key={i} className="rounded-xl border border-slate-200">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                <span>{m.time} · To <b className="text-slate-700">{m.to}</b></span>
                <span className="flex gap-2"><Pill tone="violet">{m.status}</Pill></span>
              </div>
              <div className="px-3 pt-2 text-sm font-semibold">{m.subject}</div>
              <pre className="whitespace-pre-wrap p-3 pt-1 font-sans text-sm text-slate-700">{m.body.split("\n").slice(2).join("\n") || m.body}</pre>
            </div>))}</div>)}
        {v && tab === "bank" && (v.bank.rows.length === 0
          ? <EmptyState icon={<Landmark className="h-5 w-5" />} title="Nothing booked yet">Pressing Notify after you approve a plan books its payments here.</EmptyState>
          : <>
            <div className="mb-2 text-xs text-slate-500">Payments for the plan you approved, starting from {money(v.bank.opening ?? 0, cur)} in the bank today.</div>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Day</th><th>Booking</th><th className="text-right">Amount</th><th className="text-right">Balance</th></tr></thead>
              <tbody>{v.bank.rows.map((r, i) => (
                <tr key={i} className="border-t border-slate-100"><td className="py-1.5 text-slate-500">{r.day}</td><td>{r.label}</td>
                  <td className={`text-right ${r.amount < 0 ? "text-rose-700" : "text-emerald-700"}`}>{money(r.amount, cur, { sign: true })}</td>
                  <td className="text-right font-semibold">{money(r.balance, cur)}</td></tr>))}</tbody>
            </table></>)}
        {v && tab === "lender" && (v.lender.length === 0
          ? <EmptyState icon={<Building2 className="h-5 w-5" />} title="No loans accepted">Only plans that include a loan use the lender, and only on the lender's own terms.</EmptyState>
          : <div className="space-y-2">{v.lender.map((l, i) => (
            <div key={i} className="rounded-xl border border-slate-200 p-3 text-sm">
              <div className="flex items-center justify-between font-semibold">{l.lender} · {l.offer}<Pill tone="violet">{l.status}</Pill></div>
              <div className="mt-1 text-xs text-slate-500">Loan {money(Number(l.terms.principal), cur)} · fee {l.terms.fee_pct}% · {l.terms.monthly_rate_pct}%/month · origination {money(Number(l.terms.origination), cur)} · draw day {l.terms.draw_day} → repay day {l.terms.repay_day}</div>
              
            </div>))}</div>)}
      </div>
    </Card>
  );
}

const STATUS: Record<LogStatus, { icon: React.ReactNode; cls: string }> = {
  success: { icon: <CheckCircle2 className="h-4 w-4" />, cls: "text-emerald-700" },
  warning: { icon: <AlertTriangle className="h-4 w-4" />, cls: "text-amber-700" },
  failed: { icon: <XCircle className="h-4 w-4" />, cls: "text-rose-700" },
};

/** One log entry as a sentence, with the raw technical record behind "View details". */
function LogRow({ e, onOpenSandbox }: { e: LogEntry; onOpenSandbox: (t: SandboxTab) => void }) {
  const line = describe(e);
  const st = STATUS[line.status];
  const tab = e.where === "sandbox" ? SANDBOX_TAB[e.tool] : undefined;
  return (
    <li className="grid grid-cols-[64px_1fr] gap-3 py-3.5 sm:grid-cols-[76px_1fr]">
      <time className="pt-0.5 text-xs text-slate-500" title={`${e.time} (server time)`}>{friendlyTime(e.time)}</time>
      <div className="min-w-0">
        <p className="text-sm leading-relaxed text-slate-900">{line.sentence}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <span className={`inline-flex items-center gap-1 font-semibold ${st.cls}`}>{st.icon}{line.statusText}</span>
          <span className={`chip ${WHERE[e.where].cls}`}>{WHERE[e.where].icon}{line.who}</span>
          {tab && <button className="font-semibold text-violet-700 hover:underline" onClick={() => onOpenSandbox(tab)}>See it in the sandbox →</button>}
        </div>
        {line.next && <p className="mt-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900"><b>What to do:</b> {line.next}</p>}
        <details className="group mt-1.5">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-xs text-slate-500 hover:text-slate-800 [&::-webkit-details-marker]:hidden">
            <ChevronRight className="h-3 w-3 transition group-open:rotate-90" /> View details
          </summary>
          <dl className="mt-1.5 grid grid-cols-[110px_1fr] gap-x-3 gap-y-0.5 rounded-md bg-slate-50 p-2.5 font-mono text-[11px] text-slate-600">
            <dt>step</dt><dd className="break-all">{e.tool}</dd>
            <dt>permission tier</dt><dd>{e.tier}</dd>
            <dt>raw result</dt><dd className="break-all">{e.result}</dd>
            {e.blocked_reason && <><dt>blocked reason</dt><dd className="break-all">{e.blocked_reason}</dd></>}
            {e.approval_id && <><dt>approval ID</dt><dd className="break-all">{e.approval_id}</dd></>}
            <dt>input hash</dt><dd className="break-all">{e.input_hash}</dd>
            <dt>time</dt><dd>{e.time} (server)</dd>
          </dl>
        </details>
      </div>
    </li>
  );
}

/** The operation log as plain sentences, newest first, filterable by who did each step. */
export function OperationLog({ log, loading, onOpenSandbox }: { log: LogEntry[]; loading: boolean; onOpenSandbox: (t: SandboxTab) => void }) {
  const [filter, setFilter] = useState<"all" | LogEntry["where"]>("all");
  const rows = [...log].reverse().filter((e) => filter === "all" || e.where === filter);
  const count = (w: LogEntry["where"]) => log.filter((e) => e.where === w).length;
  const chip = (on: boolean) => `chip px-3 py-1 transition ${on ? "bg-slate-900 text-white ring-0" : "bg-white text-slate-600 ring-1 ring-inset ring-slate-300 hover:ring-slate-400"}`;
  return (
    <Card className="p-6">
      <SectionTitle icon={<ScrollText className="h-5 w-5" />} title="Operation log"
        sub={loading ? "Refreshing…" : "Everything that happened in this case, newest first: who did it and how it went."}
        right={<button className="btn-secondary" onClick={async () => { window.location.href = await logUrl(); }}><Download className="h-4 w-4" /> Download (JSON)</button>} />
      <div className="mb-2 flex flex-wrap gap-2 text-xs" role="group" aria-label="Show steps by">
        <button className={chip(filter === "all")} aria-pressed={filter === "all"} onClick={() => setFilter("all")}>Everything ({log.length})</button>
        {(Object.keys(WHERE) as LogEntry["where"][]).map((w) => (
          <button key={w} className={chip(filter === w)} aria-pressed={filter === w} onClick={() => setFilter(w)}>{WHERE[w].icon}{WHERE[w].label} ({count(w)})</button>
        ))}
      </div>
      <div className="scroll-thin max-h-[30rem] overflow-auto pr-1">
        {rows.length > 0 && <div className="sticky top-0 z-[1] border-b border-slate-200 bg-white py-2 text-xs font-semibold text-slate-500">This session</div>}
        <ol className="divide-y divide-slate-100">
          {rows.map((e, i) => <LogRow key={`${e.time}-${e.tool}-${i}`} e={e} onOpenSandbox={onOpenSandbox} />)}
        </ol>
        {rows.length === 0 && <div className="mt-3"><EmptyState title="Nothing here yet">{filter === "all" ? "Steps appear here as you work through the case." : "No steps of this kind yet. Choose “Everything” to see all steps."}</EmptyState></div>}
      </div>
    </Card>
  );
}
