import { useState, type ReactNode } from "react";
import {
  BookOpen, BrainCircuit, CheckCircle2, ChevronDown, CircleDot, FileSearch, FolderCheck, Gauge, GitCompare,
  HelpCircle, Lock, ShieldCheck, Sparkles, Stamp, UserRound,
} from "lucide-react";
import type { User } from "../api";

export const STEPS = [
  { key: "start", title: "Add documents", sub: "Sample or your own", icon: FileSearch },
  { key: "facts", title: "Check the facts", sub: "Verify what AI read", icon: ShieldCheck },
  { key: "risk", title: "See the cash risk", sub: "Day-by-day balance", icon: Gauge },
  { key: "options", title: "Compare options", sub: "Find the safest way", icon: GitCompare },
  { key: "act", title: "Approve & notify", sub: "Email the other side", icon: Stamp },
] as const;

function Section({ title, icon, children, open: initial = false }: { title: string; icon: ReactNode; children: ReactNode; open?: boolean }) {
  const [open, setOpen] = useState(initial);
  return (
    <div className="border-b border-white/10">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-2 py-3 text-left text-sm font-semibold text-slate-100 hover:text-white">
        <span className="flex items-center gap-2">{icon}{title}</span>
        <ChevronDown className={`h-4 w-4 text-slate-400 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="pb-4 text-[13px] leading-relaxed text-slate-300">{children}</div>}
    </div>
  );
}

function Term({ t, children }: { t: string; children: ReactNode }) {
  return <p className="mb-2"><span className="font-semibold text-white">{t}: </span>{children}</p>;
}

export function Sidebar({ step, maxStep, onStep, ai, onHowItWorks, user, onProfile, approvedActive, onApproved }: {
  step: number; maxStep: number; onStep: (i: number) => void;
  ai: { label: string; gemini: boolean } | null; onHowItWorks: () => void;
  user: User; onProfile: () => void; approvedActive: boolean; onApproved: () => void;
}) {
  return (
    <aside className="flex h-full w-[300px] shrink-0 flex-col bg-gradient-to-b from-ink-950 via-ink-900 to-ink-800 text-slate-200">
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 shadow-lg shadow-brand-600/30">
            <CheckCircle2 className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="text-xl font-extrabold tracking-tight text-white">SolvOrder</div>
            <div className="text-[11px] font-medium text-brand-500">Can my cash carry this order?</div>
          </div>
        </div>
      </div>

      <nav className="px-3">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const active = i === step && !approvedActive, done = i < step, locked = i > maxStep;
          return (
            <button key={s.key} disabled={locked} onClick={() => onStep(i)}
              className={`mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${active ? "bg-white/10 text-white" : locked ? "cursor-not-allowed text-slate-500" : "text-slate-300 hover:bg-white/5"}`}>
              <span className={`grid h-7 w-7 place-items-center rounded-lg text-xs font-bold ${active ? "bg-brand-600 text-white" : done ? "bg-brand-700/40 text-brand-100" : "bg-white/5"}`}>
                {done ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold">{s.title}</span>
                <span className="block text-[11px] text-slate-400">{s.sub}</span>
              </span>
              {active && <Icon className="ml-auto h-4 w-4 text-brand-500" />}
            </button>
          );
        })}
        <button onClick={onApproved}
          className={`mt-2 flex w-full items-center gap-3 rounded-xl border border-white/10 px-3 py-2.5 text-left transition ${approvedActive ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5"}`}>
          <span className={`grid h-7 w-7 place-items-center rounded-lg ${approvedActive ? "bg-brand-600 text-white" : "bg-white/5"}`}><FolderCheck className="h-4 w-4" /></span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold">Approved plans</span>
            <span className="block text-[11px] text-slate-400">Plans and the emails sent</span>
          </span>
        </button>
      </nav>

      <div className="mx-6 mt-4 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
        <BookOpen className="h-3.5 w-3.5" /> User manual
      </div>
      <div className="scroll-thin mt-1 flex-1 overflow-y-auto px-6">
        <Section title="What SolvOrder does" icon={<Sparkles className="h-4 w-4 text-brand-500" />} open>
          <p className="mb-2">A big order can be profitable and still sink you: you pay the supplier weeks before the customer pays you.</p>
          <p>SolvOrder reads the order documents, rebuilds your cash <b>day by day</b>, tells you if and when cash falls below your safety reserve, checks the documents for <b>fraud</b>, and finds the cheapest safe way to say yes.</p>
        </Section>
        <Section title="Quick start (5 steps)" icon={<CircleDot className="h-4 w-4 text-brand-500" />} open>
          <ol className="list-decimal space-y-1.5 pl-4">
            <li><b>Add documents.</b> Pick a sample case, or upload your purchase order, supplier quote and invoice (PDF or text).</li>
            <li><b>Check the facts.</b> Gemini reads the documents; every value shows the exact quote it came from. Fix or confirm anything marked <i>Needs your check</i>, and deal with any red fraud alert.</li>
            <li><b>See the cash risk.</b> The chart shows your balance every day if you accept as-is. Red = below your reserve.</li>
            <li><b>Compare options.</b> Customer advance, later supplier payment, a loan, or decline. Tell SolvOrder what matters most and how late the customer might pay.</li>
            <li><b>Approve & notify.</b> Approve one plan, then press <b>Notify my customer</b> (or supplier, when you are the buyer). The email goes to the demo outbox, the payments are booked in a simulated bank, and the plan is filed under <b>Approved plans</b>. Nothing real is sent.</li>
          </ol>
        </Section>
        <Section title="Reading the results" icon={<Gauge className="h-4 w-4 text-brand-500" />}>
          <Term t="Cash reserve">The minimum cash you always want to keep. A day below it is a <b>breach</b>.</Term>
          <Term t="Lowest balance">The worst day for your cash under a plan.</Term>
          <Term t="Funding gap">How much you are short, and for how many days, if you accept as-is.</Term>
          <Term t="Late-payment tolerance">How many days late the customer can pay before the plan breaks.</Term>
          <Term t="Stress test">Re-running every plan as if the customer pays 15, 30, 60 or 90 days late.</Term>
          <Term t="Provisional">A value that changes the result was read with low confidence. Confirm it before trusting the answer.</Term>
          <Term t="Near tie">Two plans are almost equal. You choose which advantage matters more.</Term>
          <Term t="Override">Approving a plan that breaks your reserve on purpose. It is recorded everywhere.</Term>
        </Section>
        <Section title="Fraud & safety checks" icon={<ShieldCheck className="h-4 w-4 text-brand-500" />}>
          <p className="mb-2"><b className="text-rose-300">Bank details changed / payee mismatch</b>: the invoice or an email asks you to pay a different account than the quote. Call the supplier on a number you already have. Payments stay blocked until you record that check.</p>
          <p className="mb-2"><b className="text-amber-300">Amounts don't match, unclear terms, cancel-anytime clauses</b>: SolvOrder shows both readings and asks you.</p>
          <p><b className="text-sky-300">Instructions to the AI</b> hidden in a document are flagged and ignored. They can never change the decision.</p>
        </Section>
        <Section title="What the AI does, and doesn't" icon={<BrainCircuit className="h-4 w-4 text-brand-500" />}>
          <p className="mb-2"><b>Gemini (Google AI)</b> reads your documents, explains the decision and polishes the draft email.</p>
          <p className="mb-2">It <b>never</b> does the maths, invents loan terms, decides what is safe or approves anything. A deterministic engine checks every number, and a verifier checks every quote Gemini returns.</p>
          <p>If Gemini is unavailable, SolvOrder still works: a built-in parser or manual entry replaces it.</p>
        </Section>
        <Section title="Permission tiers" icon={<Lock className="h-4 w-4 text-brand-500" />}>
          <Term t="T0 Read">Read documents and data. No effect.</Term>
          <Term t="T1 Propose">Simulate, rank, draft. Output only.</Term>
          <Term t="T2 Act">Sandbox bank, mock outbox and mock lender, only after you approve that exact plan.</Term>
          <Term t="T3 Never">Real money, real email, invented loan terms. No code path exists; attempts are logged.</Term>
        </Section>
        <Section title="FAQ" icon={<HelpCircle className="h-4 w-4 text-brand-500" />}>
          <Term t="Is this financial advice?">No. It is decision support on the figures you give it.</Term>
          <Term t="Is my data stored?">Only in this browser session's memory. Use synthetic data in this demo.</Term>
          <Term t="Why does it ask questions?">When a document is unclear it asks instead of guessing.</Term>
        </Section>
        <div className="h-4" />
      </div>

      <div className="space-y-3 border-t border-white/10 px-6 py-4">
        <button onClick={onProfile} className="flex w-full items-center gap-3 rounded-xl bg-white/5 p-2.5 text-left hover:bg-white/10" title="Profile, password and log out">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-600 text-sm font-bold text-white">
            {user.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase() || <UserRound className="h-4 w-4" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-white">{user.name}{user.demo && <span className="ml-1 text-[10px] font-normal text-amber-300">demo</span>}</div>
            <div className="truncate text-[11px] text-slate-400">{user.email}</div>
          </div>
          <span className="text-[11px] font-semibold text-teal-300">Profile</span>
        </button>
        <button onClick={onHowItWorks} className="flex w-full items-center justify-center gap-2 rounded-lg bg-white/10 py-2 text-sm font-semibold text-white hover:bg-white/15">
          <Sparkles className="h-4 w-4" /> How SolvOrder works
        </button>
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <span className={`h-2 w-2 rounded-full ${ai?.gemini ? "bg-emerald-400" : "bg-amber-400"}`} />
          <span className="truncate">{ai ? ai.label : "Checking AI…"}</span>
        </div>
        <p className="text-[10px] leading-snug text-slate-500">Decision support, not financial advice. Synthetic demo data; no real bank, lender or email is ever used.</p>
      </div>
    </aside>
  );
}
