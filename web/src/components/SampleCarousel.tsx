import { ChevronLeft, ChevronRight, Download, ShieldAlert } from "lucide-react";
import type { Pack } from "../api";
import { useCarousel } from "../hooks/useCarousel";
import { LoadingButton } from "./ui";

const BADGE: Record<string, string> = {
  Risk: "bg-sky-50 text-sky-800 ring-sky-200", Fraud: "bg-rose-50 text-rose-800 ring-rose-200",
  Security: "bg-violet-50 text-violet-800 ring-violet-200", Integrity: "bg-amber-50 text-amber-800 ring-amber-200",
  Role: "bg-emerald-50 text-emerald-800 ring-emerald-200",
};

/** Sample cases as a horizontal carousel. "Use this case" calls the same onPick as the old list. */
export function SampleCarousel({ packs, busy, onPick }: { packs: Pack[]; busy: string | null; onPick: (id: string) => void }) {
  const c = useCarousel(packs.length);
  const arrow = "grid h-9 w-9 place-items-center rounded-full border border-slate-300 bg-white text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 disabled:cursor-default disabled:opacity-35";
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-sm text-slate-500" aria-live="polite">{packs.length > 0 && <>Case <b className="text-slate-800">{c.index + 1}</b> of {packs.length}</>}</span>
        <div className="flex gap-2">
          <button className={arrow} onClick={c.prev} disabled={c.atStart} aria-label="Previous sample case"><ChevronLeft className="h-5 w-5" /></button>
          <button className={arrow} onClick={c.next} disabled={c.atEnd} aria-label="Next sample case"><ChevronRight className="h-5 w-5" /></button>
        </div>
      </div>

      <div ref={c.track} tabIndex={0} onKeyDown={c.onKeyDown} role="region" aria-roledescription="carousel" aria-label="Sample cases (use the left and right arrow keys)"
        className="no-scrollbar -mx-1 flex snap-x snap-mandatory scroll-px-1 gap-4 overflow-x-auto px-1 pb-2 pt-1 focus-visible:outline-offset-4">
        {packs.map((p, i) => (
          <article key={p.id} aria-roledescription="slide" aria-label={`${i + 1} of ${packs.length}: ${p.title}`}
            className="card flex w-[86%] shrink-0 snap-start flex-col p-5 sm:w-[58%] lg:w-[44%] xl:w-[34%]">
            <div className="flex items-center justify-between gap-2">
              <span className={`chip ring-1 ring-inset ${BADGE[p.badge] ?? "bg-slate-50 text-slate-700 ring-slate-200"}`}>{p.badge === "Fraud" && <ShieldAlert className="h-3 w-3" />}{p.badge}</span>
              <span className="text-xs text-slate-400">{i + 1}/{packs.length}</span>
            </div>
            <h3 className="mt-3 text-lg font-semibold leading-snug text-slate-900">{p.title}</h3>
            <div className="text-xs text-slate-500">{p.subtitle}</div>
            <p className="mt-3 text-sm leading-relaxed text-slate-700">{p.story}</p>
            <div className="mt-3 text-[13px] font-semibold text-slate-600">What to look for</div>
            <ul className="mt-1 flex-1 space-y-1 text-[13px] text-slate-600">
              {p.look_for.map((l) => <li key={l} className="flex gap-2"><span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400" />{l}</li>)}
            </ul>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {p.files.map((f) => (
                <a key={f} href={`/api/samples/${p.id}/${f}`} target="_blank" rel="noreferrer" title="Open this sample document"
                  className="chip bg-slate-100 text-slate-600 hover:bg-slate-200"><Download className="h-3 w-3" />{f.replace(".pdf", "")}</a>
              ))}
            </div>
            <LoadingButton loading={busy === p.id} loadingText="Reading…" disabled={!!busy} className="btn-secondary mt-4"
              onClick={() => onPick(p.id)}>
              Use this case
            </LoadingButton>
          </article>
        ))}
      </div>

      {packs.length > 1 && (
        <div className="mt-3 flex justify-center gap-1.5" role="group" aria-label="Choose a sample case">
          {packs.map((p, i) => (
            <button key={p.id} onClick={() => c.goTo(i)} aria-label={`Show case ${i + 1}: ${p.title}`} aria-current={i === c.index ? "true" : undefined}
              className="grid h-6 w-6 place-items-center">
              <span className={`block h-2 rounded-full transition-all ${i === c.index ? "w-5 bg-brand-600" : "w-2 bg-slate-300 hover:bg-slate-400"}`} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
