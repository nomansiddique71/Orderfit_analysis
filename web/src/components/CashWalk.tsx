import { useState } from "react";
import { Minus, Plus, Equal, Route } from "lucide-react";
import type { Analysis, CashWalk as Walk } from "../api";
import { money, words } from "../format";
import { Card, SectionTitle, Segmented } from "./ui";

/** One plan's path to its lowest point, as a short sum the owner can check by hand. */
function WalkColumn({ w, cur, title, tone }: { w: Walk; cur: string; title: string; tone: "bad" | "good" }) {
  const outs = Object.entries(w.out_until_low);
  const ins = Object.entries(w.in_until_low);
  const safe = w.headroom >= 0;
  const Line = ({ icon, label, value, cls = "" }: { icon: React.ReactNode; label: string; value: string; cls?: string }) => (
    <div className={`flex items-center justify-between gap-3 py-1.5 text-sm ${cls}`}>
      <span className="flex items-center gap-2">{icon}{label}</span><span className="font-semibold tabular-nums">{value}</span>
    </div>
  );
  return (
    <div className={`rounded-lg border p-5 ${tone === "good" ? "border-emerald-200 bg-emerald-50/50" : "border-rose-200 bg-rose-50/30"}`}>
      <div className="label">{title}</div>
      <div className="mb-3 font-semibold text-slate-900">{w.plan}</div>
      <Line icon={<span className="h-4 w-4" />} label="Cash in the bank today" value={money(w.opening, cur)} />
      {outs.length > 0 && <div className="mt-2 text-xs font-semibold text-slate-500">Paid out up to day {w.low_day}</div>}
      {outs.map(([g, v]) => <Line key={g} icon={<Minus className="h-4 w-4 text-rose-600" />} label={g} value={money(v, cur)} cls="text-rose-800" />)}
      {ins.length > 0 && <div className="mt-2 text-xs font-semibold text-slate-500">Received up to day {w.low_day}</div>}
      {ins.map(([g, v]) => <Line key={g} icon={<Plus className="h-4 w-4 text-emerald-600" />} label={g} value={money(v, cur)} cls="text-emerald-800" />)}
      <div className="mt-2 border-t border-slate-200 pt-2">
        <Line icon={<Equal className="h-4 w-4" />} label={`Lowest cash (day ${w.low_day})`} value={money(w.low, cur)} cls="text-base font-bold" />
        <Line icon={<span className="h-4 w-4" />} label="Your safety reserve" value={money(w.reserve, cur)} cls="text-slate-500" />
        <div className={`mt-2 rounded-md px-3 py-2 text-sm font-semibold ${safe ? "bg-emerald-100 text-emerald-900" : "bg-rose-100 text-rose-900"}`}>
          <span className="sr-only">{safe ? "Safe: " : "Problem: "}</span>
          {safe ? `${money(w.headroom, cur)} above the reserve at the tightest moment` : `${money(-w.headroom, cur)} short of the reserve on day ${w.low_day}`}
        </div>
      </div>
    </div>
  );
}

export function CashWalk({ a }: { a: Analysis }) {
  const cur = a.case.currency;
  const { asis, recommended } = a.walk;
  const same = a.verdict.winner === "accept-as-is";
  const declined = a.verdict.winner === "decline";
  const [ledger, setLedger] = useState<"asis" | "recommended">(same ? "asis" : "recommended");
  const rows = a.walk[ledger].rows;
  const paid = a.case.advance_received > 0;
  const w = words(a.case.role);
  const buyer = a.case.role === "buyer";

  const story = [
    `You have ${money(asis.opening, cur)} today and promised yourself never to go below ${money(asis.reserve, cur)}.`,
    `If you accept as-is, you pay ${Object.entries(asis.out_until_low).map(([g, v]) => `${g.toLowerCase()} ${money(v, cur)}`).join(", ")} before day ${asis.low_day}`
      + (buyer
        ? (a.case.order_value > 0 ? `, and the income from the goods (${money(a.case.order_value, cur)}) only arrives on day ${a.case.pay_day}` : ", and you expect no income back from the goods within the plan")
        : `, but the customer only pays ${money(a.case.balance_due, cur)} on day ${a.case.pay_day}`)
      + (paid ? ` (they already paid ${money(a.case.advance_received, cur)} in advance, which is in today's cash)` : "") + ".",
    asis.headroom >= 0
      ? `Even at the tightest moment (day ${asis.low_day}) you keep ${money(asis.headroom, cur)} above the reserve, so the ${w.deal} is affordable as it is.`
      : `At the tightest moment (day ${asis.low_day}) cash would be ${money(asis.low, cur)}, ${money(-asis.headroom, cur)} below your reserve. That is why SolvOrder does not accept it as-is.`,
    same ? "" : declined
      ? "No plan keeps you above the reserve, so SolvOrder recommends declining (or changing the terms shown on the options screen)."
      : `With "${recommended.plan}", the tightest moment is ${money(recommended.low, cur)} on day ${recommended.low_day}, ${money(recommended.headroom, cur)} above the reserve, so you can take the deal this way.`,
  ].filter(Boolean);

  return (
    <Card className="p-6">
      <SectionTitle icon={<Route className="h-5 w-5" />} title="How SolvOrder reached this decision"
        sub={`Cash today, minus payroll, bills and the ${w.deal}'s costs, plus what comes in, gives your lowest cash point. That point is compared with your reserve.`} />
      <ol className="mb-5 max-w-4xl space-y-2 text-sm leading-relaxed text-slate-700">
        {story.map((t, i) => <li key={i} className="flex gap-2"><span className="mt-px grid h-5 w-5 shrink-0 place-items-center rounded-full border border-brand-200 bg-brand-50 text-[11px] font-bold text-brand-700">{i + 1}</span>{t}</li>)}
      </ol>
      <div className={`grid gap-4 ${same ? "" : "md:grid-cols-2"}`}>
        <WalkColumn w={asis} cur={cur} title={`If you accept the ${w.deal} as it is`} tone={asis.headroom >= 0 ? "good" : "bad"} />
        {!same && <WalkColumn w={recommended} cur={cur} title={declined ? "If you decline" : "With the recommended plan"} tone={recommended.headroom >= 0 ? "good" : "bad"} />}
      </div>
      <details className="mt-5">
        <summary className="cursor-pointer text-sm font-semibold text-brand-700 hover:underline">Show every payment with the balance after it</summary>
        {!same && <div className="mt-3"><Segmented value={ledger} onChange={setLedger} options={[{ value: "asis", label: "Accept as-is" }, { value: "recommended", label: "Recommended plan" }]} /></div>}
        <div className="scroll-thin overflow-x-auto"><table className="mt-3 w-full min-w-[520px] text-sm">
          <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Day</th><th>What</th><th className="text-right">Amount</th><th className="text-right">Cash after</th></tr></thead>
          <tbody>
            <tr className="border-t border-slate-100"><td className="py-1.5 text-slate-500">0</td><td>Cash today</td><td /><td className="text-right font-semibold">{money(a.walk[ledger].opening, cur)}</td></tr>
            {rows.map((r, i) => (
              <tr key={i} className={`border-t border-slate-100 ${r.below_reserve ? "bg-rose-50" : ""}`}>
                <td className="py-1.5 text-slate-500">{r.day}</td>
                <td>{r.label}<div className="text-xs text-slate-400">{r.group}</div>{r.note && <div className="text-xs text-sky-800">{r.note}</div>}</td>
                <td className={`text-right ${r.amount < 0 ? "text-rose-700" : "text-emerald-700"}`}>{money(r.amount, cur, { sign: true })}</td>
                <td className={`text-right font-semibold ${r.below_reserve ? "text-rose-700" : ""}`}>{money(r.balance, cur)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
        <p className="mt-2 text-xs text-slate-500">Red rows are below your {money(a.case.reserve, cur)} reserve. On a day with money in and out, money out is counted first.</p>
      </details>
    </Card>
  );
}
