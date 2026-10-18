import { useState } from "react";
import { ArrowRight, Bell, CalendarClock, CircleAlert, ListOrdered, OctagonX, Scale, ShieldAlert } from "lucide-react";
import type { Analysis } from "../api";
import { money } from "../format";
import { CashChart } from "./CashChart";
import { CashWalk } from "./CashWalk";
import { Callout, Card, LoadingButton, NextBar, Pill, SectionTitle, Segmented, Stat, Updating } from "./ui";

// How sure SolvOrder is about its recommendation (agent.py uncertainty level).
const LEVEL = { LOW: ["green", "Confident answer"], MEDIUM: ["amber", "Fairly confident"], HIGH: ["red", "Needs your judgement"] } as const;
const ALERT_TITLE: Record<string, string> = {
  reserve_breach: "Cash drops below your reserve", payment_before_receipt: "You pay before you are paid", offer_expiry: "A loan offer runs out",
  fragile_plan: "This plan breaks if you are paid late", constraint_violation: "A firm rule is broken", overdue_receivable: "Money owed to you is late",
  ineligible_offer: "A loan you can't use", provisional: "Result not final yet",
};

export function Verdict({ a, onConfirm, compact = false, updating = false }: { a: Analysis; onConfirm: (key: string) => void; compact?: boolean; updating?: boolean }) {
  const v = a.verdict;
  const [confirming, setConfirming] = useState<string | null>(null);
  const [tone, label] = LEVEL[v.level];
  const safe = a.plans.find((p) => p.id === v.winner);
  return (
    <div className="space-y-3">
      <div className={`card border-t-4 p-6 sm:p-7 ${v.level === "LOW" ? "border-t-emerald-500" : v.level === "MEDIUM" ? "border-t-amber-500" : "border-t-rose-500"}`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] font-semibold text-slate-500">{v.provisional ? "Recommendation (not final yet)" : "Recommendation"} · {a.case.business} · {a.case.order_ref} ({a.case.customer})</span>
          <Pill tone={tone}>{label}</Pill>
          {v.provisional && <Pill tone="amber">Waiting for you to confirm</Pill>}
        </div>
        <h2 className="mt-2 text-[22px] font-semibold leading-snug text-slate-900 md:text-[26px]">{v.headline}</h2>
        {!compact && <p className="mt-2 max-w-4xl text-sm leading-relaxed text-slate-600">{v.why}</p>}
        {safe && !compact && safe.id !== "decline" && (
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            <Pill tone="slate">Lowest cash {money(safe.min_balance, a.case.currency)} on day {safe.min_day}</Pill>
            <Pill tone="slate">Net profit {money(safe.net_margin, a.case.currency)}</Pill>
            {safe.tolerance && <Pill tone={safe.tolerance.kind === "fails_on_time" ? "red" : "green"}>Late payment: {safe.tolerance.label}</Pill>}
          </div>
        )}
      </div>
      {v.execution_blocks.length > 0 && (
        <Callout tone="critical" title="Payments are blocked by a fraud check">
          {v.execution_blocks.join("; ")}. Go back to <b>Check the facts</b> and record how you checked it with the supplier.
        </Callout>
      )}
      {v.provisional && (
        <Callout tone="warning" title="This result isn't final yet: please confirm these values">
          {v.provisional_fields.map((f) => (
            <div key={f.key} className="mt-2 flex flex-col gap-2 rounded-md border border-amber-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
              <div><b>{f.name}:</b> {f.value}<div className="text-xs">{f.question}</div></div>
              <LoadingButton className="btn-secondary shrink-0" loading={updating && confirming === f.key} loadingText="Confirming…"
                disabled={updating} onClick={() => { setConfirming(f.key); onConfirm(f.key); }}>Confirm</LoadingButton>
            </div>
          ))}
        </Callout>
      )}
      {v.no_plan_survives && (
        <Callout tone="critical" title="No plan works">
          No way of accepting this order keeps your reserve and every firm rule. The smallest change that would make it work:
          <ul className="mt-2 list-disc space-y-1 pl-5">{v.smallest_changes.map((c) => <li key={c}>{c}</li>)}</ul>
        </Callout>
      )}
    </div>
  );
}

export function RiskStep({ a, onConfirm, reading, setReading, onNext, updating }: {
  a: Analysis; onConfirm: (key: string) => void; reading: string | null; setReading: (r: string) => void; onNext: () => void;
  updating: boolean;
}) {
  const cur = a.case.currency;
  const buyer = a.case.role === "buyer";
  const asis = a.plans.find((p) => p.id === "accept-as-is")!;
  const best = a.plans.find((p) => p.id === a.verdict.winner)!;
  const decline = a.plans.find((p) => p.id === "decline")!;
  const chartPlans = [asis, ...(best.id !== "accept-as-is" && best.id !== "decline" ? [best] : []), decline];
  const readings = Object.entries(a.case.payment_readings);
  const alerts = [...a.alerts].sort((x, y) => ({ critical: 0, warning: 1, info: 2 }[x.severity] - { critical: 0, warning: 1, info: 2 }[y.severity]));

  return (
    <Updating active={updating}>
    <div className="space-y-6">
      <Verdict a={a} onConfirm={onConfirm} updating={updating} />
      <CashWalk a={a} />

      {readings.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={<CalendarClock className="h-5 w-5" />} title="When does the customer actually pay?"
            sub="The payment terms don't say when the count of days starts. Pick what the customer means; until you do, SolvOrder uses the later, safer date." />
          <Segmented value={reading ?? a.case.basis_used} onChange={setReading}
            options={readings.map(([k, d]) => ({ value: k, label: `${k === "after_order" ? "From order date" : "From delivery"}: day ${d}` }))} />
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Stat label={buyer ? "Income from the goods" : "Order value"} value={money(a.case.order_value, cur)} sub={`Gross profit ${money(a.case.gross_margin, cur)}`} />
        <Stat label="Cash today" value={money(a.case.opening_cash, cur)} sub={`Reserve ${money(a.case.reserve, cur)}`} />
        <Stat label={buyer ? "Income arrives" : "Customer pays"} value={`Day ${a.case.pay_day}`} sub={`${buyer ? "Goods arrive" : "Delivery"} day ${a.case.delivery_day}`} />
        <Stat label="Lowest cash if you accept as-is" value={money(asis.min_balance, cur)} tone={asis.reserve_ok ? "good" : "bad"}
          sub={asis.reserve_ok ? "Never below the reserve" : `Lowest point, on day ${asis.min_day}. Below the reserve from day ${asis.first_breach_day}`} />
        <Stat label="Cash you'd be short" value={a.gap.days ? money(a.gap.amount, cur) : "None"} tone={a.gap.days ? "bad" : "good"}
          sub={a.gap.days ? `Short for ${a.gap.days} days (day ${a.gap.from_day} to ${a.gap.until_day})` : "No extra cash needed"} />
      </div>

      <Card className="p-6">
        <SectionTitle icon={<Scale className="h-5 w-5" />} title="Your cash, day by day"
          sub="The shaded band is below your reserve. Compare accepting as-is, the recommended plan and declining." />
        <CashChart plans={chartPlans} reserve={a.case.reserve} opening={a.case.opening_cash} currency={cur} />
        <p className="mt-3 text-xs leading-relaxed text-slate-500">Balances change only on payment days. When money goes out and comes in on the same day, SolvOrder assumes it goes out first (the dip you see), so a same-day shortfall is never hidden.</p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <SectionTitle icon={<Bell className="h-5 w-5" />} title="What SolvOrder noticed" sub="Checked again every time you change something." />
          <div className="space-y-2">
            {alerts.map((al, i) => (
              <Callout key={i} tone={al.severity} title={ALERT_TITLE[al.rule] ?? al.rule}>{al.message}</Callout>
            ))}
            {alerts.length === 0 && a.flags.every((f) => f.resolved || f.severity === "info") && <Callout tone="success" title="Nothing to worry about">No warnings for this deal.</Callout>}
            {a.flags.filter((f) => !f.resolved && f.severity !== "info").map((f) => (
              <Callout key={f.code} tone={f.severity} title={<span className="flex items-center gap-2">{f.category === "fraud" ? <ShieldAlert className="h-4 w-4" /> : <CircleAlert className="h-4 w-4" />}{f.title}</span>}>{f.message}</Callout>
            ))}
          </div>
        </Card>
        <Card className="p-6">
          <SectionTitle icon={<ListOrdered className="h-5 w-5" />} title="Every payment in and out" sub="Your existing bills, payroll and income, plus what this order costs." />
          <div className="scroll-thin max-h-[420px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white text-left text-xs text-slate-500"><tr><th className="py-2">Day</th><th>Item</th><th className="text-right">Amount</th></tr></thead>
              <tbody>
                {a.case.movements.map((m, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="py-1.5 text-slate-500">{m.day}</td>
                    <td>{m.label}<div className="text-xs text-slate-400">{m.counterparty}{m.kind === "order_cost" ? " · order cost" : ""}</div>{m.note && <div className="text-xs text-sky-800">{m.note}</div>}</td>
                    <td className={`text-right font-medium ${m.amount < 0 ? "text-rose-700" : "text-emerald-700"}`}>{money(m.amount, cur, { sign: true })}</td>
                  </tr>
                ))}
                <tr className="border-t border-slate-100"><td className="py-1.5 text-slate-500">{a.case.pay_day}</td><td>{buyer ? "Income from the goods" : <>Customer pays {a.case.advance_received > 0 ? "the rest of " : ""}the order</>}<div className="text-xs text-slate-400">{a.case.customer}{a.case.advance_received > 0 && ` · ${money(a.case.advance_received, cur)} advance already received`}</div></td><td className="text-right font-medium text-emerald-700">{money(a.case.balance_due, cur, { sign: true })}</td></tr>
              </tbody>
            </table>
          </div>
          {a.case.assumptions.length > 0 && (
            <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs leading-relaxed text-slate-600"><b>What SolvOrder assumed:</b> {a.case.assumptions.join(" ")}</div>
          )}
        </Card>
      </div>

      {a.verdict.no_plan_survives && <Callout tone="critical" title="Before you continue"><OctagonX className="mr-1 inline h-4 w-4" /> The next screen shows why each plan fails.</Callout>}
      <NextBar note="Next, see every way to take this deal, side by side.">
        <button className="btn-primary px-6 py-3 text-base" onClick={onNext}>Compare options <ArrowRight className="h-5 w-5" /></button>
      </NextBar>
    </div>
    </Updating>
  );
}
