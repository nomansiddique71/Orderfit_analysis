import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Globe, HelpCircle, Search, TriangleAlert, XCircle } from "lucide-react";
import { post } from "../api";
import { Card, Pill, SectionTitle, Spinner } from "./ui";

interface PartyView {
  role: "customer" | "supplier"; company: string; email: string; domain: string;
  rules: { kind: "ok" | "warn" | "bad"; text: string }[];
  google: { found: string; official_domain: string; email_domain_matches: string; summary: string } | null;
}
interface CompaniesView { parties: PartyView[]; mode: "on" | "off" | "error"; note: string; sources: { title: string; uri: string }[] }

const ICON = {
  ok: <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />,
  warn: <TriangleAlert className="h-4 w-4 shrink-0 text-amber-600" />,
  bad: <XCircle className="h-4 w-4 shrink-0 text-rose-600" />,
};

function GoogleVerdict({ g }: { g: NonNullable<PartyView["google"]> }) {
  const found = g.found === "yes", match = g.email_domain_matches;
  return (
    <div className="space-y-1 text-sm">
      <div className="flex flex-wrap gap-1.5">
        {found ? <Pill tone="green"><Globe className="h-3 w-3" /> Found on Google</Pill>
          : g.found === "no" ? <Pill tone="amber"><HelpCircle className="h-3 w-3" /> No public record found</Pill>
          : <Pill tone="slate">Unclear on Google</Pill>}
        {match === "yes" && <Pill tone="green">Email domain belongs to them</Pill>}
        {match === "no" && <Pill tone="red">Email domain is not theirs</Pill>}
        {g.official_domain && <Pill tone="slate">Official site: {g.official_domain}</Pill>}
      </div>
      {g.summary && <p className="text-xs text-slate-600">{g.summary}</p>}
    </div>
  );
}

/** Customer and supplier: name + email, checked by rules and (optionally) on Google by Gemini. */
export function CompanyCheck({ refreshKey }: { refreshKey: string }) {
  const [v, setV] = useState<CompaniesView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setV(null); setErr(null);
    post<CompaniesView>("/api/companies").then(setV).catch((e) => setErr((e as Error).message));
  }, [refreshKey]);

  return (
    <Card className="p-6">
      <SectionTitle icon={<Search className="h-5 w-5" />} title="Who are you dealing with?"
        sub="Company names and email addresses from the documents. Rules check the emails; Gemini can also look the companies up on Google." />
      {!v && !err && <Spinner text="Checking the companies (Gemini may be searching Google)…" />}
      {err && <p className="text-sm text-rose-700">{err}</p>}
      {v && v.parties.length === 0 && <p className="text-sm text-slate-500">No company names or emails were found in the documents. Add them on this screen to have them checked.</p>}
      {v && v.parties.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {v.parties.map((p) => (
            <div key={p.role} className="rounded-xl border border-slate-200 p-4">
              <div className="label">{p.role === "supplier" ? "Supplier (you pay them)" : "Customer (they pay you)"}</div>
              <div className="font-bold text-slate-900">{p.company || "Name not found"}</div>
              <div className="font-mono text-xs text-slate-500">{p.email || "no email found"}</div>
              <ul className="mt-2 space-y-1">{p.rules.map((r, i) => <li key={i} className="flex gap-2 text-sm">{ICON[r.kind]}{r.text}</li>)}</ul>
              <div className="mt-3 border-t border-slate-100 pt-3">
                {p.google ? <GoogleVerdict g={p.google} /> : <p className="text-xs text-slate-500">{v.mode === "on" ? "Gemini returned no result for this company." : "Google check not run."}</p>}
              </div>
            </div>
          ))}
        </div>
      )}
      {v && (
        <div className="mt-3 text-xs text-slate-500">
          {v.note}
          {v.mode === "on" && v.parties.some((p) => p.google?.found === "no") && " The sample companies are invented, so 'no public record' is expected for them; for a real order it is a reason to verify before paying."}
          {v.sources.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-2">Sources: {v.sources.map((s) => (
              <a key={s.uri} href={s.uri} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-brand-700 hover:underline">{s.title}<ExternalLink className="h-3 w-3" /></a>))}</div>
          )}
        </div>
      )}
    </Card>
  );
}
