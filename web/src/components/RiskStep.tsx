import { useState } from "react";
import { ArrowRight, Bell, CalendarClock, CircleAlert, ListOrdered, OctagonX, Scale, ShieldAlert } from "lucide-react";
import type { Analysis } from "../api";
import { money } from "../format";
import { CashChart } from "./CashChart";
import { CashWalk } from "./CashWalk";
import { Callout, Card, LoadingButton, Pill, SectionTitle, Segmented, Stat, Updating } from "./ui";

const LEVEL = { LOW: ["green", "Low uncertainty"], MEDIUM: ["amber", "Medium uncertainty"], HIGH: ["red", "High uncertainty"] } as const;
const ALERT_TITLE: Record<string, string> = {
  reserve_breach: "Reserve breach", payment_before_receipt: "Payment before receipt", offer_expiry: "Offer expiry",
  fragile_plan: "Fragile plan", constraint_violation: "Hard constraint", overdue_receivable: "Overdue receivable",
  ineligible_offer: "Ineligible offer", provisional: "Provisional result",
};

export function Verdict({ a, onConfirm, compact = false, updating = false }: { a: Analysis; onConfirm: (key: string) => void; compact?: boolean; updating?: boolean }) {
  const v = a.verdict;
  const [confirming, setConfirming] = useState<string | null>(null);
  const [tone, label] = LEVEL[v.level];
  const safe = a.plans.find((p) => p.id === v.winner);
  return (
    <div className="space-y-3">
      <div className={`rounded-3xl border-l-8 bg-white p-6 shadow-sm ${v.level === "LOW" ? "border-emerald-500" : v.level === "MEDIUM" ? "border-amber-500" : "border-rose-500"}`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="label">{v.provisional ? "Provisional decision" : "Decision"} · {a.case.business} · {a.case.order_ref} ({a.case.customer})</span>
          <Pill tone={tone}>{label}</Pill>
          {v.provisional && <Pill tone="amber">Waiting for your confirmation</Pill>}
        </div>
        <div className="mt-2 text-xl font-bold leading-snug text-slate-900 md:text-2xl">{v.headline}</div>
        {!compact && <p className="mt-2 text-sm text-slate-600">{v.why}</p>}
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
          {v.execution_blocks.join("; ")}. Go to <b>Check the facts</b> and record how you verified it with the supplier.
        </Callout>
      )}
      {v.provisional && (
        <Callout tone="warning" title="This result is provisional">
          {v.provisional_fields.map((f) => (
            <div key={f.key} className="mt-2 flex flex-col gap-2 rounded-lg bg-white/60 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div><b>{f.name}:</b> {f.value}<div className="text-xs">{f.question}</div></div>
              <LoadingButton className="btn-secondary shrink-0" loading={updating && confirming === f.key} loadingText="Confirming…"
                disabled={updating} onClick={() => { setConfirming(f.key); onConfirm(f.key); }}>Confirm</LoadingButton>
            </div>
          ))}
        </Callout>
      )}
      {v.no_plan_survives && (
        <Callout tone="critical" title="No plan survives">
          No way of accepting this order keeps your reserve and every hard constraint. Smallest change that would make it work:
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
            sub="The payment terms don't say when the days start. Pick the reading the customer means; SolvOrder uses the later, safer one until you choose." />
          <Segmented value={reading ?? a.case.basis_used} onChange={setReading}
            options={readings.map(([k, d]) => ({ value: k, label: `${k === "after_order" ? "From order date" : "From delivery"}: day ${d}` }))} />
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Stat label="Order value" value={money(a.case.order_value, cur)} sub={`Gross profit ${money(a.case.gross_margin, cur)}`} />
        <Stat label="Cash today" value={money(a.case.opening_cash, cur)} sub={`Reserve ${money(a.case.reserve, cur)}`} />
        <Stat label="Customer pays" value={`Day ${a.case.pay_day}`} sub={`Delivery day ${a.case.delivery_day}`} />
        <Stat label="If accepted as-is" value={money(asis.min_balance, cur)} tone={asis.reserve_ok ? "good" : "bad"}
          sub={asis.reserve_ok ? "never below the reserve" : `lowest, day ${asis.min_day} · first breach day ${asis.first_breach_day}`} />
        <Stat label="Funding gap" value={a.gap.days ? money(a.gap.amount, cur) : "None"} tone={a.gap.days ? "bad" : "good"}
          sub={a.gap.days ? `short for ${a.gap.days} days (day ${a.gap.from_day}–${a.gap.until_day})` : "no extra cash needed"} />
      </div>

      <Card className="p-6">
        <SectionTitle icon={<Scale className="h-5 w-5" />} title="Your cash, day by day"
          sub="Red zone = below your reserve. Compare accepting as-is, the recommended plan and declining." />
        <CashChart plans={chartPlans} reserve={a.case.reserve} opening={a.case.opening_cash} currency={cur} />
        <p className="mt-2 text-xs text-slate-500">Balances change only on payment days. When money goes out and comes in on the same day, SolvOrder assumes it goes out first (the dip you see), so a same-day shortfall is never hidden.</p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <SectionTitle icon={<Bell className="h-5 w-5" />} title="What SolvOrder noticed" sub="Alerts are re-checked on every change." />
          <div className="space-y-2">
            {alerts.map((al, i) => (
              <Callout key={i} tone={al.severity} title={ALERT_TITLE[al.rule] ?? al.rule}>{al.message}</Callout>
            ))}
            {a.flags.filter((f) => !f.resolved && f.severity !== "info").map((f) => (
              <Callout key={f.code} tone={f.severity} title={<span className="flex items-center gap-2">{f.category === "fraud" ? <ShieldAlert className="h-4 w-4" /> : <CircleAlert className="h-4 w-4" />}{f.title}</span>}>{f.message}</Callout>
            ))}
          </div>
        </Card>
        <Card className="p-6">
          <SectionTitle icon={<ListOrdered className="h-5 w-5" />} title="Every cash movement" sub="Existing bills, payroll and receipts, plus what the order costs." />
          <div className="max-h-[420px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white text-left text-xs text-slate-500"><tr><th className="py-2">Day</th><th>Item</th><th className="text-right">Amount</th></tr></thead>
              <tbody>
                {a.case.movements.map((m, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="py-1.5 text-slate-500">{m.day}</td>
                    <td>{m.label}<div className="text-xs text-slate-400">{m.counterparty}{m.kind === "order_cost" ? " · order cost" : ""}</div></td>
                    <td className={`text-right font-medium ${m.amount < 0 ? "text-rose-700" : "text-emerald-700"}`}>{money(m.amount, cur, { sign: true })}</td>
                  </tr>
                ))}
                <tr className="border-t border-slate-100"><td className="py-1.5 text-slate-500">{a.case.pay_day}</td><td>Customer pays {a.case.advance_received > 0 ? "the rest of " : ""}the order<div className="text-xs text-slate-400">{a.case.customer}{a.case.advance_received > 0 && ` · ${money(a.case.advance_received, cur)} advance already received`}</div></td><td className="text-right font-medium text-emerald-700">{money(a.case.balance_due, cur, { sign: true })}</td></tr>
              </tbody>
            </table>
          </div>
          {a.case.assumptions.length > 0 && (
            <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600"><b>Assumptions:</b> {a.case.assumptions.join(" ")}</div>
          )}
        </Card>
      </div>

      {a.verdict.no_plan_survives && <Callout tone="critical" title="Before you continue"><OctagonX className="mr-1 inline h-4 w-4" /> The options screen still shows why each plan fails.</Callout>}
      <div className="flex justify-end">
        <button className="btn-primary px-6 py-3 text-base" onClick={onNext}>Compare options <ArrowRight className="h-5 w-5" /></button>
      </div>
    </div>
    </Updating>
  );
}
