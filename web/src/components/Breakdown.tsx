import { useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, CheckCircle2, ListTree, MinusCircle, ThumbsDown, ThumbsUp, X, XCircle } from "lucide-react";
import { post, type Breakdown } from "../api";
import { money } from "../format";
import { Callout, Spinner } from "./ui";

function Totals({ title, rows, total, cur, tone }: { title: string; rows: Record<string, number>; total: number; cur: string; tone: "in" | "out" }) {
  const Icon = tone === "in" ? ArrowDownLeft : ArrowUpRight;
  const cls = tone === "in" ? "text-emerald-700" : "text-rose-700";
  return (
    <div className="rounded-2xl border border-slate-200 p-4">
      <div className={`mb-2 flex items-center gap-2 text-sm font-bold ${cls}`}><Icon className="h-4 w-4" />{title}</div>
      {Object.keys(rows).length === 0 && <div className="text-sm text-slate-400">Nothing</div>}
      {Object.entries(rows).map(([g, v]) => (
        <div key={g} className="flex justify-between py-0.5 text-sm"><span>{g}</span><span className="tabular-nums">{money(v, cur)}</span></div>
      ))}
      <div className={`mt-2 flex justify-between border-t border-slate-100 pt-2 text-sm font-bold ${cls}`}><span>Total</span><span className="tabular-nums">{money(total, cur)}</span></div>
    </div>
  );
}

/** Day-by-day money in and out for one plan, with the engine's reasons to accept it or not. */
export function BreakdownModal({ planId, title, cur, onClose }: { planId: string; title: string; cur: string; onClose: () => void }) {
  const [b, setB] = useState<Breakdown | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { post<Breakdown>("/api/breakdown", { plan_id: planId }).then(setB).catch((e) => setErr((e as Error).message)); }, [planId]);
  const tone = b?.verdict === "accept" ? "success" : b?.verdict === "reject" ? "critical" : "info";

  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 grid place-items-center bg-ink-950/50 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-6">
          <div className="flex gap-3">
            <div className="rounded-xl bg-brand-50 p-2 text-brand-700"><ListTree className="h-5 w-5" /></div>
            <div>
              <div className="label">Money breakdown</div>
              <h3 className="text-lg font-bold text-slate-900">{title}</h3>
            </div>
          </div>
          <button className="text-slate-400 hover:text-slate-700" aria-label="Close" onClick={onClose}><X className="h-5 w-5" /></button>
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {!b && !err && <div className="py-10"><Spinner text="Working out every payment…" /></div>}
          {err && <Callout tone="critical">{err}</Callout>}
          {b && <>
            <Callout tone={tone} title={b.summary} />

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4">
                <div className="mb-2 flex items-center gap-2 font-bold text-emerald-800"><ThumbsUp className="h-4 w-4" /> Why you would accept</div>
                {b.reasons_for.length === 0 && <p className="text-sm text-slate-500">No reason in favour.</p>}
                <ul className="space-y-1.5 text-sm text-slate-800">{b.reasons_for.map((t, i) => <li key={i} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />{t}</li>)}</ul>
              </div>
              <div className="rounded-2xl border border-rose-200 bg-rose-50/40 p-4">
                <div className="mb-2 flex items-center gap-2 font-bold text-rose-800"><ThumbsDown className="h-4 w-4" /> Why you would not</div>
                {b.reasons_against.length === 0 && <p className="text-sm text-slate-500">Nothing against it.</p>}
                <ul className="space-y-1.5 text-sm text-slate-800">{b.reasons_against.map((t, i) => <li key={i} className="flex gap-2"><XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />{t}</li>)}</ul>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <Totals title="Money coming in" rows={b.money_in} total={b.total_in} cur={cur} tone="in" />
              <Totals title="Money going out" rows={b.money_out} total={b.total_out} cur={cur} tone="out" />
              <div className="rounded-2xl border border-slate-200 p-4 text-sm">
                <div className="mb-2 font-bold text-slate-900">Your balance</div>
                {[["Cash today", b.opening], ["+ money in", b.total_in], ["− money out", -b.total_out]].map(([l, v]) => (
                  <div key={l as string} className="flex justify-between py-0.5"><span>{l}</span><span className="tabular-nums">{money(v as number, cur, { sign: l !== "Cash today" })}</span></div>
                ))}
                <div className="mt-2 flex justify-between border-t border-slate-100 pt-2 font-bold"><span>Cash at the end</span><span className="tabular-nums">{money(b.end, cur)}</span></div>
                <div className="mt-3 flex justify-between"><span>Lowest point (day {b.low_day})</span><span className="font-semibold tabular-nums">{money(b.low, cur)}</span></div>
                <div className="flex justify-between text-slate-500"><span>Your reserve</span><span className="tabular-nums">{money(b.reserve, cur)}</span></div>
                <div className={`mt-2 rounded-lg px-2 py-1 text-xs font-semibold ${b.headroom >= 0 ? "bg-emerald-100 text-emerald-900" : "bg-rose-100 text-rose-900"}`}>
                  {b.headroom >= 0 ? `${money(b.headroom, cur)} above the reserve at the tightest moment` : `${money(-b.headroom, cur)} short of the reserve on day ${b.low_day}`}
                </div>
              </div>
            </div>

            {b.plan_id !== "decline" && (
              <div className="rounded-2xl border border-slate-200 p-4 text-sm">
                <div className="mb-2 font-bold text-slate-900">Profit on this deal</div>
                <div className="grid gap-1 sm:grid-cols-4">
                  <div><div className="text-xs text-slate-500">Income from the deal</div><div className="font-semibold">{money(b.profit.income, cur)}</div></div>
                  <div><div className="text-xs text-slate-500">− Deal costs</div><div className="font-semibold">{money(b.profit.costs, cur)}</div></div>
                  <div><div className="text-xs text-slate-500">− Loan cost</div><div className="font-semibold">{money(b.profit.financing, cur)}</div></div>
                  <div><div className="text-xs text-slate-500">= Net profit</div><div className={`font-bold ${b.profit.net >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{money(b.profit.net, cur)}</div></div>
                </div>
              </div>
            )}

            <div>
              <div className="mb-2 font-bold text-slate-900">Every payment, in date order</div>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Day</th><th>What</th><th>Who</th><th className="text-right">In</th><th className="text-right">Out</th><th className="text-right">Cash after</th></tr></thead>
                <tbody>
                  <tr className="border-t border-slate-100"><td className="py-1.5 text-slate-500">0</td><td>Cash in the bank today</td><td /><td /><td /><td className="text-right font-semibold">{money(b.opening, cur)}</td></tr>
                  {b.rows.map((r, i) => (
                    <tr key={i} className={`border-t border-slate-100 ${r.below_reserve ? "bg-rose-50" : ""}`}>
                      <td className="py-1.5 text-slate-500">{r.day}</td>
                      <td>{r.label}<div className="text-xs text-slate-400">{r.group}</div>{r.note && <div className="text-xs text-sky-800">{r.note}</div>}</td>
                      <td className="text-xs text-slate-500">{r.counterparty}</td>
                      <td className="text-right text-emerald-700">{r.amount > 0 ? money(r.amount, cur) : ""}</td>
                      <td className="text-right text-rose-700">{r.amount < 0 ? money(-r.amount, cur) : ""}</td>
                      <td className={`text-right font-semibold ${r.below_reserve ? "text-rose-700" : ""}`}>{money(r.balance, cur)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 flex items-center gap-1 text-xs text-slate-500"><MinusCircle className="h-3 w-3" /> Red rows are below your reserve. On a day with money in and out, money out is counted first. Every number comes from the engine's day-by-day simulation.</p>
            </div>
          </>}
        </div>
      </div>
    </div>
  );
}
