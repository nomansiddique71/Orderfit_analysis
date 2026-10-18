import { BrainCircuit, Calculator, FileText, Scale, ShieldAlert, Stamp, UserCheck, X } from "lucide-react";

const FLOW = [
  { icon: FileText, title: "Your documents", text: "Purchase order, supplier quote, invoice, emails (PDF or text)." },
  { icon: BrainCircuit, title: "Gemini reads", text: "Google Gemini extracts amounts, dates, terms and bank details, quoting its source." },
  { icon: ShieldAlert, title: "Verify & check fraud", text: "Every quote is matched to the document. Rules flag changed bank details, mismatches and hidden instructions." },
  { icon: Calculator, title: "Calculator simulates", text: "Exact decimal maths: your cash every day, for every option, on time and when paid late." },
  { icon: Scale, title: "Decide", text: "Only plans that keep your reserve qualify; they are ranked by what matters to you." },
  { icon: UserCheck, title: "You approve", text: "Nothing happens without your approval of that exact plan." },
  { icon: Stamp, title: "Practice systems act", text: "Email, loan acceptance and payments run in a practice outbox, lender and bank, each step logged." },
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
    <div role="dialog" aria-modal="true" aria-label="How SolvOrder works" className="fixed inset-0 z-50 grid place-items-center bg-ink-950/45 p-3 sm:p-4" onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl sm:p-8" onClick={(e) => e.stopPropagation()}>
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <div className="text-[13px] font-semibold text-brand-700">How SolvOrder works</div>
            <h2 className="mt-1 text-[28px] font-semibold leading-tight text-slate-900">The AI reads. The calculator checks. You decide.</h2>
            <p className="mt-3 max-w-3xl leading-relaxed text-slate-600">
              A small business gets a big, profitable order, but has to pay its supplier weeks before the customer pays.
              SolvOrder answers the real question before the owner commits: <b className="text-slate-900">can we accept this order without our cash
              falling below the safety reserve, and if not, what is the best way to make it work?</b>
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><X className="h-5 w-5" /></button>
        </div>

        <ol className="relative grid gap-x-4 gap-y-5 sm:grid-cols-2 lg:grid-cols-7">
          <span aria-hidden className="absolute left-0 right-0 top-[15px] hidden h-px bg-slate-200 lg:block" />
          {FLOW.map((f, i) => (
            <li key={f.title} className="relative flex gap-3 lg:block">
              <span className="relative z-[1] grid h-8 w-8 shrink-0 place-items-center rounded-full border border-brand-200 bg-white text-sm font-semibold text-brand-700">{i + 1}</span>
              <div className="lg:mt-3">
                <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-900"><f.icon className="h-4 w-4 text-brand-600" />{f.title}</div>
                <div className="mt-1 text-[13px] leading-relaxed text-slate-600">{f.text}</div>
              </div>
            </li>
          ))}
        </ol>

        <h3 className="mt-10 mb-3 text-xl font-semibold text-slate-900">How it covers the BFSI track</h3>
        <dl className="divide-y divide-slate-200 border-y border-slate-200">
          {BFSI.map((b) => (
            <div key={b.t} className="grid gap-1 py-3 sm:grid-cols-[220px_1fr] sm:gap-6">
              <dt className="text-sm font-semibold text-brand-700">{b.t}</dt>
              <dd className="text-sm leading-relaxed text-slate-700">{b.d}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border-l-[3px] border-brand-500 bg-brand-50 p-5">
            <div className="text-sm font-semibold text-brand-800">Gemini is used for</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              <li>Reading PDFs and text into facts, each with the exact words it came from</li>
              <li>Spotting instructions and conflicts inside documents</li>
              <li>Explaining the decision and answering your questions</li>
              <li>Polishing the email to the other side</li>
            </ul>
          </div>
          <div className="rounded-lg border-l-[3px] border-rose-500 bg-rose-50 p-5">
            <div className="text-sm font-semibold text-rose-800">Gemini can never</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              <li>Do the arithmetic or decide a plan is safe (the calculator does)</li>
              <li>Create or change loan terms (lenders' own offers only)</li>
              <li>Add or change a number in the email (a check rejects it)</li>
              <li>Approve or carry out anything (only you can, and the code enforces it)</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
