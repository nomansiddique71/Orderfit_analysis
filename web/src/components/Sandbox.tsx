import { useEffect, useState } from "react";
import { Bot, Box, Building2, Calculator, Download, Inbox, Landmark, ScrollText, ShieldX, User } from "lucide-react";
import { get, logUrl, session, type LogEntry } from "../api";
import { money } from "../format";
import { Card, Pill, SectionTitle, Segmented, Spinner } from "./ui";

export interface SandboxView {
  outbox: { to: string; subject: string; body: string; status: string; time: string; approval_id: string }[];
  bank: { approval_id: string; opening: number | null; rows: { day: number; label: string; amount: number; balance: number }[] };
  lender: { offer: string; lender: string; terms: Record<string, string | number>; status: string; approval_id: string }[];
}
export type SandboxTab = "outbox" | "bank" | "lender";

export const WHERE: Record<LogEntry["where"], { label: string; cls: string; icon: React.ReactNode }> = {
  sandbox: { label: "Sandbox", cls: "bg-violet-100 text-violet-800", icon: <Box className="h-3 w-3" /> },
  gemini: { label: "Gemini", cls: "bg-sky-100 text-sky-800", icon: <Bot className="h-3 w-3" /> },
  engine: { label: "Engine", cls: "bg-slate-200 text-slate-700", icon: <Calculator className="h-3 w-3" /> },
  owner: { label: "You", cls: "bg-emerald-100 text-emerald-800", icon: <User className="h-3 w-3" /> },
  blocked: { label: "Blocked", cls: "bg-rose-100 text-rose-800", icon: <ShieldX className="h-3 w-3" /> },
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
        sub="Exactly what SolvOrder did on your behalf. These are mock systems: no email leaves, no money moves, no loan is signed." />
      <Segmented value={tab} onChange={setTab} options={[
        { value: "outbox", label: `Mock outbox (${v?.outbox.length ?? 0})` },
        { value: "bank", label: `Simulated bank (${v?.bank.rows.length ?? 0})` },
        { value: "lender", label: `Mock lender portal (${v?.lender.length ?? 0})` },
      ]} />
      <div className="mt-4">
        {!v && <Spinner text="Opening the sandbox…" />}
        {v && tab === "outbox" && (v.outbox.length === 0
          ? <Empty icon={<Inbox className="h-5 w-5" />} text="No messages yet. Approving a plan sends its messages here." />
          : <div className="space-y-3">{v.outbox.map((m, i) => (
            <div key={i} className="rounded-xl border border-slate-200">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                <span>{m.time} · To <b className="text-slate-700">{m.to}</b></span>
                <span className="flex gap-2">{m.approval_id && <Pill tone="slate">{m.approval_id}</Pill>}<Pill tone="violet">{m.status}</Pill></span>
              </div>
              <div className="px-3 pt-2 text-sm font-semibold">{m.subject}</div>
              <pre className="whitespace-pre-wrap p-3 pt-1 font-sans text-sm text-slate-700">{m.body.split("\n").slice(2).join("\n") || m.body}</pre>
            </div>))}</div>)}
        {v && tab === "bank" && (v.bank.rows.length === 0
          ? <Empty icon={<Landmark className="h-5 w-5" />} text="Nothing booked yet. Pressing Notify after approval books the approved plan here." />
          : <>
            <div className="mb-2 text-xs text-slate-500">Ledger for approval <b>{v.bank.approval_id}</b>, starting from {money(v.bank.opening ?? 0, cur)} today.</div>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Day</th><th>Booking</th><th className="text-right">Amount</th><th className="text-right">Balance</th></tr></thead>
              <tbody>{v.bank.rows.map((r, i) => (
                <tr key={i} className="border-t border-slate-100"><td className="py-1.5 text-slate-500">{r.day}</td><td>{r.label}</td>
                  <td className={`text-right ${r.amount < 0 ? "text-rose-700" : "text-emerald-700"}`}>{money(r.amount, cur, { sign: true })}</td>
                  <td className="text-right font-semibold">{money(r.balance, cur)}</td></tr>))}</tbody>
            </table></>)}
        {v && tab === "lender" && (v.lender.length === 0
          ? <Empty icon={<Building2 className="h-5 w-5" />} text="No loans accepted. Only plans with financing use the lender portal, and only on the lender's own terms." />
          : <div className="space-y-2">{v.lender.map((l, i) => (
            <div key={i} className="rounded-xl border border-slate-200 p-3 text-sm">
              <div className="flex items-center justify-between font-semibold">{l.lender} · {l.offer}<Pill tone="violet">{l.status}</Pill></div>
              <div className="mt-1 text-xs text-slate-500">Principal {money(Number(l.terms.principal), cur)} · fee {l.terms.fee_pct}% · {l.terms.monthly_rate_pct}%/month · origination {money(Number(l.terms.origination), cur)} · draw day {l.terms.draw_day} → repay day {l.terms.repay_day}</div>
              <div className="text-xs text-slate-400">approval {l.approval_id}</div>
            </div>))}</div>)}
      </div>
    </Card>
  );
}

function Empty({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <div className="flex items-center gap-3 rounded-xl border border-dashed border-slate-200 p-5 text-sm text-slate-500">{icon}{text}</div>;
}

/** The operation log, labelled by where each step ran. Sandbox rows open the sandbox view. */
export function OperationLog({ log, loading, onOpenSandbox }: { log: LogEntry[]; loading: boolean; onOpenSandbox: (t: SandboxTab) => void }) {
  const [filter, setFilter] = useState<"all" | LogEntry["where"]>("all");
  const rows = [...log].reverse().filter((e) => filter === "all" || e.where === filter);
  const count = (w: LogEntry["where"]) => log.filter((e) => e.where === w).length;
  return (
    <Card className="p-6">
      <SectionTitle icon={<ScrollText className="h-5 w-5" />} title="Operation log"
        sub={loading ? "Refreshing…" : "Every step, newest first, with where it ran. Violet = executed in the sandbox: click it to see what it did."}
        right={<button className="btn-secondary" onClick={async () => { window.location.href = await logUrl(); }}><Download className="h-4 w-4" /> Export JSON</button>} />
      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        <button className={`chip ${filter === "all" ? "bg-ink-900 text-white" : "bg-slate-100 text-slate-600"}`} onClick={() => setFilter("all")}>All ({log.length})</button>
        {(Object.keys(WHERE) as LogEntry["where"][]).map((w) => (
          <button key={w} className={`chip ${filter === w ? "ring-2 ring-offset-1 ring-slate-400" : ""} ${WHERE[w].cls}`} onClick={() => setFilter(w)}>{WHERE[w].icon}{WHERE[w].label} ({count(w)})</button>
        ))}
      </div>
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white text-left text-xs text-slate-500"><tr><th className="py-1">Time</th><th>Where</th><th>What happened</th><th>Result</th></tr></thead>
          <tbody>
            {rows.map((e, i) => {
              const tab = e.where === "sandbox" ? SANDBOX_TAB[e.tool] : undefined;
              return (
                <tr key={i} className={`border-t border-slate-100 align-top ${e.where === "sandbox" ? "bg-violet-50/40" : e.where === "blocked" ? "bg-rose-50/40" : ""}`}>
                  <td className="py-2 pr-2 font-mono text-xs text-slate-500">{e.time}</td>
                  <td className="pr-2"><span className={`chip ${WHERE[e.where].cls}`}>{WHERE[e.where].icon}{WHERE[e.where].label}</span></td>
                  <td className="pr-2">
                    <div className="font-medium text-slate-800">{e.what}</div>
                    <div className="font-mono text-[11px] text-slate-400">{e.tool} · {e.tier}{e.approval_id && ` · ${e.approval_id}`} · in:{e.input_hash}</div>
                    {tab && <button className="mt-0.5 text-xs font-semibold text-violet-700 hover:underline" onClick={() => onOpenSandbox(tab)}>View in the sandbox →</button>}
                  </td>
                  <td className={`text-xs ${e.where === "blocked" ? "font-semibold text-rose-700" : "text-slate-600"}`}>{e.result}{e.blocked_reason && <div className="font-normal text-rose-600">{e.blocked_reason}</div>}</td>
                </tr>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-sm text-slate-400">Nothing here yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
