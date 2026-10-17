import { ArrowRight, BrainCircuit, Calculator, FileText, Scale, ShieldAlert, Stamp, UserCheck, X } from "lucide-react";

const FLOW = [
  { icon: FileText, title: "Your documents", text: "Purchase order, supplier quote, invoice, emails (PDF or text)." },
  { icon: BrainCircuit, title: "Gemini reads", text: "Google Gemini extracts amounts, dates, terms and bank details, quoting its source." },
  { icon: ShieldAlert, title: "Verify & check fraud", text: "Every quote is matched to the document. Rules flag changed bank details, mismatches and hidden instructions." },
  { icon: Calculator, title: "Engine simulates", text: "Exact decimal maths: your cash every day, for every option, on time and when paid late." },
  { icon: Scale, title: "Decide", text: "Only plans that keep your reserve qualify; they are ranked by what matters to you." },
  { icon: UserCheck, title: "You approve", text: "Nothing happens without your approval of that exact plan." },
  { icon: Stamp, title: "Sandbox acts", text: "Email, loan acceptance and payments run in a simulated bank, each step logged." },
];

const BFSI = [
  { t: "Risk", d: "Liquidity risk of a single order: reserve breaches, funding gap, late-payment stress, cancellation exposure." },
  { t: "Fraud", d: "Payment-diversion checks (bank details or payee changed), invoice/quote mismatches, pressure wording, prompt injection." },
  { t: "Automating complex processes", d: "Documents → facts → cash rebuild → options → draft → approved, logged execution, in minutes." },
  { t: "Better interactions", d: "Plain-language verdict, ask-anything Q&A, and a ready-to-send, number-checked message to the customer or supplier." },
  { t: "Personalised & informed", d: "Your cash, your reserve, your priorities, your stress level; the answer changes when they do." },
];

export function HowItWorks({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink-950/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-3xl bg-white p-8 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-6 flex items-start justify-between">
          <div>
            <div className="label text-brand-700">How SolvOrder works</div>
            <h2 className="mt-1 text-2xl font-extrabold text-slate-900">The AI reads. The engine checks. You decide.</h2>
            <p className="mt-2 max-w-3xl text-slate-600">
              A small business gets a big, profitable order, but has to pay its supplier weeks before the customer pays.
              SolvOrder answers the real question before the owner commits: <b>can we accept this order without our cash
              falling below the safety reserve, and if not, what is the best way to make it work?</b>
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"><X className="h-5 w-5" /></button>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
          {FLOW.map((f, i) => (
            <div key={f.title} className="relative rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand-600 text-xs font-bold text-white">{i + 1}</span>
                <f.icon className="h-4 w-4 text-brand-700" />
              </div>
              <div className="text-sm font-bold text-slate-900">{f.title}</div>
              <div className="mt-1 text-xs leading-relaxed text-slate-600">{f.text}</div>
              {i < FLOW.length - 1 && <ArrowRight className="absolute -right-3 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-slate-300 lg:block" />}
            </div>
          ))}
        </div>

        <h3 className="mt-8 mb-3 text-lg font-bold text-slate-900">How it covers the BFSI track</h3>
        <div className="grid gap-3 md:grid-cols-5">
          {BFSI.map((b) => (
            <div key={b.t} className="rounded-2xl border border-brand-100 bg-brand-50/60 p-4">
              <div className="text-sm font-bold text-brand-700">{b.t}</div>
              <div className="mt-1 text-xs leading-relaxed text-slate-700">{b.d}</div>
            </div>
          ))}
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl bg-ink-900 p-5 text-slate-200">
            <div className="text-sm font-bold text-white">Gemini is used for</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              <li>Reading PDFs and text into typed facts, each with a verbatim quote</li>
              <li>Spotting instructions and conflicts inside documents</li>
              <li>Explaining the decision and answering your questions</li>
              <li>Polishing the negotiation email</li>
            </ul>
          </div>
          <div className="rounded-2xl border-2 border-rose-100 p-5">
            <div className="text-sm font-bold text-rose-700">Gemini can never</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              <li>Do the arithmetic or decide a plan is safe (the engine does)</li>
              <li>Create or change loan terms (catalogue only)</li>
              <li>Add or change a number in the email (rejected by a check)</li>
              <li>Approve or execute anything (owner approval + code-enforced tiers)</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
