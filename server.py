"""SolvOrder API (FastAPI) + static React UI.

Run locally:  uvicorn server:app --reload --port 8000
The React build in web/dist is served at "/"; the API lives under /api.

Design rules carried over from the engine:
  * Gemini proposes (reads documents, explains, polishes); engine.py verifies.
  * Gemini is only called on an explicit action (upload, Ask, Explain,
    Polish) and every call is cached; re-analysing never calls the model.
  * Every tool call is written to the session's operation log with its tier.
  * Sandbox actions (T2) need an owner approval bound to the exact plan
    version, and are refused while a fraud flag is unresolved.

Session state (approvals, sandbox, log) lives in memory per browser session;
Cloud Run must use session affinity. Nothing is persisted.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent
import case_builder
import doc_extract
import engine
import gemini_client
from docmodel import FACT_LABELS, SIMULATION_FACTS, Fact, Facts, SupplierPayment
from sandbox import (OVERRIDE_TAG, Approval, MockLenderPortal, MockOutbox, OperationLog,
                     PermissionGate, SimulatedBank, execute_plan)

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
WEB_DIST = ROOT / "web" / "dist"
MAX_SESSIONS = 300
MAX_FILES = 6

app = FastAPI(title="SolvOrder API", version="1.0")


# ------------------------------------------------------------------ session


@dataclass
class Session:
    id: str
    created: float = field(default_factory=time.time)
    log: OperationLog = field(default_factory=OperationLog)
    bank: SimulatedBank = field(default_factory=SimulatedBank)
    outbox: MockOutbox = field(default_factory=MockOutbox)
    approvals: dict = field(default_factory=dict)  # approval_id -> Approval
    active_approval: str | None = None
    executed: dict | None = None
    docs: list = field(default_factory=list)
    facts: Facts | None = None
    mode: str = ""
    note: str = ""
    profile: case_builder.BusinessProfile | None = None
    sample_id: str | None = None
    resolved: dict = field(default_factory=dict)  # flag code -> owner note
    last: dict = field(default_factory=dict)  # run, case, pay_day, versions
    ai_cache: dict = field(default_factory=dict)

    @property
    def gate(self) -> PermissionGate:
        return PermissionGate(self.log)


_SESSIONS: dict[str, Session] = {}
_LOCK = threading.Lock()


def _new_session() -> Session:
    with _LOCK:
        if len(_SESSIONS) >= MAX_SESSIONS:
            oldest = min(_SESSIONS.values(), key=lambda s: s.created)
            _SESSIONS.pop(oldest.id, None)
        s = Session(secrets.token_urlsafe(16))
        _SESSIONS[s.id] = s
        return s


def _session(session_id: str) -> Session:
    s = _SESSIONS.get(session_id or "")
    if s is None:
        raise HTTPException(404, "Session expired. Reload the page to start again.")
    return s


# ---------------------------------------------------------------- helpers


def num(x) -> float | None:
    return None if x is None else float(x)


def _fact_json(key: str, f: Fact) -> dict:
    return {"key": key, "label": FACT_LABELS.get(key, key), "value": f.value, "source": f.source,
            "span": f.span, "confidence": round(f.confidence, 2), "verified": f.verified,
            "note": f.note, "simulation": key in SIMULATION_FACTS,
            "needs_review": key in SIMULATION_FACTS and f.present and
            (f.confidence < doc_extract.LOW_CONFIDENCE or not f.verified)}


def _documents_view(s: Session) -> dict:
    f = s.facts
    stage = doc_extract.to_document_stage(f, s.docs, s.mode, s.note, resolved=s.resolved)
    return {
        "mode": s.mode, "note": s.note, "sample_id": s.sample_id,
        "documents": [{"doc_id": d.doc_id, "filename": d.filename, "kind": d.kind,
                       "scanned": not d.has_text, "chars": len(d.text),
                       "text": d.text[:6000]} for d in s.docs],
        "facts": [_fact_json(k, v) for k, v in f.scalars().items()],
        "supplier_payments": [{"label": p.label, "amount": _fact_json("amount", p.amount),
                               "day": _fact_json("day", p.day)} for p in f.supplier_payments],
        "line_items": [{"description": li.description, "amount": li.amount.value,
                        "source": li.amount.source} for li in f.line_items],
        "bank_details": [{"source": b.source, "payee": b.payee, "bank": b.bank_name,
                          "account": b.account_number, "verified": b.verified}
                         for b in f.bank_details],
        "flags": [_flag_json(x) for x in stage.integrity],
        "profile": s.profile.to_json() if s.profile else None,
    }


def _flag_json(x) -> dict:
    return {"code": x.code, "severity": x.severity, "title": x.title, "message": x.message,
            "documents": x.documents, "blocks_execution": x.blocks_execution,
            "resolved": x.resolved, "resolution_note": x.resolution_note,
            "category": x.category}


def _consents(r) -> list[str]:
    return [c for c, on in (("customer", r.depends_on_customer_consent),
                            ("supplier", r.depends_on_supplier_consent)) if on]


def _plan_json(r, run, version: str) -> dict:
    t = r.tolerance
    return {
        "id": r.plan.id, "label": r.plan.label, "version": version,
        "feasible": r.feasible, "robust": r.robust, "reserve_ok": r.reserve_ok,
        "min_balance": num(r.min_balance), "min_day": r.min_day,
        "first_breach_day": r.first_breach_day, "stress_fail_day": r.stress_fail_day,
        "financing_cost": num(r.financing_cost), "net_margin": num(r.net_margin),
        "gross_margin": num(r.gross_margin), "consents": _consents(r),
        "advance_pct": num(r.plan.advance_pct), "supplier_extension": r.plan.supplier_extension,
        "financing": ({"id": r.plan.financing.id, "lender": r.plan.financing.lender,
                       "principal": num(r.plan.financing.principal),
                       "terms": r.plan.financing.terms_text(),
                       "draw_day": r.plan.financing.draw_day,
                       "repay_day": r.plan.financing.repay_day}
                      if r.plan.financing else None),
        "violations": r.violations,
        "tolerance": ({"kind": t.kind, "days": t.days, "label": t.label,
                       "last_safe_pay_day": t.last_safe_pay_day,
                       "survives": {str(d): t.survives(d) for d in agent.STRESS_OPTIONS}}
                      if t else None),
        "path": [{"day": d, "low": num(r.low_path.get(d, b)), "end": num(b)}
                 for d, b in r.path.items()],
        "recommended": r.plan.id == run.winner.plan.id,
    }


def _version(sig: str, r) -> str:
    return hashlib.sha256(f"{sig}|{r.plan.id}|{r.min_balance}|{r.net_margin}".encode()
                          ).hexdigest()[:10]


def _headline(run, case, gap) -> str:
    w, asis = run.winner, run.results["accept-as-is"]
    if run.no_plan_survives:
        return ("No way of accepting this order keeps your cash above the reserve. "
                "Decline, or ask for one of the changes below.")
    if asis.reserve_ok and not asis.violations:
        return "You can accept this order as it is: your cash stays above the reserve every day."
    if w.plan.id == "decline":
        return "Declining is the only safe choice with the options available."
    return (f"Accepting as-is would push cash below your reserve on day "
            f"{asis.first_breach_day} for {gap.days} days (short by {gap.amount:,.0f}). "
            f"Recommended: {w.plan.label.replace('Accept: ', '').lower()}.")


# ------------------------------------------------------------------- API


@app.get("/api/health")
def health():
    return {"ok": True, "ai": gemini_client.backend_label(),
            "gemini": gemini_client.gemini_available()}


@app.post("/api/session")
def create_session():
    s = _new_session()
    s.log.append("session_start", "T0", {}, None, "new SolvOrder session")
    return {"session_id": s.id}


def _packs() -> list[dict]:
    return json.loads((SAMPLES / "packs.json").read_text())


@app.get("/api/samples")
def samples():
    return _packs()


@app.get("/api/samples/{pack}/{filename}")
def sample_file(pack: str, filename: str):
    meta = next((p for p in _packs() if p["id"] == pack), None)
    if meta is None or filename not in meta["files"]:  # whitelist: no path traversal
        raise HTTPException(404, "No such sample file")
    return FileResponse(SAMPLES / pack / filename, media_type="application/pdf",
                        filename=filename)


def _default_profile() -> case_builder.BusinessProfile:
    return case_builder.profile_from_json(json.loads((SAMPLES / "clean" / "profile.json").read_text()))


def _ingest(s: Session, docs: list, profile, sample_id: str | None) -> dict:
    s.docs, s.sample_id, s.resolved = docs, sample_id, {}
    s.profile = profile or s.profile or _default_profile()
    s.facts, s.mode, s.note = doc_extract.extract_facts(docs)
    s.last, s.approvals, s.active_approval, s.executed = {}, {}, None, None
    s.log.append("extract_fields", "T0", {"documents": [d.filename for d in docs]}, None,
                 f"{len(docs)} document(s) read via {s.mode}")
    return _documents_view(s)


class SampleReq(BaseModel):
    session_id: str
    pack: str


@app.post("/api/documents/sample")
def load_sample(req: SampleReq):
    s = _session(req.session_id)
    meta = next((p for p in _packs() if p["id"] == req.pack), None)
    if meta is None:
        raise HTTPException(404, "Unknown sample")
    docs = [doc_extract.read_upload(f"DOC-{i}", name, (SAMPLES / req.pack / name).read_bytes())
            for i, name in enumerate(meta["files"], 1)]
    profile = case_builder.profile_from_json(
        json.loads((SAMPLES / req.pack / "profile.json").read_text()))
    return _ingest(s, docs, profile, req.pack)


@app.post("/api/documents/upload")
async def upload(session_id: str = Form(...), files: list[UploadFile] = File(default=[]),
                 pasted: str = Form(default=""), pasted_title: str = Form(default="Pasted text")):
    s = _session(session_id)
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload at most {MAX_FILES} files at a time.")
    docs = []
    try:
        for f in files:
            data = await f.read()
            docs.append(doc_extract.read_upload(f"DOC-{len(docs) + 1}", f.filename or "file", data))
        if pasted.strip():
            if len(pasted) > 50_000:
                raise ValueError("Pasted text is longer than 50,000 characters.")
            docs.append(doc_extract.from_text(f"DOC-{len(docs) + 1}", pasted_title[:80], pasted))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not docs:
        raise HTTPException(400, "Add at least one file or paste some text.")
    return _ingest(s, docs, None, None)


class ManualReq(BaseModel):
    session_id: str
    facts: dict[str, str] = Field(default_factory=dict)
    supplier_payments: list[dict] = Field(default_factory=list)


@app.post("/api/documents/manual")
def manual(req: ManualReq):
    """X-05: AI unavailable or no documents -- the owner types the facts."""
    s = _session(req.session_id)
    f = Facts()
    for k, v in req.facts.items():
        if k in Facts.SCALAR_FIELDS and str(v).strip():
            setattr(f, k, Fact(str(v)[:200], "OWNER", "entered by the owner", 1.0, True))
    for p in req.supplier_payments[:12]:
        f.supplier_payments.append(SupplierPayment(
            str(p.get("label", "Supplier payment"))[:80],
            Fact(str(p.get("amount", "")), "OWNER", "entered by the owner", 1.0, True),
            Fact(f"day {p.get('day', '')}", "OWNER", "entered by the owner", 1.0, True)))
    s.docs, s.facts, s.mode, s.sample_id = [], f, "manual", None
    s.note = "Facts entered by the owner (no AI used)."
    s.profile = s.profile or _default_profile()
    s.last, s.approvals, s.active_approval, s.executed, s.resolved = {}, {}, None, None, {}
    s.log.append("manual_entry", "T0", {"fields": len(req.facts)}, None, "owner-entered facts")
    return _documents_view(s)


class ResolveReq(BaseModel):
    session_id: str
    code: str
    note: str = Field(min_length=5, max_length=300)


@app.post("/api/flags/resolve")
def resolve_flag(req: ResolveReq):
    s = _session(req.session_id)
    s.resolved[req.code] = req.note.strip()
    s.log.append("resolve_flag", "T1", {"code": req.code, "note": req.note}, None,
                 f"owner resolved {req.code}: {req.note.strip()}")
    return _documents_view(s)


class AnalyzeReq(BaseModel):
    session_id: str
    edits: dict = Field(default_factory=dict)  # fact key -> value; supplier_payments list
    confirmed: list[str] = Field(default_factory=list)  # ExtractedField keys
    payment_reading: str | None = None
    priority: str = "maximize_margin"
    stress_delay: int = 15
    reserve: float | None = None
    opening_cash: float | None = None
    max_financing_cost: float | None = None
    pay_day: int | None = None  # owner what-if override of the customer payment day
    tie_choice: str | None = None


@app.post("/api/analyze")
def analyze(req: AnalyzeReq):
    s = _session(req.session_id)
    if s.facts is None:
        raise HTTPException(400, "Load a sample or upload documents first.")
    if req.priority not in ("maximize_margin", "minimize_financing_cost",
                            "avoid_customer_consent", "most_robust"):
        raise HTTPException(400, "Unknown priority")
    if req.stress_delay not in agent.STRESS_OPTIONS:
        raise HTTPException(400, "Unknown stress delay")
    from dataclasses import replace

    profile = s.profile
    if req.reserve is not None:
        profile = replace(profile, reserve=Decimal(str(round(max(req.reserve, 0), 2))))
    if req.opening_cash is not None:
        profile = replace(profile, opening_cash=Decimal(str(round(req.opening_cash, 2))))
    if req.max_financing_cost is not None:
        profile = replace(profile, max_financing_cost=Decimal(str(round(max(req.max_financing_cost, 0), 2))))
    built = case_builder.build_case(s.facts, profile, req.edits, req.payment_reading)
    if built.case is None:
        return {"ok": False, "missing": built.missing}
    case = built.case
    pay_day = req.pay_day if req.pay_day is not None else built.customer_payment_day
    if not 0 <= pay_day <= 365:
        raise HTTPException(400, "Payment day must be between 0 and 365")

    stage = doc_extract.to_document_stage(s.facts, s.docs, s.mode, s.note,
                                          frozenset(req.confirmed), s.resolved)
    # owner edits count as confirmation of that field
    edited_labels = {FACT_LABELS.get(k) for k in req.edits}
    confirmed = frozenset(req.confirmed) | {f.key for f in stage.fields
                                            if f.name in edited_labels}
    if "supplier_payments" in req.edits:
        confirmed |= {f.key for f in stage.fields if f.name.startswith("Supplier payment")}
    run = agent.run_agent(case, pay_day, req.priority, False, confirmed=confirmed,
                          tie_choice=req.tie_choice, stress_delay=req.stress_delay,
                          documents=stage)
    sig = hashlib.sha256(json.dumps(req.model_dump(exclude={"session_id", "tie_choice"}),
                                    sort_keys=True, default=str).encode()).hexdigest()[:10]
    versions = {pid: _version(sig, r) for pid, r in run.results.items()}
    if s.last.get("sig") != sig:  # scenario changed: approvals no longer apply
        s.approvals, s.active_approval, s.executed = {}, None, None
    s.last = {"run": run, "case": case, "pay_day": pay_day, "sig": sig, "versions": versions,
              "currency": profile.currency}
    s.log.append("simulate+rank_plans", "T1", {"pay_day": pay_day, "priority": req.priority,
                                               "stress": req.stress_delay}, None,
                 f"decision: {run.winner.plan.label}")

    asis = run.results["accept-as-is"]
    gap = engine.funding_gap(asis, case.reserve)
    level, why = agent.uncertainty_rating(run)
    ranked_ids = {r.plan.id for r in run.ranked}
    ordered = run.ranked + [r for r in run.results.values() if r.plan.id not in ranked_ids]
    return {
        "ok": True,
        "case": {"name": case.name, "currency": profile.currency, "business": profile.name,
                 "opening_cash": num(case.opening_cash), "reserve": num(case.reserve),
                 "order_value": num(case.order_value), "gross_margin": num(case.gross_margin),
                 "delivery_day": case.delivery_day, "customer": case.customer,
                 "supplier": case.supplier, "order_ref": case.order_ref, "pay_day": pay_day,
                 "document_pay_day": built.customer_payment_day,
                 "max_financing_cost": num(case.max_financing_cost),
                 "assumptions": built.assumptions, "payment_readings": built.payment_readings,
                 "basis_used": built.basis_used,
                 "movements": [{"day": m.day, "amount": num(m.amount), "label": m.label,
                                "counterparty": m.counterparty, "kind": m.kind}
                               for m in sorted(case.base_movements + case.order_costs,
                                               key=lambda m: m.day)]},
        "verdict": {
            "headline": _headline(run, case, gap), "level": level, "why": why,
            "winner": run.winner.plan.id, "provisional": run.provisional,
            "provisional_fields": [{"name": f.name, "value": f.value, "key": f.key,
                                    "question": f.question} for f in run.provisional_fields],
            "no_plan_survives": run.no_plan_survives, "smallest_changes": run.smallest_changes,
            "priority_conflict": run.priority_conflict,
            "near_tie": ([{"id": a.plan.id, "label": a.plan.label,
                           "strengths": agent.plan_strengths(a, b)}
                          for a, b in (run.near_tie, run.near_tie[::-1])]
                         if run.near_tie else None),
            "owner_tie_choice": run.owner_tie_choice,
            "execution_blocks": run.execution_blocks,
        },
        "gap": {"amount": num(gap.amount), "from_day": gap.from_day,
                "until_day": gap.until_day, "days": gap.days},
        "plans": [_plan_json(r, run, versions[r.plan.id]) for r in ordered],
        "alerts": [{"rule": a.rule, "day": a.day, "message": a.message, "severity": a.severity}
                   for a in run.alerts],
        "flags": [_flag_json(x) for x in run.integrity_flags],
        "fields": [{"name": f.name, "value": f.value, "source": f.source, "span": f.span,
                    "confidence": round(f.confidence, 2), "question": f.question,
                    "key": f.key, "simulation": f.affects_simulation} for f in run.fields],
        "sensitivity": {"flip_day": run.flip_day,
                        "rows": [{"day": d, "label": lbl} for d, lbl in run.sensitivity]},
        "min_safe_loans": [{"offer": o.id, "lender": o.lender, "terms": o.terms_text(),
                            "principal": num(p), "cost": num(r.financing_cost) if r else None,
                            "min": num(o.min_principal), "max": num(o.max_principal)}
                           for o, p, r in run.min_safe_loans],
        "offers": [{"id": o.id, "lender": o.lender, "principal": num(o.principal),
                    "terms": o.terms_text(), "cost": num(o.cost()), "draw_day": o.draw_day,
                    "repay_day": o.repay_day, "ineligible": o.ineligibility()}
                   for o in case.financing_offers],
        "stages": [{"stage": a, "title": b, "detail": c} for a, b, c in run.stage_log],
        "draft": run.draft_message,
        "approval": _approval_json(s),
        "executed": s.executed,
        "ai": {"label": gemini_client.backend_label(), "gemini": gemini_client.gemini_available()},
    }


def _approval_json(s: Session) -> dict | None:
    a = s.approvals.get(s.active_approval or "")
    if not a:
        return None
    return {"id": a.approval_id, "plan_id": a.plan_id, "label": a.display_label,
            "override": a.override, "reason": a.reason, "version": a.plan_version}


def _last(s: Session) -> dict:
    if not s.last:
        raise HTTPException(400, "Run the analysis first.")
    return s.last


class ScenarioReq(BaseModel):
    session_id: str
    plan_id: str
    partial_pct: int = Field(70, ge=0, le=100)
    price_pct: int = Field(10, ge=0, le=100)
    supplier_delay: int = Field(14, ge=0, le=90)


@app.post("/api/scenarios")
def scenarios(req: ScenarioReq):
    s = _session(req.session_id)
    last = _last(s)
    r = last["run"].results.get(req.plan_id)
    if r is None:
        raise HTTPException(404, "Unknown plan")
    outs = agent.scenario_table(last["case"], r, last["pay_day"],
                                agent.standard_scenarios(req.partial_pct, req.price_pct,
                                                         req.supplier_delay))
    never = next(o for o in outs if o.scenario.key == "never")
    return {
        "outcomes": [{"key": o.scenario.key, "label": o.scenario.label,
                      "min_balance": num(o.min_balance), "min_day": o.min_day,
                      "first_breach_day": o.first_breach_day, "reserve_ok": o.reserve_ok,
                      "order_net": num(o.order_net), "penalty": num(o.penalty),
                      "violations": o.violations} for o in outs],
        "max_loss": num(max(-never.order_net, Decimal(0))),
        "money_at_risk": [{"day": d, "amount": num(v)}
                          for d, v in engine.money_at_risk(last["case"], r.plan)],
    }


class ApproveReq(BaseModel):
    session_id: str
    plan_id: str
    override: bool = False
    reason: str = Field("", max_length=300)


@app.post("/api/approve")
def approve(req: ApproveReq):
    s = _session(req.session_id)
    last = _last(s)
    run = last["run"]
    r = run.results.get(req.plan_id)
    if r is None:
        raise HTTPException(404, "Unknown plan")
    if run.provisional:
        raise HTTPException(409, "Confirm the highlighted facts before approving.")
    if r.plan.id == "decline":
        raise HTTPException(409, "Declining needs no sandbox execution.")
    if req.override:
        if r.reserve_ok or r.violations:
            raise HTTPException(409, "A reserve override is only for plans that break the "
                                     "reserve and nothing else.")
        if len(req.reason.strip()) < 5:
            raise HTTPException(400, "Give a reason for the override.")
    elif not r.feasible:
        raise HTTPException(409, "This plan breaks your reserve or a hard constraint. Use "
                                 "an explicit override if you accept that.")
    pv = last["versions"][r.plan.id]
    aid = f"APP-{hashlib.sha256(pv.encode()).hexdigest()[:6].upper()}" + ("-OVR" if req.override else "")
    s.approvals[aid] = Approval(aid, pv, r.plan.id, r.plan.label, req.override, req.reason.strip())
    s.active_approval, s.executed = aid, None
    label = f"{OVERRIDE_TAG} {r.plan.label}" if req.override else r.plan.label
    s.log.append("request_approval", "T1", {"plan_version": pv, "plan": r.plan.id,
                                            "override": req.override, "reason": req.reason},
                 aid, f"approved by owner: {label}")
    return {"approval": _approval_json(s)}


class SessionReq(BaseModel):
    session_id: str


@app.post("/api/execute")
def execute(req: SessionReq):
    s = _session(req.session_id)
    last = _last(s)
    run, a = last["run"], s.approvals.get(s.active_approval or "")
    if a is None:
        raise HTTPException(409, "Approve a plan first.")
    r = run.results[a.plan_id]
    draft = (run.draft_message if r.plan.id == run.winner.plan.id else
             agent.draft_message(r, last["case"], last["pay_day"], run.min_advance))
    s.bank = SimulatedBank()  # each execution books into a fresh simulated ledger
    rep = execute_plan(run, r, draft, a, s.approvals, s.log, s.gate, s.bank, s.outbox,
                       MockLenderPortal({o.id: o for o in last["case"].financing_offers}),
                       blocks=run.execution_blocks)
    s.executed = {"ok": rep.ok, "steps": rep.steps, "consistency": rep.consistency,
                  "override": rep.override,
                  "ledger": s.bank.booked, "outbox": s.outbox.sent[-1:] if rep.ok else []}
    return s.executed


T3_ACTIONS = {
    "real_email": ("smtp.send", "T3: no real email capability exists; blocked in code"),
    "live_transfer": ("bank.live_transfer", "T3: no live bank integration exists; blocked in code"),
    "invent_terms": ("lender.create_terms", "T3: financing terms may only come from the catalogue"),
    "edit_document": ("documents.edit", "T3: source documents are read-only evidence"),
}


class T3Req(BaseModel):
    session_id: str
    action: str


@app.post("/api/t3")
def t3(req: T3Req):
    s = _session(req.session_id)
    if req.action not in T3_ACTIONS:
        raise HTTPException(404, "Unknown action")
    tool, reason = T3_ACTIONS[req.action]
    s.gate.block_t3(tool, {"action": req.action}, reason)
    return {"blocked": True, "reason": reason}


class AskReq(BaseModel):
    session_id: str
    question: str = Field("", max_length=500)


def _ai(s: Session, kind: str, key: str, fn):
    run = _last(s)["run"]
    ck = (kind, s.last["sig"], run.winner.plan.id, key)
    if ck not in s.ai_cache:
        s.ai_cache[ck] = fn(run)
        s.log.append(f"gemini.{kind}", "T1", {"q": key}, None, f"source: {s.ai_cache[ck][1]}")
    return s.ai_cache[ck]


@app.post("/api/ai/ask")
def ask(req: AskReq):
    s = _session(req.session_id)
    if not req.question.strip():
        raise HTTPException(400, "Type a question first.")
    text, mode = _ai(s, "ask", req.question.strip(), lambda run: gemini_client.ask(run, req.question))
    return {"text": text, "source": mode}


@app.post("/api/ai/explain")
def explain(req: SessionReq):
    s = _session(req.session_id)
    text, mode = _ai(s, "explain", "", gemini_client.explain_memo)
    return {"text": text, "source": mode}


@app.post("/api/ai/polish")
def polish(req: SessionReq):
    s = _session(req.session_id)
    text, mode, note = _ai(s, "polish", "", gemini_client.polish_draft)
    return {"text": text, "source": mode, "note": note}


@app.get("/api/log")
def get_log(session_id: str):
    s = _session(session_id)
    return {"entries": s.log.as_dicts()}


@app.get("/api/log/export")
def export_log(session_id: str):
    s = _session(session_id)
    return Response(json.dumps(s.log.as_dicts(), indent=1), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=solvorder_operation_log.json"})


# ------------------------------------------------------------- static UI

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    target = (WEB_DIST / path).resolve()
    if path and target.is_file() and WEB_DIST.resolve() in target.parents:
        return FileResponse(target)
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "UI not built. Run: cd web && npm install && npm run build"},
                        status_code=503)
