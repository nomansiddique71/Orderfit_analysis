import { useEffect, useState } from "react";
import { ArrowRight, Banknote, Bot, CheckCircle2, ListTree, FlaskConical, Grid3x3, HandCoins, MessageSquare, Scale, Send, SlidersHorizontal, XCircle } from "lucide-react";
import { post, type Analysis, type Plan, type ScenarioResult } from "../api";
import { money, planTitle, words } from "../format";
import { BreakdownModal } from "./Breakdown";
import { CashChart } from "./CashChart";
import { Callout, Card, LoadingButton, Pill, SectionTitle, Segmented, Spinner, Updating } from "./ui";

export const PRIORITIES = [
  { value: "maximize_margin", label: "Highest profit", hint: "Most net profit among safe plans" },
  { value: "minimize_financing_cost", label: "Least borrowing", hint: "Avoid loan costs" },
  { value: "avoid_customer_consent", label: "No favours from customer", hint: "Don't depend on the customer agreeing to pay early" },
  { value: "most_robust", label: "Safest if paid late", hint: "Survive the longest customer delay" },
];

export type Choice = { id: string; override: boolean } | null;

function OptionCard({ p, a, best, chosen, onChoose, onBreakdown }: { p: Plan; a: Analysis; best: boolean; chosen: boolean; onChoose: () => void; onBreakdown: () => void }) {
  const cur = a.case.currency;
  return (
    <div className={`flex h-full flex-col rounded-2xl border-2 bg-white p-5 ${chosen ? "border-violet-500 shadow-lg shadow-violet-600/10" : best ? "border-brand-500 shadow-lg shadow-brand-600/10" : "border-slate-200"}`}>
      <div className="mb-1 flex flex-wrap gap-2">
        {best && <span className="label text-brand-700">★ Recommended</span>}
        {chosen && <span className="label text-violet-700">✓ Your choice</span>}
      </div>
      <div className="text-base font-bold leading-snug text-slate-900">{planTitle(p, cur)}</div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {p.feasible ? <Pill tone="green"><CheckCircle2 className="h-3 w-3" /> Keeps reserve</Pill> : <Pill tone="red"><XCircle className="h-3 w-3" /> {p.violations[0] ?? `Breaks reserve day ${p.first_breach_day}`}</Pill>}
        {p.feasible && (p.robust ? <Pill tone="green">Survives late payment</Pill> : <Pill tone="amber">Fragile if paid late</Pill>)}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
        <dt className="text-slate-500">Lowest cash</dt><dd className="text-right font-semibold">{money(p.min_balance, cur)} <span className="text-xs font-normal text-slate-400">d{p.min_day}</span></dd>
        <dt className="text-slate-500">Financing cost</dt><dd className="text-right font-semibold">{money(p.financing_cost, cur)}</dd>
        <dt className="text-slate-500">Net profit</dt><dd className="text-right font-semibold">{money(p.net_margin, cur)}</dd>
        <dt className="text-slate-500">Paid late, still OK?</dt><dd className="text-right text-xs font-semibold">{p.tolerance?.label ?? "—"}</dd>
      </dl>
      <div className="mt-auto pt-3 text-xs text-slate-500">Needs agreement from: {p.consents.length ? p.consents.join(" and ") : "nobody"}</div>
      <button className="mt-3 flex w-full items-center justify-center gap-1 rounded-xl border border-dashed border-brand-300 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50" onClick={onBreakdown}>
        <ListTree className="h-4 w-4" /> See the money breakdown
      </button>
      <button className={`${chosen ? "btn-primary" : "btn-secondary"} mt-2 w-full`} onClick={onChoose}>
        {chosen ? "Chosen: go to approval" : best ? "Go with the recommendation" : "Choose this plan instead"}
      </button>
    </div>
  );
}

/** No way of accepting keeps the reserve: the one recommendation is to decline, with every option's failure. */
function DeclineCard({ a, onBreakdown, onChoose }: { a: Analysis; onBreakdown: () => void; onChoose: () => void }) {
  const d = a.decline!;
  const w = words(a.case.role);
  const who = a.case.role === "buyer" ? "supplier" : "customer";
  return (
    <Card className="border-2 border-rose-300 p-6">
      <div className="label text-rose-700">★ Recommended: the only safe choice</div>
      <h3 className="mt-1 text-xl font-extrabold text-slate-900">Decline the {w.deal}</h3>
      <p className="mt-1 text-sm text-slate-600">No way of accepting this {w.deal} keeps your cash above your {money(a.case.reserve, a.case.currency)} reserve. SolvOrder tried every option:</p>
      <ul className="mt-3 space-y-2">
        {d.tried.map((t) => (
          <li key={t.option} className="flex gap-2 rounded-xl bg-rose-50 px-3 py-2 text-sm">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
            <span><b>{t.option}</b>{t.option !== "Accept as it is" && <span className="text-slate-500"> (best version: {t.best_plan.replace("Accept: ", "")})</span>}: {t.why}.</span>
          </li>
        ))}
      </ul>
      {d.ask && <Callout tone="info" title={`What would let you accept: ask your ${who}`}>The engine checked it: the {w.deal} works if {d.ask}. The decline mail offers this.</Callout>}
      {d.owner_changes.length > 0 && <details className="mt-3 text-sm"><summary className="cursor-pointer font-semibold text-slate-700">Changes only you can make</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600">{d.owner_changes.map((c) => <li key={c}>{c}</li>)}</ul></details>}
      <div className="mt-4 flex flex-wrap gap-3">
        <button className="btn-secondary" onClick={onBreakdown}><ListTree className="h-4 w-4" /> See the full breakdown</button>
        <button className="btn-danger" onClick={onChoose}>Decline and write to my {who} <ArrowRight className="h-4 w-4" /></button>
      </div>
    </Card>
  );
}

export function OptionsStep({ a, controls, setControls, onNext, updating, choice, onChoose }: {
  a: Analysis; updating: boolean; choice: Choice; onChoose: (c: Choice) => void;
  controls: { priority: string; stress: number; payDay: number | null; tie: string | null };
  setControls: (c: Partial<{ priority: string; stress: number; payDay: number | null; tie: string | null }>) => void;
  onNext: () => void;
}) {
  const cur = a.case.currency;
  const w = words(a.case.role);
  const winner = a.plans.find((p) => p.id === a.verdict.winner)!;
  const feasible = a.plans.filter((p) => p.feasible && p.id !== winner.id && p.id !== "decline");
  const failing = a.plans.filter((p) => !p.feasible);
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? feasible : feasible.slice(0, 5);
  const [bd, setBd] = useState<Plan | null>(null);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <SectionTitle icon={<SlidersHorizontal className="h-5 w-5" />} title="Tell SolvOrder what matters to you"
          sub="The recommendation updates instantly. Only plans that keep your reserve can be recommended." />
        <div className="grid gap-5 lg:grid-cols-3">
          <div><div className="label mb-2">What matters most?</div>
            <Segmented value={controls.priority} options={PRIORITIES} onChange={(v) => setControls({ priority: v, tie: null })} /></div>
          <div><div className="label mb-2">How late might {w.payer} {w.pays === "pays" ? "pay" : "arrive"}?</div>
            <Segmented value={controls.stress} options={[15, 30, 60, 90].map((d) => ({ value: d, label: `${d} days` }))} onChange={(v) => setControls({ stress: v })} /></div>
          <div><div className="label mb-2">What if {w.payer} {w.pays} on day… <b className="text-slate-900">{controls.payDay ?? a.case.pay_day}</b></div>
            <input type="range" min={Math.max(0, a.case.delivery_day)} max={Math.max(120, a.case.document_pay_day + 30)} value={controls.payDay ?? a.case.pay_day}
              onChange={(e) => setControls({ payDay: Number(e.target.value) })} className="w-full accent-teal-600" />
            <div className="flex justify-between text-xs text-slate-500"><span>Documents say day {a.case.document_pay_day}</span>
              {controls.payDay !== null && <button className="font-semibold text-brand-700" onClick={() => setControls({ payDay: null })}>reset</button>}</div></div>
        </div>
      </Card>

      <Updating active={updating}>
      <div className="space-y-6">
      {a.verdict.near_tie && (
        <Callout tone="warning" title="Two plans are almost equal: your call">
          <div className="mt-2 grid gap-3 md:grid-cols-2">
            {a.verdict.near_tie.map((t) => {
              const p = a.plans.find((x) => x.id === t.id)!;
              const chosen = winner.id === t.id;
              return (
                <div key={t.id} className={`rounded-xl border bg-white p-3 ${chosen ? "border-brand-500" : "border-amber-200"}`}>
                  <div className="font-semibold text-slate-900">{planTitle(p, cur)}</div>
                  <div className="text-xs text-slate-600">Better on: {t.strengths.join("; ") || "nothing"}</div>
                  <LoadingButton className={chosen ? "btn-primary mt-2" : "btn-secondary mt-2"} loading={updating && controls.tie === t.id && !chosen}
                    loadingText="Applying…" onClick={() => setControls({ tie: t.id })}>{chosen ? "Chosen" : "Prefer this"}</LoadingButton>
                </div>
              );
            })}
          </div>
        </Callout>
      )}
      {a.verdict.priority_conflict && <Callout tone="critical" title="Your priority conflicts with every safe plan">SolvOrder will not recommend a plan that breaks your priority. Choose a different priority, or decline.</Callout>}

      {a.decline && <DeclineCard a={a} onBreakdown={() => setBd(winner)} onChoose={() => onChoose({ id: "decline", override: false })} />}
      <section className={a.decline ? "hidden" : ""}>
        <SectionTitle icon={<Scale className="h-5 w-5" />} title="Your options, compared" sub="SolvOrder recommends one, but the choice is yours: pick any safe plan. Every number comes from the engine's day-by-day simulation." />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <OptionCard p={winner} a={a} best chosen={choice?.id === winner.id} onChoose={() => onChoose({ id: winner.id, override: false })} onBreakdown={() => setBd(winner)} />
          {shown.map((p) => <OptionCard key={p.id} p={p} a={a} best={false} chosen={choice?.id === p.id} onChoose={() => onChoose({ id: p.id, override: false })} onBreakdown={() => setBd(p)} />)}
        </div>
        {feasible.length > 5 && <button className="mt-3 text-sm font-semibold text-brand-700" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${feasible.length + 1} safe plans`}</button>}
        {failing.length > 0 && (
          <details className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
            <summary className="cursor-pointer text-sm font-semibold text-slate-700">{failing.length} plans that don't work, and why</summary>
            <ul className="mt-3 space-y-1 text-sm">
              {failing.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 border-t border-slate-100 pt-1">
                  <span>{planTitle(p, cur)}</span>
                  <span className="flex items-center gap-3 text-right text-rose-700">{p.violations.join(" ") || `cash below reserve from day ${p.first_breach_day} (low ${money(p.min_balance, cur)})`}
                    <button className="chip shrink-0 bg-slate-100 text-slate-700 hover:bg-slate-200" onClick={() => setBd(p)}>Breakdown</button>
                    {p.id !== "decline" && p.violations.length === 0 && !p.reserve_ok &&
                      <button className="chip shrink-0 bg-rose-100 text-rose-800 hover:bg-rose-200" onClick={() => onChoose({ id: p.id, override: true })}>Choose anyway (override)</button>}</span>
                </li>))}
            </ul>
          </details>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-6">
          <SectionTitle icon={<Grid3x3 className="h-5 w-5" />} title={`Stress test: what if ${w.paysLate}?`} sub={`✓ = your reserve still holds if ${w.payer} ${w.pays} that many days late.`} />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="py-2">Plan</th>{[15, 30, 60, 90].map((d) => <th key={d} className="text-center">+{d}d</th>)}</tr></thead>
              <tbody>
                {[winner, ...feasible.slice(0, 5), ...a.plans.filter((p) => p.id === "accept-as-is" || p.id === "decline")].filter((p, i, arr) => arr.findIndex((q) => q.id === p.id) === i).map((p) => (
                  <tr key={p.id} className="border-t border-slate-100">
                    <td className="py-2 pr-2">{p.recommended && "★ "}{planTitle(p, cur)}<div className="text-xs text-slate-400">{p.tolerance?.label}</div></td>
                    {[15, 30, 60, 90].map((d) => <td key={d} className="text-center">{p.tolerance?.survives[String(d)] ? <span className="text-emerald-600">✓</span> : <span className="text-rose-500">✗</span>}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card className="p-6">
          <SectionTitle icon={<HandCoins className="h-5 w-5" />} title="If you need a loan: the smallest safe amount" sub="Sized from each lender's own terms. The AI cannot change rates or fees." />
          {a.min_safe_loans.length === 0 && <p className="text-sm text-slate-500">No lender on file offers a flexible amount.</p>}
          <div className="space-y-3">
            {a.min_safe_loans.map((l) => (
              <div key={l.offer} className="rounded-xl border border-slate-200 p-4">
                <div className="flex items-center gap-2 font-semibold"><Banknote className="h-4 w-4 text-brand-700" />{l.lender}<span className="text-xs font-normal text-slate-500">{l.terms}</span></div>
                {l.principal !== null
                  ? <p className="mt-1 text-sm">Borrow <b>{money(l.principal, cur)}</b> (cost <b>{money(l.cost, cur)}</b>). That keeps your reserve even if {w.payer} {w.pays} {controls.stress} days late.</p>
                  : <p className="mt-1 text-sm text-rose-700">No amount between {money(l.min, cur)} and {money(l.max, cur)} survives a {controls.stress}-day late payment.</p>}
              </div>
            ))}
            {a.offers.filter((o) => o.ineligible).map((o) => <div key={o.id} className="text-xs text-slate-500">Not an option: {o.lender}: {o.ineligible}.</div>)}
          </div>
          {a.sensitivity.rows.length > 0 && (
            <div className="mt-5">
              <div className="label mb-1">Does the answer change with the payment date?</div>
              <p className="text-sm text-slate-600">{a.sensitivity.flip_day ? <>Yes. The best plan changes if {w.payer} {w.pays} on <b>day {a.sensitivity.flip_day}</b> or later.</> : "No: the same plan wins for every payment day from 40 to 90."}</p>
            </div>
          )}
        </Card>
      </div>

      <Scenarios a={a} />
      </div>
      </Updating>
      <AskAgent a={a} />

      <div className="flex justify-end">
        <button className="btn-primary px-6 py-3 text-base" onClick={onNext}>Approve a plan <ArrowRight className="h-5 w-5" /></button>
      </div>
      {bd && <BreakdownModal planId={bd.id} title={planTitle(bd, cur)} cur={cur} onClose={() => setBd(null)} />}
    </div>
  );
}

function Scenarios({ a }: { a: Analysis }) {
  const cur = a.case.currency;
  const [planId, setPlanId] = useState(a.verdict.winner === "decline" ? "accept-as-is" : a.verdict.winner);
  const [p, setP] = useState({ partial_pct: 70, price_pct: 10, supplier_delay: 14 });
  const [res, setRes] = useState<ScenarioResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      post<ScenarioResult>("/api/scenarios", { plan_id: planId, ...p })
        .then((r) => { setRes(r); setErr(null); })
        .catch((e) => setErr((e as Error).message))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(t);
  }, [planId, p, a]);
  const plan = a.plans.find((x) => x.id === planId);
  return (
    <Card className="p-6">
      <SectionTitle icon={<FlaskConical className="h-5 w-5" />} title="What if things go wrong?" sub="Re-run a plan with partial payment, no payment, a supplier price rise or a late supplier." />
      <div className="grid gap-3 md:grid-cols-[2fr_1fr_1fr_1fr]">
        <select className="input" value={planId} onChange={(e) => setPlanId(e.target.value)}>
          {a.plans.filter((x) => x.id !== "decline").map((x) => <option key={x.id} value={x.id}>{x.recommended ? "★ " : ""}{planTitle(x, cur)}</option>)}
        </select>
        <label className="text-xs text-slate-500">Customer pays only %<input type="number" className="input mt-1" min={0} max={100} value={p.partial_pct} onChange={(e) => setP({ ...p, partial_pct: Number(e.target.value) })} /></label>
        <label className="text-xs text-slate-500">Supplier price rise %<input type="number" className="input mt-1" min={0} max={100} value={p.price_pct} onChange={(e) => setP({ ...p, price_pct: Number(e.target.value) })} /></label>
        <label className="text-xs text-slate-500">Supplier late (days)<input type="number" className="input mt-1" min={0} max={90} value={p.supplier_delay} onChange={(e) => setP({ ...p, supplier_delay: Number(e.target.value) })} /></label>
      </div>
      {err && <Callout tone="warning">{err}</Callout>}
      {!res ? <div className="mt-4"><Spinner text="Running scenarios…" /></div> : (
        <Updating active={loading}>
        <div className="mt-4 grid gap-4 lg:grid-cols-[2fr_1fr]">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500"><tr><th className="py-2">Scenario</th><th>Lowest cash</th><th>Reserve</th><th className="text-right">Order cash result</th></tr></thead>
            <tbody>
              {res.outcomes.map((o) => (
                <tr key={o.key} className="border-t border-slate-100">
                  <td className="py-2">{o.label}{o.penalty > 0 && <div className="text-xs text-amber-700">late-delivery penalty {money(o.penalty, cur)}</div>}{o.violations.length > 0 && <div className="text-xs text-rose-700">{o.violations.join(" ")}</div>}</td>
                  <td>{money(o.min_balance, cur)} <span className="text-xs text-slate-400">d{o.min_day}</span></td>
                  <td>{o.reserve_ok ? <Pill tone="green">kept</Pill> : <Pill tone="red">breached d{o.first_breach_day}</Pill>}</td>
                  <td className={`text-right font-semibold ${o.order_net < 0 ? "text-rose-700" : "text-slate-800"}`}>{money(o.order_net, cur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="space-y-3">
            <div className="rounded-xl bg-rose-50 p-4"><div className="label text-rose-700">Maximum loss if never paid</div><div className="text-2xl font-bold text-rose-700">{money(res.max_loss, cur)}</div><div className="text-xs text-rose-800">everything spent on the order, less any advance</div></div>
            {res.money_at_risk.length > 0 && (
              <div className="rounded-xl border border-slate-200 p-3 text-sm"><div className="label mb-1">If the customer cancels after day…</div>
                {res.money_at_risk.map((m) => <div key={m.day} className="flex justify-between"><span>day {m.day}</span><span className="font-semibold">{money(m.amount, cur)} at risk</span></div>)}</div>
            )}
          </div>
        </div>
        </Updating>
      )}
      {plan && <div className="mt-4"><CashChart plans={[plan]} reserve={a.case.reserve} opening={a.case.opening_cash} currency={cur} height={220} /></div>}
    </Card>
  );
}

function AskAgent({ a }: { a: Analysis }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<"ask" | "explain" | null>(null);
  const [answers, setAnswers] = useState<{ q: string; text: string; source: string }[]>([]);
  async function ask(question: string, explain = false) {
    if (explain === false && !question.trim()) return;
    setBusy(explain ? "explain" : "ask");
    try {
      const r = explain ? await post<{ text: string; source: string }>("/api/ai/explain")
        : await post<{ text: string; source: string }>("/api/ai/ask", { question });
      setAnswers([{ q: explain ? "Explain this decision in plain language" : question, ...r }, ...answers]);
      setQ("");
    } catch (e) { setAnswers([{ q: question, text: (e as Error).message, source: "error" }, ...answers]); }
    finally { setBusy(null); }
  }
  const suggestions = ["Why is this plan recommended?", "What happens if the customer pays 30 days late?", "How much does financing cost me?"];
  return (
    <Card className="p-6">
      <SectionTitle icon={<MessageSquare className="h-5 w-5" />} title="Ask SolvOrder"
        sub={a.ai.gemini ? "Answered by Google Gemini, using only the engine's verified numbers." : "Gemini is not configured. Answers fall back to a template."}
        right={<LoadingButton className="btn-secondary" loading={busy === "explain"} loadingText="Explaining…" disabled={!!busy} onClick={() => ask("", true)}><Bot className="h-4 w-4" /> Explain the decision</LoadingButton>} />
      <div className="flex gap-2">
        <input className="input" value={q} maxLength={500} disabled={!!busy} placeholder="Ask anything about this decision…" onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && !busy && q.trim() && ask(q)} />
        <LoadingButton className="btn-primary shrink-0" loading={busy === "ask"} loadingText="Asking…" disabled={!!busy || !q.trim()} onClick={() => ask(q)}><Send className="h-4 w-4" /> Ask</LoadingButton>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">{suggestions.map((s) => <button key={s} disabled={!!busy} className="chip bg-slate-100 text-slate-600 hover:bg-slate-200 disabled:opacity-50" onClick={() => ask(s)}>{s}</button>)}</div>
      {busy && <div className="mt-3 rounded-xl bg-slate-50 p-4"><Spinner text={busy === "explain" ? "Gemini is writing a plain-language explanation…" : "Gemini is answering from the engine's verified numbers…"} /></div>}
      <div className="mt-4 space-y-3">
        {answers.map((x, i) => (
          <div key={i} className="rounded-xl bg-slate-50 p-4">
            <div className="text-xs font-semibold text-slate-500">{x.q}</div>
            <div className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{x.text}</div>
            <div className="mt-1 text-[11px] text-slate-400">source: {x.source === "gemini" ? "Google Gemini (grounded in the engine's memo)" : x.source}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
