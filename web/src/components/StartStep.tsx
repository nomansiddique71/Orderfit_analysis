import { useState } from "react";
import { BadgeAlert, FileText, FileUp, Keyboard, LayoutList, Plus, Scale, Sparkles, Trash2, Upload, Wallet } from "lucide-react";
import type { DocView, Role } from "../api";
import { useStartStep } from "../hooks/useStartStep";
import { SampleCarousel } from "./SampleCarousel";
import { BusyOverlay, Callout, Card, LoadingButton, SectionTitle } from "./ui";

const PROMISES = [
  { icon: Wallet, t: "Cash risk", d: "Your balance for every day of the deal, the days it dips below your safety reserve, and what happens if you are paid late." },
  { icon: BadgeAlert, t: "Fraud checks", d: "Changed bank details, invoices that don't match the quote, and hidden instructions aimed at the AI." },
  { icon: Scale, t: "A clear decision", d: "Options ranked by what matters to you. Nothing is sent or paid until you approve." },
];

export function StartStep({ onLoaded, onHowItWorks, aiOn, role, company }: {
  onLoaded: (v: DocView) => void; onHowItWorks: () => void; aiOn: boolean; role: Role; company: string;
}) {
  const s = useStartStep(onLoaded, aiOn);
  const { busy } = s;

  return (
    <div className="space-y-8">
      <section className="card grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.25fr_1fr] lg:gap-10">
        <div>
          <h2 className="text-[26px] font-semibold leading-tight text-slate-900 sm:text-[30px]">Got a big order? Check that your cash can carry it before you say yes.</h2>
          <p className="mt-3 max-w-xl leading-relaxed text-slate-600">
            SolvOrder reads the purchase order and your supplier's documents with Google Gemini, checks them for fraud,
            works out your bank balance for every day of the deal, and suggests the safest way to accept. If there isn't one, it tells you plainly.
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button onClick={onHowItWorks} className="btn-secondary">How it works</button>
            <a href="#samples" className="btn-quiet">No documents to hand? Try a sample case ↓</a>
          </div>
        </div>
        <ul className="divide-y divide-slate-200 border-y border-slate-200 lg:self-center">
          {PROMISES.map(({ icon: Icon, t, d }) => (
            <li key={t} className="flex gap-3 py-3.5">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
              <div><div className="text-sm font-semibold text-slate-900">{t}</div><div className="text-[13px] leading-relaxed text-slate-600">{d}</div></div>
            </li>
          ))}
        </ul>
      </section>

      <BusyOverlay show={!!busy} title={busy === "manual" ? "Preparing your facts" : aiOn ? "Gemini is reading your documents" : "Reading your documents"}
        steps={s.steps} hint={aiOn && busy !== "manual" ? "Google Gemini usually needs 20 to 40 seconds for a full set of documents. You only wait once: the result is cached." : undefined} />
      {s.error && <Callout tone="critical" title="Could not read the documents">{s.error} Check that the files are PDF or plain text and try again, or type the facts in yourself.</Callout>}

      <section className="grid gap-6 lg:grid-cols-[1.15fr_1fr]">
        <Card className="p-6">
          <SectionTitle icon={<Upload />} title="Option 1 · Use your own documents"
            sub="Purchase order, supplier quote, invoice or email. PDF or text, up to 6 files." />
          <div role="button" tabIndex={0} aria-label="Choose files to upload" onClick={() => s.input.current?.click()}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); s.input.current?.click(); } }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); s.addFiles(Array.from(e.dataTransfer.files)); }}
            className="cursor-pointer rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-7 text-center transition hover:border-brand-400 hover:bg-brand-50/50">
            <FileUp className="mx-auto h-7 w-7 text-brand-600" />
            <div className="mt-2 text-sm font-semibold text-slate-800">Drop files here, or click to choose</div>
            <div className="text-xs text-slate-500">PDF, TXT or EML, up to 8 MB each</div>
            <input ref={s.input} type="file" multiple accept=".pdf,.txt,.eml,text/plain,application/pdf" className="hidden"
              onChange={(e) => s.addFiles(Array.from(e.target.files ?? []))} />
          </div>
          {s.files.length > 0 && (
            <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200">
              {s.files.map((f, i) => (
                <li key={i} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <span className="flex min-w-0 items-center gap-2"><FileText className="h-4 w-4 shrink-0 text-slate-400" /><span className="truncate">{f.name}</span></span>
                  <button onClick={() => s.removeFile(i)} className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600" aria-label={`Remove ${f.name}`}><Trash2 className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          )}
          <label className="mt-5 block">
            <span className="label">Or paste text, such as an email from the supplier</span>
            <textarea value={s.pasted} onChange={(e) => s.setPasted(e.target.value)} rows={4} className="input mt-1.5 font-mono text-xs"
              placeholder="From: supplier@example.com&#10;Subject: Payment details…" />
          </label>
          <LoadingButton loading={busy === "upload"} loadingText={aiOn ? "Gemini is reading…" : "Reading…"}
            disabled={!!busy || (!s.files.length && !s.pasted.trim())} className="btn-primary mt-4 w-full py-2.5"
            onClick={s.readUploads}>
            <Sparkles className="h-4 w-4" /> {aiOn ? "Read documents with Gemini" : "Read documents"}
          </LoadingButton>
          <p className="mt-2 text-xs text-slate-500">{!s.files.length && !s.pasted.trim() ? "Add a file or paste some text to continue. " : ""}This is a demo: please use made-up documents. Files stay in this session's memory and are never stored.</p>
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<Keyboard />} title="Option 2 · Type the facts in yourself"
            sub="No documents, or the AI isn't available? SolvOrder works just as well from typed numbers." />
          {!s.manual ? (
            <button className="btn-secondary w-full" onClick={() => s.setManual(true)}><Plus className="h-4 w-4" /> Open the form</button>
          ) : (
            <ManualForm busy={!!busy} loading={busy === "manual"} role={role} company={company} onSubmit={s.submitManual} />
          )}
        </Card>
      </section>

      <section id="samples" className="scroll-mt-40">
        <SectionTitle icon={<LayoutList />} title="Option 3 · Try a sample case"
          sub="Made-up businesses and documents. Each case shows a different problem SolvOrder catches." />
        <SampleCarousel packs={s.packs} busy={busy} onPick={s.pickSample} />
      </section>
    </div>
  );
}

type Pay = { label: string; amount: string; day: number; paid: boolean };
const SELLER_FIELDS = ["customer_name", "order_ref", "order_value", "delivery_day", "payment_terms_days", "payment_terms_basis",
  "supplier_name", "late_penalty_pct_per_week", "advance_received", "customer_email", "supplier_email"];
const BUYER_FIELDS = ["customer_name", "order_ref", "order_value", "delivery_day", "supplier_name", "supplier_email", "expected_income", "income_days"];

function ManualForm({ busy, loading, onSubmit, role: initialRole, company }: {
  busy: boolean; loading: boolean; role: Role; company: string;
  onSubmit: (f: Record<string, string>, p: Pay[], role: Role) => void;
}) {
  const [role, setRole] = useState<Role>(initialRole);
  const [f, setF] = useState<Record<string, string>>({
    customer_name: initialRole === "buyer" ? company : "", order_ref: "", order_value: "", delivery_day: "30", payment_terms_days: "30",
    payment_terms_basis: "after_delivery", supplier_name: "", late_penalty_pct_per_week: "", advance_received: "", customer_email: "", supplier_email: "",
    expected_income: "", income_days: "15",
  });
  const switchRole = (r: Role) => { setRole(r); setF({ ...f, customer_name: r === "buyer" ? company : "" }); };
  const keep = role === "buyer" ? BUYER_FIELDS : SELLER_FIELDS;
  const facts = () => Object.fromEntries(Object.entries(f).filter(([k]) => keep.includes(k)));
  const [pays, setPays] = useState([{ label: "Supplier deposit", amount: "", day: 0, paid: false }]);
  const field = (k: string, label: string, ph = "") => (
    <label className="block"><span className="label">{label}</span>
      <input className="input mt-1" value={f[k]} placeholder={ph} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
  );
  return (
    <div className="space-y-3">
      <div>
        <div className="label mb-1.5">In this deal I am the…</div>
        <div className="grid grid-cols-2 gap-2">
          {([["seller", "Seller", "A customer ordered from me"], ["buyer", "Buyer", "A supplier offered me goods"]] as [Role, string, string][]).map(([r, t, d]) => (
            <button key={r} type="button" aria-pressed={role === r} onClick={() => switchRole(r)} className={`rounded-lg border px-3 py-2 text-left transition ${role === r ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-slate-300 hover:border-slate-400"}`}>
              <div className="text-sm font-bold">{t}</div><div className="text-xs text-slate-500">{d}</div>
            </button>
          ))}
        </div>
      </div>
      {role === "buyer" ? (
      <div className="grid gap-3 sm:grid-cols-2">
        {field("supplier_name", "Supplier", "Meghna Fabrics Ltd")}
        {field("supplier_email", "Supplier email", "sales@meghnafabrics.example")}
        {field("order_ref", "Offer / quotation reference", "Q-2045")}
        {field("order_value", "Purchase total (what you pay)", "800000")}
        {field("delivery_day", "Goods arrive by day", "30")}
        {field("customer_name", "Buyer (your company)", company || "Your company")}
        {field("expected_income", "Income you expect from the goods", "0 if none")}
        {field("income_days", "Days after arrival that income comes", "15")}
      </div>
      ) : (
      <div className="grid gap-3 sm:grid-cols-2">
        {field("customer_name", "Customer", "Meridian Retail")}
        {field("order_ref", "Order reference", "PO-1001")}
        {field("order_value", "Order value", "30000")}
        {field("supplier_name", "Supplier", "Brightwave Supplies")}
        {field("customer_email", "Customer email", "ap@meridianretail.example")}
        {field("supplier_email", "Supplier email", "accounts@brightwavesupplies.example")}
        {field("delivery_day", "Delivery day", "30")}
        {field("payment_terms_days", "Customer pays after (days)", "30")}
        <label className="block"><span className="label">Counting from</span>
          <select className="input mt-1" value={f.payment_terms_basis} onChange={(e) => setF({ ...f, payment_terms_basis: e.target.value })}>
            <option value="after_delivery">Delivery</option><option value="after_invoice">Invoice</option><option value="after_order">Order date</option>
          </select></label>
        {field("late_penalty_pct_per_week", "Late penalty % / week", "1%")}
        {field("advance_received", "Advance the customer already paid you", "0 if none")}
      </div>
      )}
      <div>
        <div className="label mb-1">What you pay the supplier</div>
        <div className="mb-1 grid grid-cols-[1fr_96px_64px_auto_28px] gap-2 text-[11px] text-slate-500"><span>What for</span><span>Amount</span><span>Day</span><span>Paid?</span><span /></div>
        {pays.map((p, i) => (
          <div key={i} className="mb-2 grid grid-cols-[1fr_110px_80px_auto_32px] items-center gap-2">
            <input className="input" aria-label="Payment" value={p.label} onChange={(e) => setPays(pays.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
            <input className="input" aria-label="Amount" placeholder="12000" value={p.amount} onChange={(e) => setPays(pays.map((x, j) => j === i ? { ...x, amount: e.target.value } : x))} />
            <input className="input" aria-label="Day" type="number" min={0} value={p.day} disabled={p.paid} onChange={(e) => setPays(pays.map((x, j) => j === i ? { ...x, day: Number(e.target.value) } : x))} />
            <label className="flex items-center gap-1 text-xs" title="Already paid before today: it is already out of your cash"><input type="checkbox" className="accent-teal-600" checked={p.paid} onChange={(e) => setPays(pays.map((x, j) => j === i ? { ...x, paid: e.target.checked } : x))} />paid</label>
            <button className="text-slate-400 hover:text-rose-600" aria-label="Remove payment" onClick={() => setPays(pays.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}
        <button className="btn-quiet -ml-2" onClick={() => setPays([...pays, { label: "Payment", amount: "", day: 0, paid: false }])}><Plus className="h-4 w-4" /> Add payment</button>
      </div>
      <LoadingButton loading={loading} loadingText="Checking…" disabled={busy} className="btn-primary w-full" onClick={() => onSubmit(facts(), pays, role)}>Use these facts</LoadingButton>
      <p className="text-xs text-slate-500">Your cash position, reserve and lenders come from the business profile, which you can edit on the next screen.</p>
    </div>
  );
}
