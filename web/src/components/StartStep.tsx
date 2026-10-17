import { useEffect, useRef, useState } from "react";
import { Download, FileText, FileUp, Keyboard, Plus, ShieldAlert, Sparkles, Trash2, Upload } from "lucide-react";
import { get, post, upload, type DocView, type Pack } from "../api";
import { BusyOverlay, Callout, Card, LoadingButton, SectionTitle } from "./ui";

const BADGE: Record<string, string> = {
  Risk: "bg-sky-100 text-sky-800", Fraud: "bg-rose-100 text-rose-800",
  Security: "bg-violet-100 text-violet-800", Integrity: "bg-amber-100 text-amber-800",
};

export function StartStep({ onLoaded, onHowItWorks, aiOn }: {
  onLoaded: (v: DocView) => void; onHowItWorks: () => void; aiOn: boolean;
}) {
  const [packs, setPacks] = useState<Pack[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [pasted, setPasted] = useState("");
  const [manual, setManual] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { get<Pack[]>("/api/samples").then(setPacks).catch(() => setPacks([])); }, []);

  async function run(label: string, fn: () => Promise<DocView>) {
    setBusy(label); setError(null);
    try { onLoaded(await fn()); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  const steps = busy === "manual"
    ? ["Checking the facts you entered", "Preparing them for review"]
    : aiOn
      ? ["Opening the documents", "Gemini is reading each document", "Checking every quoted value against the source text",
         "Running fraud and consistency checks", "Preparing the facts for your review"]
      : ["Opening the documents", "Reading them with the built-in parser", "Running fraud and consistency checks",
         "Preparing the facts for your review"];

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-ink-900 via-ink-800 to-brand-700 p-8 text-white shadow-lg">
        <div className="max-w-3xl">
          <div className="chip bg-white/10 text-brand-100"><Sparkles className="h-3.5 w-3.5" /> AI decision agent for small-business cash</div>
          <h1 className="mt-3 text-3xl font-extrabold leading-tight md:text-4xl">Got a big order? Find out if your cash can carry it, before you say yes.</h1>
          <p className="mt-3 text-slate-200">
            SolvOrder reads your purchase order and supplier documents with Google Gemini, checks them for fraud,
            simulates your cash every day, and recommends the safest way to accept, or tells you plainly to decline.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <button onClick={onHowItWorks} className="btn bg-white text-ink-900 hover:bg-brand-50">How it works</button>
            <a href="#samples" className="btn border border-white/30 text-white hover:bg-white/10">Try a sample case ↓</a>
          </div>
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {[["Risk", "Exact day-by-day cash, reserve breaches and late-payment stress tests"],
            ["Fraud", "Changed bank details, mismatched invoices and hidden AI instructions flagged"],
            ["Decision", "Options ranked by what matters to you; nothing runs without your approval"]].map(([t, d]) => (
            <div key={t} className="rounded-2xl bg-white/10 p-4 backdrop-blur">
              <div className="font-bold">{t}</div><div className="text-sm text-slate-200">{d}</div>
            </div>
          ))}
        </div>
      </div>

      <BusyOverlay show={!!busy} title={busy === "manual" ? "Preparing your facts" : aiOn ? "Gemini is reading your documents" : "Reading your documents"}
        steps={steps} hint={aiOn && busy !== "manual" ? "Google Gemini usually needs 20 to 40 seconds for a full set of documents. You only wait once: the result is cached." : undefined} />
      {error && <Callout tone="critical" title="Could not read the documents">{error}</Callout>}

      <section id="samples">
        <SectionTitle icon={<FileText className="h-5 w-5" />} title="Option 1 · Try a sample case"
          sub="Synthetic businesses and documents. Each case shows a different risk SolvOrder handles." />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {packs.map((p) => (
            <Card key={p.id} className="flex flex-col p-5 transition hover:shadow-md">
              <span className={`chip w-fit ${BADGE[p.badge] ?? "bg-slate-100"}`}>{p.badge === "Fraud" && <ShieldAlert className="h-3 w-3" />}{p.badge}</span>
              <div className="mt-2 text-base font-bold text-slate-900">{p.title}</div>
              <div className="text-xs text-slate-500">{p.subtitle}</div>
              <p className="mt-2 text-sm text-slate-600">{p.story}</p>
              <ul className="mt-2 flex-1 space-y-1 text-xs text-slate-600">
                {p.look_for.map((l) => <li key={l} className="flex gap-1.5"><span className="text-brand-600">✓</span>{l}</li>)}
              </ul>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {p.files.map((f) => (
                  <a key={f} href={`/api/samples/${p.id}/${f}`} target="_blank" rel="noreferrer"
                    className="chip bg-slate-100 text-slate-600 hover:bg-slate-200"><Download className="h-3 w-3" />{f.replace(".pdf", "")}</a>
                ))}
              </div>
              <LoadingButton loading={busy === p.id} loadingText="Reading…" disabled={!!busy} className="btn-primary mt-4"
                onClick={() => run(p.id, () => post<DocView>("/api/documents/sample", { pack: p.id }))}>
                Use this case
              </LoadingButton>
            </Card>
          ))}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <SectionTitle icon={<Upload className="h-5 w-5" />} title="Option 2 · Use your own documents"
            sub="Purchase order, supplier quote, invoice or email. PDF or text, up to 6 files." />
          <div onClick={() => input.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); setFiles((f) => [...f, ...Array.from(e.dataTransfer.files)].slice(0, 6)); }}
            className="cursor-pointer rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 p-6 text-center transition hover:border-brand-500 hover:bg-brand-50/40">
            <FileUp className="mx-auto h-8 w-8 text-brand-600" />
            <div className="mt-2 text-sm font-semibold text-slate-700">Drop files here or click to choose</div>
            <div className="text-xs text-slate-500">PDF, TXT or EML · max 8 MB each</div>
            <input ref={input} type="file" multiple accept=".pdf,.txt,.eml,text/plain,application/pdf" className="hidden"
              onChange={(e) => setFiles((f) => [...f, ...Array.from(e.target.files ?? [])].slice(0, 6))} />
          </div>
          {files.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {files.map((f, i) => (
                <li key={i} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                  <span className="flex items-center gap-2 truncate"><FileText className="h-4 w-4 text-slate-400" />{f.name}</span>
                  <button onClick={() => setFiles(files.filter((_, j) => j !== i))} className="text-slate-400 hover:text-rose-600"><Trash2 className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4">
            <div className="label mb-1">…or paste text (e.g. an email from the supplier)</div>
            <textarea value={pasted} onChange={(e) => setPasted(e.target.value)} rows={4} className="input font-mono text-xs"
              placeholder="From: supplier@example.com&#10;Subject: Payment details…" />
          </div>
          <LoadingButton loading={busy === "upload"} loadingText={aiOn ? "Gemini is reading…" : "Reading…"}
            disabled={!!busy || (!files.length && !pasted.trim())} className="btn-primary mt-4 w-full"
            onClick={() => run("upload", () => upload(files, pasted))}>
            <Sparkles className="h-4 w-4" /> {aiOn ? "Read documents with Gemini" : "Read documents"}
          </LoadingButton>
          <p className="mt-2 text-xs text-slate-500">Demo: use synthetic documents only. Files stay in this session's memory and are never stored.</p>
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<Keyboard className="h-5 w-5" />} title="Option 3 · Enter the facts yourself"
            sub="No documents, or AI unavailable? The engine works fully from typed facts." />
          {!manual ? (
            <button className="btn-secondary w-full" onClick={() => setManual(true)}><Plus className="h-4 w-4" /> Open the manual form</button>
          ) : (
            <ManualForm busy={!!busy} loading={busy === "manual"} onSubmit={(facts, pays) => run("manual", () => post<DocView>("/api/documents/manual", { facts, supplier_payments: pays }))} />
          )}
        </Card>
      </section>
    </div>
  );
}

function ManualForm({ busy, loading, onSubmit }: { busy: boolean; loading: boolean; onSubmit: (f: Record<string, string>, p: { label: string; amount: string; day: number; paid: boolean }[]) => void }) {
  const [f, setF] = useState<Record<string, string>>({
    customer_name: "", order_ref: "", order_value: "", delivery_day: "30", payment_terms_days: "30",
    payment_terms_basis: "after_delivery", supplier_name: "", late_penalty_pct_per_week: "", advance_received: "", customer_email: "", supplier_email: "",
  });
  const [pays, setPays] = useState([{ label: "Supplier deposit", amount: "", day: 0, paid: false }]);
  const field = (k: string, label: string, ph = "") => (
    <label className="block"><span className="label">{label}</span>
      <input className="input mt-1" value={f[k]} placeholder={ph} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
  );
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
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
      <div>
        <div className="label mb-1">What you pay the supplier (amount, day, already paid?)</div>
        {pays.map((p, i) => (
          <div key={i} className="mb-2 grid grid-cols-[1fr_110px_80px_auto_32px] items-center gap-2">
            <input className="input" value={p.label} onChange={(e) => setPays(pays.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
            <input className="input" placeholder="12000" value={p.amount} onChange={(e) => setPays(pays.map((x, j) => j === i ? { ...x, amount: e.target.value } : x))} />
            <input className="input" type="number" min={0} value={p.day} disabled={p.paid} onChange={(e) => setPays(pays.map((x, j) => j === i ? { ...x, day: Number(e.target.value) } : x))} />
            <label className="flex items-center gap-1 text-xs" title="Already paid before today: it is already out of your cash"><input type="checkbox" className="accent-teal-600" checked={p.paid} onChange={(e) => setPays(pays.map((x, j) => j === i ? { ...x, paid: e.target.checked } : x))} />paid</label>
            <button className="text-slate-400 hover:text-rose-600" onClick={() => setPays(pays.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}
        <button className="text-sm font-semibold text-brand-700" onClick={() => setPays([...pays, { label: "Payment", amount: "", day: 0, paid: false }])}>+ Add payment</button>
      </div>
      <LoadingButton loading={loading} loadingText="Checking…" disabled={busy} className="btn-primary w-full" onClick={() => onSubmit(f, pays)}>Use these facts</LoadingButton>
      <p className="text-xs text-slate-500">Your cash position, reserve and lenders come from the business profile, which you can edit on the next screen.</p>
    </div>
  );
}
