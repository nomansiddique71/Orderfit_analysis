import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, authPost, forgetCase, get, me, post, resetSession, setToken, type Analysis, type DocView, type User } from "../api";
import type { FactState } from "../components/FactsStep";
import type { Choice } from "../components/OptionsStep";

export const EMPTY_FACTS: FactState = { edits: {}, payEdits: null, confirmed: new Set(), reserve: null, openingCash: null, maxFin: null };
const DEFAULT_CONTROLS = { priority: "maximize_margin", stress: 15, payDay: null as number | null, tie: null as string | null };
export type Controls = typeof DEFAULT_CONTROLS;

/**
 * All state and server calls behind the 5-step flow (moved out of App.tsx unchanged,
 * so App only lays out screens). Think of it as the screen's ViewModel.
 */
export function useCaseFlow() {
  const [step, setStep] = useState(0);
  const [maxStep, setMaxStep] = useState(0);
  const [ai, setAi] = useState<{ label: string; gemini: boolean } | null>(null);
  const [view, setView] = useState<DocView | null>(null);
  const [facts, setFacts] = useState<FactState>(EMPTY_FACTS);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [controls, setControlsState] = useState(DEFAULT_CONTROLS);
  const [reading, setReading] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState<string[] | null>(null);
  const [how, setHow] = useState(false);
  const [needsOpen, setNeedsOpen] = useState(false);
  const [choice, setChoice] = useState<Choice>(null);
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined = still checking
  const [profileOpen, setProfileOpen] = useState(false);
  const [page, setPage] = useState<"flow" | "approved">("flow");
  const [toast, setToast] = useState<string | null>(null);
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(null), 6000); return () => clearTimeout(t); }, [toast]);
  useEffect(() => { me().then(setUser).catch(() => setUser(null)); }, []);
  const main = useRef<HTMLDivElement>(null);

  useEffect(() => { get<{ ai: string; gemini: boolean }>("/api/health").then((h) => setAi({ label: h.ai, gemini: h.gemini })).catch(() => setAi(null)); }, []);

  const go = (i: number) => { setPage("flow"); setStep(i); setMaxStep((m) => Math.max(m, i)); main.current?.scrollTo({ top: 0, behavior: "smooth" }); };
  const setControls = (c: Partial<Controls>) => setControlsState((s) => ({ ...s, ...c }));

  const restart = useCallback((msg?: string) => {
    resetSession(); forgetCase(); setChoice(null); setView(null); setAnalysis(null); setFacts(EMPTY_FACTS); setReading(null);
    setControlsState(DEFAULT_CONTROLS);
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

  async function logout() {
    try { await authPost("/api/auth/logout"); } catch { /* already logged out */ }
    setToken(null); setProfileOpen(false); restart(); setUser(null);
  }

  /** A case was read (sample, upload or manual form): reset the flow and open "Check the facts". */
  function onLoaded(v: DocView) {
    setView(v); setChoice(null); setFacts(EMPTY_FACTS); setAnalysis(null); setReading(null); setMissing(null); setMaxStep(1); go(1);
    if (v.profile_source === "default" || v.questions > 0) setNeedsOpen(true);
  }

  /** Sidebar click: later steps need an analysis first. */
  const onStep = (i: number) => (i >= 2 && !analysis ? toRisk() : go(i));

  const confirmFact = (k: string) => setFacts((f) => ({ ...f, confirmed: new Set([...f.confirmed, k]) }));
  const chooseOption = (c: Choice) => { setChoice(c); go(4); };

  /** The intake pop-up switched the deal role: the case changed, the pop-up stays open. */
  const onNeedsView = (v: DocView) => { setView(v); setAnalysis(null); setMaxStep(1); };
  const onNeedsSaved = (v: DocView | null, answers: Record<string, string>) => {
    if (v) setView(v);
    setFacts((f) => ({ ...f, edits: { ...f.edits, ...answers }, ...(v ? { reserve: null, openingCash: null, maxFin: null } : {}) }));
    setMissing(null); setNeedsOpen(false);
  };

  return {
    step, maxStep, ai, view, setView, facts, setFacts, analysis, controls, setControls, reading, setReading,
    busy, error, missing, how, setHow, needsOpen, setNeedsOpen, choice, user, setUser, profileOpen, setProfileOpen,
    page, setPage, toast, setToast, main, go, restart, analyze, toRisk, logout, onLoaded, onStep, confirmFact, chooseOption,
    onNeedsView, onNeedsSaved,
  };
}
