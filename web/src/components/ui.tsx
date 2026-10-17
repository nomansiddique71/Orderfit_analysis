import { useEffect, useState, useSyncExternalStore, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertOctagon, AlertTriangle, CheckCircle2, Info, Loader2 } from "lucide-react";
import { pendingCount, subscribePending, type Severity } from "../api";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function SectionTitle({ icon, title, sub, right }: { icon?: ReactNode; title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        {icon && <div className="mt-0.5 rounded-xl bg-brand-50 p-2 text-brand-700">{icon}</div>}
        <div>
          <h3 className="text-base font-bold text-slate-900">{title}</h3>
          {sub && <p className="mt-0.5 text-sm text-slate-500">{sub}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

const SEV = {
  critical: { box: "border-rose-200 bg-rose-50 text-rose-900", icon: <AlertOctagon className="h-5 w-5 text-rose-600" /> },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-900", icon: <AlertTriangle className="h-5 w-5 text-amber-600" /> },
  info: { box: "border-sky-200 bg-sky-50 text-sky-900", icon: <Info className="h-5 w-5 text-sky-600" /> },
  success: { box: "border-emerald-200 bg-emerald-50 text-emerald-900", icon: <CheckCircle2 className="h-5 w-5 text-emerald-600" /> },
};

export function Callout({ tone, title, children, action }: { tone: Severity | "success"; title?: ReactNode; children?: ReactNode; action?: ReactNode }) {
  const s = SEV[tone];
  return (
    <div className={`flex gap-3 rounded-xl border p-4 ${s.box}`}>
      <div className="shrink-0">{s.icon}</div>
      <div className="min-w-0 flex-1 text-sm leading-relaxed">
        {title && <div className="mb-0.5 font-semibold">{title}</div>}
        {children}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}

export function Stat({ label, value, sub, tone = "default" }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "default" | "good" | "bad" | "warn" }) {
  const color = { default: "text-slate-900", good: "text-emerald-700", bad: "text-rose-700", warn: "text-amber-700" }[tone];
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className={`mt-1 text-2xl font-bold tracking-tight ${color}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function Pill({ tone, children }: { tone: "green" | "red" | "amber" | "slate" | "blue" | "violet"; children: ReactNode }) {
  const c = {
    green: "bg-emerald-100 text-emerald-800", red: "bg-rose-100 text-rose-800", amber: "bg-amber-100 text-amber-800",
    slate: "bg-slate-100 text-slate-700", blue: "bg-sky-100 text-sky-800", violet: "bg-violet-100 text-violet-800",
  }[tone];
  return <span className={`chip ${c}`}>{children}</span>;
}

export function Spinner({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-slate-600">
      <Loader2 className="h-5 w-5 animate-spin text-brand-600" /> {text}
    </div>
  );
}

export function Segmented<T extends string | number>({ value, options, onChange }: {
  value: T; options: { value: T; label: string; hint?: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-xl bg-slate-100 p-1">
      {options.map((o) => (
        <button key={String(o.value)} title={o.hint} onClick={() => onChange(o.value)}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${value === o.value ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------- loading feedback

/** Number of API requests currently in flight (any screen). */
export function usePending() {
  return useSyncExternalStore(subscribePending, pendingCount);
}

/** Thin animated bar fixed to the top of the window while any request runs. */
export function TopProgress() {
  const n = usePending();
  return (
    <div aria-hidden={n === 0} className={`pointer-events-none fixed inset-x-0 top-0 z-[60] h-1 overflow-hidden transition-opacity duration-300 ${n ? "opacity-100" : "opacity-0"}`}>
      <div className="progress-indeterminate h-full w-1/3 rounded-full bg-gradient-to-r from-brand-500 via-teal-300 to-brand-600" />
    </div>
  );
}

/** Button that shows a spinner + text while its action runs, and can't be double-clicked. */
export function LoadingButton({ loading, loadingText, children, disabled, className = "btn-primary", ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean; loadingText?: string }) {
  return (
    <button {...rest} className={className} disabled={disabled || loading} aria-busy={loading}>
      {loading ? <><Loader2 className="h-4 w-4 animate-spin" />{loadingText ?? "Working…"}</> : children}
    </button>
  );
}

/** Full-screen progress panel for long operations (e.g. Gemini reading documents).
 *  Appears only if the operation lasts longer than `delay` ms, so quick actions don't flash. */
export function BusyOverlay({ show, title, steps, hint, delay = 450 }: {
  show: boolean; title: string; steps: string[]; hint?: string; delay?: number;
}) {
  const [visible, setVisible] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!show) { setVisible(false); setElapsed(0); return; }
    const start = Date.now();
    const t = setTimeout(() => setVisible(true), delay);
    const i = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 250);
    return () => { clearTimeout(t); clearInterval(i); };
  }, [show, delay]);
  if (!show || !visible) return null;
  const stepIndex = Math.min(steps.length - 1, Math.floor(elapsed / 4));
  return (
    <div role="status" aria-live="polite" className="fixed inset-0 z-50 grid place-items-center bg-ink-950/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-3xl bg-white p-7 shadow-2xl">
        <div className="flex items-center gap-3">
          <div className="relative grid h-12 w-12 place-items-center">
            <span className="absolute inset-0 animate-ping rounded-full bg-brand-100" />
            <Loader2 className="relative h-8 w-8 animate-spin text-brand-600" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-900">{title}</div>
            <div className="text-xs text-slate-500">{elapsed}s elapsed</div>
          </div>
        </div>
        <ol className="mt-5 space-y-2">
          {steps.map((s, i) => (
            <li key={s} className={`flex items-center gap-2 text-sm transition ${i < stepIndex ? "text-slate-400" : i === stepIndex ? "font-semibold text-slate-900" : "text-slate-300"}`}>
              {i < stepIndex ? <CheckCircle2 className="h-4 w-4 text-brand-600" />
                : i === stepIndex ? <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
                : <span className="h-4 w-4 rounded-full border-2 border-slate-200" />}
              {s}
            </li>
          ))}
        </ol>
        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div className="progress-indeterminate h-full w-1/3 rounded-full bg-brand-500" />
        </div>
        {hint && <p className="mt-3 text-xs text-slate-500">{hint}</p>}
      </div>
    </div>
  );
}

/** Dims content and shows an "Updating…" badge while results recalculate. */
export function Updating({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <div className="relative">
      {active && (
        <div className="sticky top-24 z-20 flex justify-center">
          <span className="chip absolute -top-2 bg-ink-900 px-3 py-1 text-white shadow-lg"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Updating results…</span>
        </div>
      )}
      <div className={`transition-opacity duration-200 ${active ? "pointer-events-none opacity-50" : "opacity-100"}`}>{children}</div>
    </div>
  );
}
