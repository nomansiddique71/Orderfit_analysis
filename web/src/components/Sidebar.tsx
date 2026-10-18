import { useState, type ReactNode } from "react";
import {
  BookOpen, BrainCircuit, Check, ChevronDown, CircleDot, FileSearch, FolderCheck, Gauge, GitCompare,
  HelpCircle, Lock, ShieldCheck, Sparkles, Stamp, UserRound,
} from "lucide-react";
import type { User } from "../api";

export const STEPS = [
  { key: "start", title: "Add documents", sub: "Your own or a sample", icon: FileSearch },
  { key: "facts", title: "Check the facts", sub: "Confirm what was read", icon: ShieldCheck },
  { key: "risk", title: "See the cash risk", sub: "Day-by-day balance", icon: Gauge },
  { key: "options", title: "Compare options", sub: "Find the safest way", icon: GitCompare },
  { key: "act", title: "Approve and Notify", sub: "Email the other side", icon: Stamp },
] as const;

/** SolvOrder's mark: a cash line that dips but stays above the reserve line. */
export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="7" fill="var(--color-brand-600)" />
      <path d="M6 21.5h20" stroke="#d8e8dd" strokeWidth="1.6" strokeDasharray="2.4 2" />
      <path d="M6 10.5h6v6h6v-4h8" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinejoin="round" />
    </svg>
  );
}

function Section({ title, icon, children, open: initial = false }: { title: string; icon: ReactNode; children: ReactNode; open?: boolean }) {
  const [open, setOpen] = useState(initial);
  return (
    <div className="border-b border-slate-200 last:border-b-0">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between gap-2 py-2.5 text-left text-[13px] font-semibold text-slate-700 hover:text-slate-950">
        <span className="flex items-center gap-2">{icon}{title}</span>
        <ChevronDown className={`h-4 w-4 text-slate-400 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="pb-4 text-[13px] leading-relaxed text-slate-600">{children}</div>}
    </div>
  );
}

function Term({ t, children }: { t: string; children: ReactNode }) {
  return <p className="mb-2"><span className="font-semibold text-slate-800">{t}: </span>{children}</p>;
}

export function Sidebar({ step, maxStep, onStep, ai, onHowItWorks, user, onProfile, approvedActive, onApproved }: {
  step: number; maxStep: number; onStep: (i: number) => void;
  ai: { label: string; gemini: boolean } | null; onHowItWorks: () => void;
  user: User; onProfile: () => void; approvedActive: boolean; onApproved: () => void;
}) {
  const icon = "h-4 w-4 text-brand-600";
  return (
    <aside className="flex h-full w-[284px] shrink-0 flex-col border-r border-slate-200 bg-slate-50 text-slate-700">
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center gap-2.5">
          <Logo />
          <div>
            <div className="font-serif text-[21px] font-semibold leading-none text-slate-900">SolvOrder</div>
            <div className="mt-1 text-[12px] text-slate-500">Can my cash carry this order?</div>
          </div>
        </div>
      </div>

      <nav aria-label="Steps" className="px-3">
        <ol className="relative">
          {STEPS.map((s, i) => {
            const active = i === step && !approvedActive, done = i < step, locked = i > maxStep;
            return (
              <li key={s.key} className="relative">
                {i < STEPS.length - 1 && <span aria-hidden className={`absolute left-[25px] top-10 h-[calc(100%-24px)] w-px ${i < maxStep ? "bg-brand-300" : "bg-slate-200"}`} />}
                <button disabled={locked} onClick={() => onStep(i)} aria-current={active ? "step" : undefined}
                  className={`relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition ${active ? "bg-white shadow-md ring-1 ring-slate-200" : locked ? "cursor-not-allowed" : "hover:bg-white/70"}`}>
                  <span className={`grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full text-xs font-bold ${active ? "bg-brand-600 text-white" : done ? "bg-brand-100 text-brand-700" : locked ? "border border-slate-300 bg-slate-50 text-slate-400" : "border border-slate-300 bg-white text-slate-600"}`}>
                    {done ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className={`block text-sm font-semibold ${active ? "text-slate-900" : locked ? "text-slate-400" : "text-slate-700"}`}>{s.title}</span>
                    <span className={`block text-[12px] ${locked ? "text-slate-400" : "text-slate-500"}`}>{s.sub}</span>
                  </span>
                  {locked && <Lock className="ml-auto h-3.5 w-3.5 text-slate-300" aria-label="Not yet available" />}
                </button>
              </li>
            );
          })}
        </ol>
        <div className="mx-3 my-3 border-t border-slate-200" />
        <button onClick={onApproved} aria-current={approvedActive ? "page" : undefined}
          className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition ${approvedActive ? "bg-white shadow-md ring-1 ring-slate-200" : "hover:bg-white/70"}`}>
          <span className={`grid h-[26px] w-[26px] place-items-center rounded-full ${approvedActive ? "bg-brand-600 text-white" : "border border-slate-300 bg-white text-slate-600"}`}><FolderCheck className="h-3.5 w-3.5" /></span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-slate-800">Approved / declined plans</span>
            <span className="block text-[12px] text-slate-500">Decisions and the emails sent</span>
          </span>
        </button>
      </nav>

      <div className="mx-5 mt-5 flex items-center gap-2 text-[12px] font-semibold text-slate-500">
        <BookOpen className="h-3.5 w-3.5" /> Help
      </div>
      <div className="scroll-thin mt-1 flex-1 overflow-y-auto px-5">
        <Section title="Quick start (5 steps)" icon={<CircleDot className={icon} />} open>
          <ol className="list-decimal space-y-1.5 pl-4">
            <li><b>Add documents.</b> Upload your purchase order, supplier quote and invoice (PDF or text), type the facts in, or pick a sample case.</li>
            <li><b>Check the facts.</b> Gemini reads the documents; every value shows the exact words it came from. Fix or confirm anything marked <i>Needs your check</i>, and deal with any red fraud alert.</li>
            <li><b>See the cash risk.</b> The chart shows your balance every day if you accept as-is. Red means below your reserve.</li>
            <li><b>Compare options.</b> Customer advance, later supplier payment, a loan, or decline. Tell SolvOrder what matters most and how late the customer might pay.</li>
            <li><b>Approve and Notify.</b> Approve one plan, then press <b>Notify my customer</b> (or supplier, when you are the buyer). The email goes to the demo outbox, the payments are booked in a practice bank, and the plan is filed under <b>Approved / declined plans</b>. Nothing real is sent.</li>
          </ol>
        </Section>
        <Section title="Reading the results" icon={<Gauge className={icon} />}>
          <Term t="Cash reserve">The minimum cash you always want to keep. A day below it is a <b>breach</b>.</Term>
          <Term t="Lowest balance">The worst day for your cash under a plan.</Term>
          <Term t="Funding gap">How much you are short, and for how many days, if you accept as-is.</Term>
          <Term t="Late-payment tolerance">How many days late the customer can pay before the plan breaks.</Term>
          <Term t="Stress test">Re-running every plan as if the customer pays 15, 30, 60 or 90 days late.</Term>
          <Term t="Provisional">A value that changes the result was read with low confidence. Confirm it before trusting the answer.</Term>
          <Term t="Near tie">Two plans are almost equal. You choose which advantage matters more.</Term>
          <Term t="Override">Approving a plan that breaks your reserve on purpose. It is recorded everywhere.</Term>
        </Section>
        <Section title="Fraud and safety checks" icon={<ShieldCheck className={icon} />}>
          <p className="mb-2"><b className="text-rose-700">Bank details changed or payee mismatch</b>: the invoice or an email asks you to pay a different account than the quote. Call the supplier on a number you already have. Payments stay blocked until you record that check.</p>
          <p className="mb-2"><b className="text-amber-700">Amounts don't match, unclear terms, cancel-anytime clauses</b>: SolvOrder shows both readings and asks you.</p>
          <p><b className="text-sky-700">Instructions to the AI</b> hidden in a document are flagged and ignored. They can never change the decision.</p>
        </Section>
        <Section title="What the AI does, and doesn't" icon={<BrainCircuit className={icon} />}>
          <p className="mb-2"><b>Gemini (Google AI)</b> reads your documents, explains the decision and polishes the draft email.</p>
          <p className="mb-2">It <b>never</b> does the maths, invents loan terms, decides what is safe or approves anything. A fixed calculator checks every number, and every quote Gemini returns is checked against the document.</p>
          <p>If Gemini is unavailable, SolvOrder still works: a built-in reader or manual entry replaces it.</p>
        </Section>
        <Section title="What SolvOrder is allowed to do" icon={<Lock className={icon} />}>
          <Term t="Read">Read documents and data. No effect.</Term>
          <Term t="Suggest">Simulate, rank, draft. Output only.</Term>
          <Term t="Act in practice systems">Demo outbox, practice bank and practice lender, only after you approve that exact plan.</Term>
          <Term t="Never">Real money, real email, invented loan terms. There is no way for it to do these; attempts are blocked and logged.</Term>
        </Section>
        <Section title="Questions" icon={<HelpCircle className={icon} />}>
          <Term t="Is this financial advice?">No. It is decision support on the figures you give it.</Term>
          <Term t="Is my data stored?">Only in this browser session's memory. Use made-up data in this demo.</Term>
          <Term t="Why does it ask questions?">When a document is unclear it asks instead of guessing.</Term>
        </Section>
        <div className="h-4" />
      </div>

      <div className="space-y-3 border-t border-slate-200 px-4 py-4">
        <button onClick={onProfile} className="flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-white" title="Profile, password and log out">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-100 text-sm font-bold text-brand-800">
            {user.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase() || <UserRound className="h-4 w-4" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-slate-900">{user.name}{user.demo && <span className="ml-1.5 rounded bg-amber-100 px-1 text-[10px] font-semibold text-amber-800">demo</span>}</div>
            <div className="truncate text-[12px] text-slate-500">{user.email}</div>
          </div>
          <span className="text-[12px] font-semibold text-brand-700">Profile</span>
        </button>
        <button onClick={onHowItWorks} className="btn-secondary w-full">
          <Sparkles className="h-4 w-4 text-brand-600" /> How SolvOrder works
        </button>
        <div className="flex items-center gap-2 text-[12px] text-slate-500">
          <span className={`h-2 w-2 shrink-0 rounded-full ${ai?.gemini ? "bg-emerald-500" : "bg-amber-500"}`} aria-hidden />
          <span className="truncate">{ai ? ai.label : "Checking AI…"}</span>
        </div>
        <p className="text-[11px] leading-snug text-slate-400">Decision support, not financial advice. Made-up demo data; no real bank, lender or email is ever used.</p>
      </div>
    </aside>
  );
}
