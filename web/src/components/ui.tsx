import type { ReactNode } from "react";
import { AlertOctagon, AlertTriangle, CheckCircle2, Info, Loader2 } from "lucide-react";
import type { Severity } from "../api";

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
