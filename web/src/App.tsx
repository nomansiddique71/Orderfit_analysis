import { useEffect, useState } from "react";
import { BellRing, Menu, RotateCcw, X } from "lucide-react";
import { AuthScreen, ProfileModal } from "./components/Auth";
import { ActStep, DeclineStep } from "./components/ActStep";
import { ApprovedPlans } from "./components/ApprovedPlans";
import { FactsStep } from "./components/FactsStep";
import { HowItWorks } from "./components/HowItWorks";
import { NeedsModal } from "./components/NeedsModal";
import { OptionsStep } from "./components/OptionsStep";
import { RiskStep } from "./components/RiskStep";
import { Logo, Sidebar, STEPS } from "./components/Sidebar";
import { StartStep } from "./components/StartStep";
import { Callout, Spinner, TopProgress } from "./components/ui";
import { useCaseFlow } from "./hooks/useCaseFlow";

const INTRO = [
  "Start with the order. SolvOrder needs the purchase order and what you will pay the supplier. A quote, invoice or email helps it spot fraud.",
  "Here is what SolvOrder read from your documents, with the exact words each value came from. Fix anything wrong, confirm anything marked for checking, and deal with any fraud alert.",
  "Your bank balance, day by day, if you accept the deal as it is, next to the plan SolvOrder recommends.",
  "SolvOrder tried every mix of customer advance, later supplier payment and loans, kept only the plans that keep your reserve, and ranked them by what you care about.",
  "Approve one plan and let the other side know by email, or, when no plan keeps your reserve, decline politely. Everything here is practice: nothing real is sent or paid.",
];

export default function App() {
  const f = useCaseFlow();
  const [navOpen, setNavOpen] = useState(false); // mobile menu only
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setNavOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

  if (f.user === undefined) return <div className="grid h-full place-items-center"><Spinner text="Opening SolvOrder…" /></div>;
  if (f.user === null) return <><TopProgress /><AuthScreen onAuthed={(a) => f.setUser(a.user)} /></>;
  const user = f.user;

  const sidebar = (closeAfter: boolean) => {
    const wrap = <A extends unknown[]>(fn: (...a: A) => unknown) => (...a: A) => { if (closeAfter) setNavOpen(false); fn(...a); };
    return (
      <Sidebar step={f.step} maxStep={f.maxStep} onStep={wrap(f.onStep)} ai={f.ai} onHowItWorks={wrap(() => f.setHow(true))}
        user={user} onProfile={wrap(() => f.setProfileOpen(true))} approvedActive={f.page === "approved"} onApproved={wrap(() => f.setPage("approved"))} />
    );
  };
  const approved = f.page === "approved";

  return (
    <div className="flex h-full">
      <TopProgress />
      <div className="hidden lg:flex">{sidebar(false)}</div>
      {navOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-ink-950/40" onClick={() => setNavOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex max-w-[88vw] shadow-2xl">
            {sidebar(true)}
            <button className="absolute right-2 top-4 rounded-md p-1.5 text-slate-500 hover:bg-slate-200" aria-label="Close menu" onClick={() => setNavOpen(false)}><X className="h-5 w-5" /></button>
          </div>
        </div>
      )}

      <main ref={f.main} className="relative min-w-0 flex-1 overflow-y-auto">
        <div className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2.5 lg:hidden">
          <button className="rounded-md p-1.5 text-slate-700 hover:bg-slate-200" aria-label="Open menu" onClick={() => setNavOpen(true)}><Menu className="h-5 w-5" /></button>
          <Logo className="h-6 w-6" />
          <span className="font-serif text-lg font-semibold text-slate-900">SolvOrder</span>
        </div>

        <header className="border-b border-slate-200 bg-slate-100/95 px-4 pt-6 pb-5 sm:px-8 lg:sticky lg:top-0 lg:z-10">
          <div className="mx-auto flex max-w-6xl flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
            <div className="min-w-0">
              {approved ? <>
                <div className="text-[13px] font-semibold text-brand-700">Your records</div>
                <h1 className="mt-0.5 text-[28px] font-semibold leading-tight text-slate-900">Approved / declined plans</h1>
                <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-slate-600">Every plan you approved and every deal you declined, with the reasons, the numbers and the emails that went to your customer or supplier.</p>
              </> : <>
                <div className="text-[13px] font-semibold text-brand-700">Step {f.step + 1} of 5</div>
                <h1 className="mt-0.5 text-[28px] font-semibold leading-tight text-slate-900">{STEPS[f.step].title}</h1>
                <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-slate-600">{INTRO[f.step]}</p>
              </>}
            </div>
            <div className="flex items-center justify-between gap-3 sm:shrink-0 sm:justify-end sm:gap-4">
              {/* Fixed slot so the "Updating" spinner never shifts the layout */}
              <div className="flex min-h-5 sm:min-w-[150px] sm:justify-end" aria-live="polite">{f.busy && f.step >= 2 && <Spinner text="Updating results…" />}</div>
              {f.view && !approved && <button className="btn-secondary whitespace-nowrap" disabled={f.busy} onClick={() => f.restart()}><RotateCcw className="h-4 w-4" /> New case</button>}
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-8 sm:py-8">
          {f.error && <Callout tone="critical" title="Something went wrong">{f.error}</Callout>}
          {f.missing && <Callout tone="warning" title="SolvOrder needs a few more facts before it can calculate">
            These were not found in the documents: <b>{f.missing.join(", ")}</b>. Add them in the table below (or use the form on the first screen). SolvOrder never guesses a number.
          </Callout>}

          {approved && <ApprovedPlans onBack={() => f.setPage("flow")} />}
          {!approved && <>
          {f.step === 0 && <StartStep aiOn={!!f.ai?.gemini} role={user.role} company={user.business} onHowItWorks={() => f.setHow(true)} onLoaded={f.onLoaded} />}
          {f.step === 1 && f.view && <FactsStep view={f.view} setView={f.setView} state={f.facts} setState={f.setFacts} onNext={f.toRisk} analysing={f.busy} onOpenNeeds={() => f.setNeedsOpen(true)} />}
          {f.step === 2 && f.analysis && <RiskStep a={f.analysis} reading={f.reading} setReading={f.setReading} onNext={() => f.go(3)} updating={f.busy} onConfirm={f.confirmFact} />}
          {f.step === 3 && f.analysis && <OptionsStep a={f.analysis} controls={f.controls} setControls={f.setControls} onNext={() => f.go(4)} updating={f.busy}
            choice={f.choice} onChoose={f.chooseOption} />}
          {f.step === 4 && f.analysis && f.analysis.verdict.winner === "decline" && <DeclineStep key={f.analysis.plans[0]?.version} a={f.analysis} onSent={f.setToast} onOpenApproved={() => f.setPage("approved")} />}
          {f.step === 4 && f.analysis && f.analysis.verdict.winner !== "decline" && <ActStep key={f.analysis.verdict.winner + f.analysis.plans[0]?.version + (f.choice?.id ?? "")} a={f.analysis} choice={f.choice}
            refresh={async () => { await f.analyze(); }} onSent={f.setToast} onOpenApproved={() => f.setPage("approved")} />}
          {f.step >= 2 && !f.analysis && !f.busy && <Callout tone="info">Go back to <b>Check the facts</b> and press <b>Analyse my cash</b>.</Callout>}
          </>}
        </div>
      </main>

      {f.toast && (
        <div role="status" className="fixed inset-x-4 bottom-4 z-50 flex items-start gap-3 rounded-xl bg-ink-900 px-5 py-4 text-sm text-white shadow-2xl sm:inset-x-auto sm:bottom-6 sm:right-6 sm:max-w-md">
          <BellRing className="mt-0.5 h-5 w-5 shrink-0 text-brand-300" />
          <div className="flex-1">{f.toast}</div>
          <button className="text-slate-300 hover:text-white" aria-label="Dismiss" onClick={() => f.setToast(null)}><X className="h-4 w-4" /></button>
        </div>
      )}
      {f.how && <HowItWorks onClose={() => f.setHow(false)} />}
      {f.profileOpen && <ProfileModal user={user} onClose={() => f.setProfileOpen(false)} onUser={f.setUser} onLogout={f.logout} />}
      {f.needsOpen && f.view && <NeedsModal edits={f.facts.edits} role={f.view.role} onClose={() => f.setNeedsOpen(false)}
        onView={f.onNeedsView} onSaved={f.onNeedsSaved} />}
    </div>
  );
}
