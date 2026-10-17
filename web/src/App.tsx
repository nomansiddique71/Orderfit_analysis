import { useCallback, useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { ApiError, forgetCase, get, post, resetSession, type Analysis, type DocView } from "./api";
import { ActStep } from "./components/ActStep";
import { FactsStep, type FactState } from "./components/FactsStep";
import { HowItWorks } from "./components/HowItWorks";
import { NeedsModal } from "./components/NeedsModal";
import { OptionsStep } from "./components/OptionsStep";
import { RiskStep } from "./components/RiskStep";
import { Sidebar, STEPS } from "./components/Sidebar";
import { StartStep } from "./components/StartStep";
import { Callout, Spinner, TopProgress } from "./components/ui";

const INTRO = [
  "Start with the order. SolvOrder needs the purchase order and what you will pay the supplier; a quote, invoice or email helps the fraud checks.",
  "SolvOrder has read your documents (with Google Gemini when it is available). Each value shows the exact text it came from. Fix anything wrong, confirm what is flagged, and clear any fraud alert.",
  "Your cash, day by day, if you accept the order as it is, plus the recommended plan.",
  "SolvOrder tried every mix of customer advance, later supplier payment and loans, kept only plans that keep your reserve, and ranked them by what you care about.",
  "Approve one plan. SolvOrder drafts the message, runs the plan in a sandbox bank and logs every step. Nothing real is sent or paid.",
];

const EMPTY: FactState = { edits: {}, payEdits: null, confirmed: new Set(), reserve: null, openingCash: null, maxFin: null };

export default function App() {
  const [step, setStep] = useState(0);
  const [maxStep, setMaxStep] = useState(0);
  const [ai, setAi] = useState<{ label: string; gemini: boolean } | null>(null);
  const [view, setView] = useState<DocView | null>(null);
  const [facts, setFacts] = useState<FactState>(EMPTY);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [controls, setControlsState] = useState({ priority: "maximize_margin", stress: 15, payDay: null as number | null, tie: null as string | null });
  const [reading, setReading] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState<string[] | null>(null);
  const [how, setHow] = useState(false);
  const [needsOpen, setNeedsOpen] = useState(false);
  const main = useRef<HTMLDivElement>(null);

  useEffect(() => { get<{ ai: string; gemini: boolean }>("/api/health").then((h) => setAi({ label: h.ai, gemini: h.gemini })).catch(() => setAi(null)); }, []);

  const go = (i: number) => { setStep(i); setMaxStep((m) => Math.max(m, i)); main.current?.scrollTo({ top: 0, behavior: "smooth" }); };
  const setControls = (c: Partial<typeof controls>) => setControlsState((s) => ({ ...s, ...c }));

  const restart = useCallback((msg?: string) => {
    resetSession(); forgetCase(); setView(null); setAnalysis(null); setFacts(EMPTY); setReading(null);
    setControlsState({ priority: "maximize_margin", stress: 15, payDay: null, tie: null });
    setStep(0); setMaxStep(0); setError(msg ?? null);
  }, []);

  const analyze = useCallback(async () => {
    if (!view) return null;
    const edits: Record<string, unknown> = {};
    for (const f of view.facts) {
      const v = facts.edits[f.key];
      if (v !== undefined && v !== f.value) edits[f.key] = v;
    }
    if (facts.payEdits) edits.supplier_payments = facts.payEdits;
    setBusy(true); setError(null);
    try {
      const r = await post<Analysis>("/api/analyze", {
        edits, confirmed: [...facts.confirmed], payment_reading: reading, priority: controls.priority,
        stress_delay: controls.stress, reserve: facts.reserve, opening_cash: facts.openingCash,
        max_financing_cost: facts.maxFin, pay_day: controls.payDay, tie_choice: controls.tie,
      });
      if (!r.ok) { setMissing(r.missing ?? []); setAnalysis(null); if (r.needs_business) setNeedsOpen(true); return r; }
      setMissing(null); setAnalysis(r);
      return r;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) restart("Your session expired. Please start again.");
      else setError((e as Error).message);
      return null;
    } finally { setBusy(false); }
  }, [view, facts, reading, controls, restart]);

  // Re-run the engine (no AI calls) whenever an input changes after the first analysis.
  useEffect(() => {
    if (step < 2 || !view) return;
    const t = setTimeout(() => { analyze(); }, 250);
    return () => clearTimeout(t);
  }, [controls, reading, facts.confirmed]); // eslint-disable-line react-hooks/exhaustive-deps

  async function toRisk() {
    const r = await analyze();
    if (r && r.ok) go(2);
  }

  return (
    <div className="flex h-full">
      <TopProgress />
      <Sidebar step={step} maxStep={maxStep} onStep={(i) => (i >= 2 && !analysis ? toRisk() : go(i))} ai={ai} onHowItWorks={() => setHow(true)} />
      <main ref={main} className="flex-1 overflow-y-auto">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/85 px-8 py-4 backdrop-blur">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="label text-brand-700">Step {step + 1} of 5</div>
              <h2 className="text-xl font-extrabold text-slate-900">{STEPS[step].title}</h2>
              <p className="max-w-3xl text-sm text-slate-500">{INTRO[step]}</p>
            </div>
            <div className="flex shrink-0 items-center gap-3 whitespace-nowrap">
              {busy && step >= 2 && <Spinner text="Updating results…" />}
              {view && <button className="btn-secondary whitespace-nowrap" disabled={busy} onClick={() => restart()}><RotateCcw className="h-4 w-4" /> New case</button>}
            </div>
          </div>
        </header>
        <div className="mx-auto max-w-7xl space-y-4 px-8 py-6">
          {error && <Callout tone="critical" title="Something went wrong">{error}</Callout>}
          {missing && <Callout tone="warning" title="SolvOrder needs a few more facts before it can calculate">
            These were not found in the documents: <b>{missing.join(", ")}</b>. Add them in the table below (or use the manual form on the first screen). SolvOrder never guesses a number.
          </Callout>}

          {step === 0 && <StartStep aiOn={!!ai?.gemini} onHowItWorks={() => setHow(true)} onLoaded={(v) => { setView(v); setFacts(EMPTY); setAnalysis(null); setReading(null); setMissing(null); setMaxStep(1); go(1); if (v.profile_source === "default") setNeedsOpen(true); }} />}
          {step === 1 && view && <FactsStep view={view} setView={setView} state={facts} setState={setFacts} onNext={toRisk} analysing={busy} onOpenNeeds={() => setNeedsOpen(true)} />}
          {step === 2 && analysis && <RiskStep a={analysis} reading={reading} setReading={setReading} onNext={() => go(3)} updating={busy}
            onConfirm={(k) => setFacts((f) => ({ ...f, confirmed: new Set([...f.confirmed, k]) }))} />}
          {step === 3 && analysis && <OptionsStep a={analysis} controls={controls} setControls={setControls} onNext={() => go(4)} updating={busy} />}
          {step === 4 && analysis && <ActStep key={analysis.verdict.winner + analysis.plans[0]?.version} a={analysis} refresh={async () => { await analyze(); }} />}
          {step >= 2 && !analysis && !busy && <Callout tone="info">Go back to <b>Check the facts</b> and press <b>Analyse my cash</b>.</Callout>}
        </div>
      </main>
      {how && <HowItWorks onClose={() => setHow(false)} />}
      {needsOpen && view && <NeedsModal edits={facts.edits} onClose={() => setNeedsOpen(false)}
        onSaved={(v, answers) => {
          if (v) setView(v);
          setFacts((f) => ({ ...f, edits: { ...f.edits, ...answers }, ...(v ? { reserve: null, openingCash: null, maxFin: null } : {}) }));
          setMissing(null); setNeedsOpen(false);
        }} />}
    </div>
  );
}
