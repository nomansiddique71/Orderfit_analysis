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
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent
import auth
import case_builder
import company_check
import doc_extract
import engine
import gemini_client
import needs
import role as roles
from docmodel import (FACT_LABELS, SIMULATION_FACTS, Fact, Facts, SupplierPayment, fact_label,
                      visible_facts)
from sandbox import (OVERRIDE_TAG, Approval, MockLenderPortal, MockOutbox, OperationLog,
                     PermissionGate, SimulatedBank, execute_plan, send_on_approval)

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
WEB_DIST = ROOT / "web" / "dist"
MAX_SESSIONS = 300
MAX_FILES = 6

@asynccontextmanager
async def _lifespan(_app):
    if gemini_client.gemini_available() and os.environ.get("SOLVORDER_WARM_SAMPLES", "1") != "0":
        threading.Thread(target=_warm_samples, name="warm-samples", daemon=True).start()
    yield


app = FastAPI(title="SolvOrder API", version="1.0", lifespan=_lifespan)


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
    # sample: the pack's own business | owner: the owner filled the business form |
    # example: owner chose the example business | default: nobody gave business facts yet
    profile_source: str = "default"
    sample_id: str | None = None
    resolved: dict = field(default_factory=dict)  # flag code -> owner note (clears the flag)
    decisions: dict = field(default_factory=dict)  # flag code -> {action, label, note}
    messages: dict = field(default_factory=dict)  # approval id -> messages sent on approval
    lender: list = field(default_factory=list)  # loan acceptances in the mock lender portal
    bank_approval: str = ""  # approval id behind the current simulated ledger
    last: dict = field(default_factory=dict)  # run, case, pay_day, versions
    ai_cache: dict = field(default_factory=dict)
    account: str = ""  # email of the logged-in owner who loaded the case ("" = anonymous API use)
    approved: list = field(default_factory=list)  # approved-plan records when nobody is logged in
    role: str = "seller"  # the owner's side in THIS deal (seller | buyer)
    role_source: str = "default"  # profile | documents | owner | sample | default
    role_guess: roles.RoleGuess = field(default_factory=lambda: roles.RoleGuess(None, ""))

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


def _fact_json(key: str, f: Fact, role: str = "seller") -> dict:
    return {"key": key, "label": fact_label(key, role), "value": f.value, "source": f.source,
            "span": f.span, "confidence": round(f.confidence, 2), "verified": f.verified,
            "note": f.note, "simulation": key in SIMULATION_FACTS,
            "needs_review": key in SIMULATION_FACTS and f.present and
            (f.confidence < doc_extract.LOW_CONFIDENCE or not f.verified)}


def _documents_view(s: Session) -> dict:
    f = s.facts
    stage = doc_extract.to_document_stage(f, s.docs, s.mode, s.note, resolved=s.resolved,
                                          currency=_doc_currency(s), role=s.role)
    shown = visible_facts(s.role)
    return {
        "mode": s.mode, "note": s.note, "sample_id": s.sample_id,
        "role": s.role, "role_source": s.role_source,
        "role_guess": {"role": s.role_guess.role, "evidence": s.role_guess.evidence},
        "currency": s.profile.currency if s.profile else _currency(s),
        "documents": [{"doc_id": d.doc_id, "filename": d.filename, "kind": d.kind,
                       "scanned": not d.has_text, "chars": len(d.text),
                       "text": d.text[:6000]} for d in s.docs],
        "facts": [_fact_json(k, v, s.role) for k, v in f.scalars().items() if k in shown],
        "supplier_payments": [{"label": p.label, "amount": _fact_json("amount", p.amount),
                               "day": _fact_json("day", p.day), "paid": p.already_paid}
                              for p in f.supplier_payments],
        "line_items": [{"description": li.description, "amount": li.amount.value,
                        "source": li.amount.source} for li in f.line_items],
        "bank_details": [{"source": b.source, "payee": b.payee, "bank": b.bank_name,
                          "account": b.account_number, "verified": b.verified}
                         for b in f.bank_details],
        "flags": [_flag_json(x, s) for x in stage.integrity],
        "profile": s.profile.to_json() if s.profile else None,
        "profile_source": s.profile_source,
        "questions": sum(n.required for n in needs.rule_needs(
            f, {}, s.profile_source, _profile_known(s), s.role, role_conflict(s))),
    }


def _flag_json(x, s: "Session | None" = None) -> dict:
    return {"code": x.code, "severity": x.severity, "title": x.title, "message": x.message,
            "documents": x.documents, "blocks_execution": x.blocks_execution,
            "resolved": x.resolved, "resolution_note": x.resolution_note,
            "category": x.category,
            "options": [{"id": i, "label": lbl, "clears": clears, "needs_note": note}
                        for i, lbl, clears, note in flag_options(x.code, x.blocks_execution)],
            "decision": (s.decisions.get(x.code) if s else None)}


# What the owner can do about each check. A blocking flag (bank details,
# payee) is cleared only by an option that really removes the risk; holding or
# reporting it keeps every payment blocked. Non-blocking flags are cleared by
# any decision, which is recorded in the log.
_VERIFY = ("verified_call", "I called the supplier on the number I already had and they confirmed it",
           True, True)
FLAG_OPTIONS: dict[str, list[tuple[str, str, bool, bool]]] = {
    "BANK_CHANGE": [_VERIFY,
                    ("use_original", "Pay only the original account from the quote; ignore the new details",
                     True, False),
                    ("hold", "Hold every payment until I can verify", False, False),
                    ("report", "Treat it as fraud: report it and do not pay", False, False)],
    "PAYEE_MISMATCH": [_VERIFY,
                       ("use_original", "Pay only the payee named in the quote", True, False),
                       ("hold", "Hold every payment until I can verify", False, False)],
    "AMOUNT_MISMATCH": [("use_po", "Use the amount in the purchase order / quote", True, False),
                        ("ask_corrected", "Ask for a corrected document before paying", True, False),
                        ("checked", "I checked; the difference is explained", True, True)],
    "LINE_ITEMS": [("use_total", "Use the stated total; ask the sender to fix the lines", True, False),
                   ("ask_corrected", "Ask for a corrected document before accepting", True, False)],
    "NET_TERMS": [("use_later", "Use the later, safer payment day", True, False),
                  ("ask_customer", "Ask the customer when the days start counting", True, False)],
    "CANCELLATION": [("ask_deposit", "Ask the customer for a non-refundable deposit", True, False),
                     ("ask_remove", "Ask the customer to remove the clause", True, False),
                     ("accept_risk", "Accept the risk shown in 'money at risk'", True, False)],
    "PRESSURE_LANGUAGE": [("normal_checks", "Ignore the urgency; follow my normal checks", True, False),
                          ("verify_sender", "Verify the sender by phone first", True, False)],
    "EMAIL_CONFLICT": [("verify_sender", "Verify the sender by phone first", True, False),
                       ("use_documents", "Trust the formal documents, not the email", True, False)],
    "LOOKALIKE_DOMAIN": [_VERIFY,
                         ("use_known", "Only use contact and bank details from the quote's known domain",
                          True, False),
                         ("hold", "Hold every payment until I can verify", False, False),
                         ("report", "Treat it as fraud: report it and do not pay", False, False)],
    "FREE_EMAIL": [("verify_sender", "Verify the contact by phone first", True, False),
                   ("ask_company_email", "Ask them to write from their company domain", True, False),
                   ("known_contact", "I know this contact personally; it is fine", True, True)],
    "CURRENCY_MISMATCH": [("same_currency", "The amounts are already in my currency; the label is wrong",
                           True, False),
                          ("ask_my_currency", "Ask the sender for documents in my currency", True, False),
                          ("checked", "I converted the amounts myself in the facts table", True, True)],
    "INJECTION": [("ignore", "Ignore the hidden instruction (SolvOrder already does)", True, False),
                  ("report", "Tell the sender their document contains an AI instruction", True, False)],
}
_GENERIC = [("checked", "I checked the documents; it is fine", True, False),
            ("ask_corrected", "Ask the sender for a corrected document", True, False)]


def flag_options(code: str, blocks: bool) -> list[tuple[str, str, bool, bool]]:
    if code in FLAG_OPTIONS:
        return FLAG_OPTIONS[code]
    return [_VERIFY, ("hold", "Hold every payment until I can verify", False, False)] if blocks else _GENERIC


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
    deal = "offer" if case.is_buyer else "order"
    if run.no_plan_survives:
        return (f"No way of accepting this {deal} keeps your cash above the reserve. "
                "Decline, or ask for one of the changes below.")
    if asis.reserve_ok and not asis.violations:
        return f"You can accept this {deal} as it is: your cash stays above the reserve every day."
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


def _owner(authorization: str | None) -> "auth.User | None":
    """The logged-in owner behind a request, or None (the analysis API also works
    without a login, e.g. in tests and scripts)."""
    if not authorization:
        return None
    try:
        return AUTH.user_for(_bearer(authorization))
    except auth.AuthError:
        return None


def _account(s: Session) -> "auth.User | None":
    return AUTH.users.get(s.account) if s.account else None


def _attach(s: Session, authorization: str | None) -> None:
    u = _owner(authorization)
    if u is not None:
        s.account = u.email


def _currency(s: Session, fallback: str = "USD") -> str:
    """The owner's own currency from the company profile. A sample keeps the
    currency its documents are written in."""
    u = _account(s)
    return u.currency if u and s.profile_source != "sample" else fallback


def _doc_currency(s: Session) -> str | None:
    """The currency the documents are checked against: the owner's profile
    currency for their own cases; samples are consistent by construction."""
    u = _account(s)
    return u.currency if u and s.profile_source != "sample" else None


def _set_role(s: Session, pack_role: str | None = None) -> None:
    """The owner's side in this deal: a sample's own role; otherwise the profile's
    role, checked against the documents (a disagreement becomes an intake question)."""
    u = _account(s)
    if s.profile_source == "sample":
        company, email = (s.profile.name if s.profile else ""), ""
    else:
        company, email = (u.business, u.company_email) if u else ("", "")
    s.role_guess = roles.detect_role(s.facts, s.docs, company, email)
    if s.profile_source == "sample":
        s.role, s.role_source = s.role_guess.role or pack_role or "seller", "sample"
    elif u is not None:
        s.role, s.role_source = u.role, "profile"
    else:
        s.role, s.role_source = s.role_guess.role or "seller", (
            "documents" if s.role_guess.role else "default")


def role_conflict(s: Session) -> bool:
    return bool(s.role_guess.role) and s.role_guess.role != s.role and s.role_source == "profile"


def _set_profile(s: Session, sample_profile) -> None:
    """A sample brings its own business. Otherwise keep business facts the owner
    already gave in this session; if none, the example business is only a
    placeholder until the owner fills the business form (analysis waits)."""
    from dataclasses import replace

    if sample_profile is not None:
        s.profile, s.profile_source = sample_profile, "sample"
    elif s.profile_source not in ("owner", "example"):
        s.profile, s.profile_source = _default_profile(), "default"
    if s.profile_source != "sample" and s.profile is not None:
        s.profile = replace(s.profile, currency=_currency(s, s.profile.currency))


def _ingest(s: Session, docs: list, profile, sample_id: str | None,
            pack_role: str | None = None) -> dict:
    s.docs, s.sample_id, s.resolved = docs, sample_id, {}
    _set_profile(s, profile)
    s.facts, s.mode, s.note = doc_extract.extract_facts(docs)
    _set_role(s, pack_role)
    s.last, s.approvals, s.active_approval, s.executed = {}, {}, None, None
    s.log.append("extract_fields", "T0", {"documents": [d.filename for d in docs]}, None,
                 f"{len(docs)} document(s) read via {s.mode}")
    return _documents_view(s)


def _sample_docs(meta: dict) -> list:
    return [doc_extract.read_upload(f"DOC-{i}", name, (SAMPLES / meta["id"] / name).read_bytes())
            for i, name in enumerate(meta["files"], 1)]


def _warm_samples() -> None:
    """Read every sample pack once in the background, so the first visitor who
    picks a sample gets Gemini's result from the cache instead of waiting ~20 s.
    Off with SOLVORDER_WARM_SAMPLES=0; skipped when Gemini is not configured."""
    for meta in _packs():
        try:
            facts, _, _ = doc_extract.extract_facts(_sample_docs(meta))
            company_check.google_check(company_check.parties(facts))
        except Exception as exc:  # warm-up is best effort; the request path retries
            print(f"[warm-up] sample {meta['id']} failed: {exc}", flush=True)


class SampleReq(BaseModel):
    session_id: str
    pack: str


@app.post("/api/documents/sample")
def load_sample(req: SampleReq, authorization: str | None = Header(default=None)):
    s = _session(req.session_id)
    _attach(s, authorization)
    meta = next((p for p in _packs() if p["id"] == req.pack), None)
    if meta is None:
        raise HTTPException(404, "Unknown sample")
    docs = _sample_docs(meta)
    data = json.loads((SAMPLES / req.pack / "profile.json").read_text())
    profile = case_builder.profile_from_json(data)
    view = _ingest(s, docs, profile, req.pack, meta.get("role"))
    deal = data.get("deal") or {}
    if deal:  # a buyer sample states its own expected income (not in any document)
        for k in ("expected_income", "income_days"):
            if k in deal:
                setattr(s.facts, k, Fact(str(deal[k]), "PROFILE", "stated by the sample business",
                                         1.0, True))
        view = _documents_view(s)
    return view


@app.post("/api/documents/upload")
async def upload(session_id: str = Form(...), files: list[UploadFile] = File(default=[]),
                 pasted: str = Form(default=""), pasted_title: str = Form(default="Pasted text"),
                 authorization: str | None = Header(default=None)):
    s = _session(session_id)
    _attach(s, authorization)
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
    role: str | None = None  # seller | buyer, chosen on the manual form
    facts: dict[str, str] = Field(default_factory=dict)
    supplier_payments: list[dict] = Field(default_factory=list)


@app.post("/api/documents/manual")
def manual(req: ManualReq, authorization: str | None = Header(default=None)):
    """X-05: AI unavailable or no documents -- the owner types the facts."""
    s = _session(req.session_id)
    _attach(s, authorization)
    f = Facts()
    for k, v in req.facts.items():
        if k in Facts.SCALAR_FIELDS and str(v).strip():
            setattr(f, k, Fact(str(v)[:200], "OWNER", "entered by the owner", 1.0, True))
    for p in req.supplier_payments[:12]:
        f.supplier_payments.append(SupplierPayment(
            str(p.get("label", "Supplier payment"))[:80],
            Fact(str(p.get("amount", "")), "OWNER", "entered by the owner", 1.0, True),
            Fact(f"day {p.get('day', '')}", "OWNER", "entered by the owner", 1.0, True),
            bool(p.get("paid", False))))
    s.docs, s.facts, s.mode, s.sample_id = [], f, "manual", None
    s.note = "Facts entered by the owner (no AI used)."
    _set_profile(s, None)
    _set_role(s)
    if req.role in auth.ROLES:  # the manual form says which side the owner is on
        s.role, s.role_source = req.role, "owner"
    s.last, s.approvals, s.active_approval, s.executed, s.resolved = {}, {}, None, None, {}
    s.log.append("manual_entry", "T0", {"fields": len(req.facts)}, None, "owner-entered facts")
    return _documents_view(s)


class SessionReq(BaseModel):
    session_id: str


@app.post("/api/companies")
def companies(req: SessionReq):
    """Who are we dealing with: rule checks on each company's email, plus an optional
    Google check through Gemini with Search grounding (SOLVORDER_GOOGLE_SEARCH=1)."""
    s = _session(req.session_id)
    if s.facts is None:
        raise HTTPException(400, "Load a sample or upload documents first.")
    ps = company_check.parties(s.facts)
    g = company_check.google_check(ps)
    if g["mode"] != "off" and ("companies", g.get("note")) not in s.ai_cache:
        s.ai_cache[("companies", g.get("note"))] = True
        s.log.append("gemini.google_search", "T1", {"companies": [p.company for p in ps]}, None,
                     f"company web check: {g['mode']}")
    lookalikes = [f[3].split(",")[0] for f in company_check.domain_flags(s.facts, s.docs)
                  if f[0] == "LOOKALIKE_DOMAIN"]

    def rules(p):
        out = company_check.rule_checks(p)
        if p.role == "supplier":
            out += [{"kind": "bad", "text": t} for t in lookalikes]
        return out

    return {"parties": [{**p.to_json(), "rules": rules(p),
                         "google": g["results"].get(p.role)} for p in ps],
            "mode": g["mode"], "note": g["note"], "sources": g.get("sources", [])}


class RoleReq(BaseModel):
    session_id: str
    role: str


@app.post("/api/role")
def set_role(req: RoleReq):
    """The owner says which side of this deal they are on (overrides profile and documents)."""
    s = _session(req.session_id)
    if req.role not in auth.ROLES:
        raise HTTPException(400, "Role must be seller or buyer.")
    if s.facts is None:
        raise HTTPException(400, "Load a sample or upload documents first.")
    s.role, s.role_source = req.role, "owner"
    s.last, s.approvals, s.active_approval, s.executed = {}, {}, None, None
    s.log.append("set_role", "T1", {"role": req.role}, None, f"owner is the {req.role} in this deal")
    return _documents_view(s)


def _profile_known(s: Session) -> frozenset[str]:
    """Intake keys the owner's company profile already answers."""
    u = _account(s)
    if u is None:
        return frozenset()
    return frozenset({"currency"} | ({"business_name"} if u.business.strip() else set()))


BUSINESS_MISSING = "Your business details (cash today, reserve, regular payments)"


class NeedsReq(BaseModel):
    session_id: str
    edits: dict = Field(default_factory=dict)


@app.post("/api/needs")
def what_else(req: NeedsReq):
    """Questions SolvOrder must ask before it can judge this order (Gemini picks and
    phrases them from a fixed list; the rule checklist is the fallback and floor)."""
    s = _session(req.session_id)
    if s.facts is None:
        raise HTTPException(400, "Load a sample or upload documents first.")
    edits = {k: str(v)[:200] for k, v in req.edits.items() if k in Facts.SCALAR_FIELDS}
    known = _profile_known(s)
    rules = needs.rule_needs(s.facts, edits, s.profile_source, known, s.role, role_conflict(s))
    ck = ("needs", hashlib.sha256(json.dumps(
        [{k: f.value for k, f in s.facts.scalars().items()}, edits, s.profile_source, sorted(known),
         s.role, role_conflict(s),
         [d.doc_id + d.text[:2000] for d in s.docs]], sort_keys=True).encode()).hexdigest())
    if ck not in s.ai_cache:
        mode, note, picked = "rules", "Gemini is not configured: standard checklist.", []
        if gemini_client.gemini_available():
            known_facts = {**{FACT_LABELS[k]: (edits.get(k) or f.value) for k, f in s.facts.scalars().items()
                              if k in visible_facts(s.role)},
                     "supplier_payments": [f"{p.label}: {p.amount.value} on {p.day.value}"
                                           for p in s.facts.supplier_payments],
                     "business_facts_given_by_owner": s.profile_source in ("owner", "sample"),
                     "owner_role_in_this_deal": s.role}
            if s.profile_source in ("owner", "sample"):
                known_facts["business"] = s.profile.to_json()
            docs = "\n\n".join(f"=== {d.doc_id} ({d.filename}) ===\n{d.text}" for d in s.docs)
            try:
                picked = gemini_client.what_else_needed(known_facts, docs or "(no documents: typed by the owner)",
                                                        needs.allowed_keys(s.role))
                mode, note = "gemini", f"Chosen by {gemini_client.backend_label()} for this order."
            except Exception as exc:  # degrade to the checklist, never block
                note = f"Gemini could not choose the questions ({exc}); standard checklist used."
        s.ai_cache[ck] = (needs.merge(rules, picked, known), mode, note)
        s.log.append("gemini.what_else_needed", "T1", {"keys": len(picked)}, None, f"source: {mode}")
    items, mode, note = s.ai_cache[ck]
    out = [n.to_json() for n in items]
    for n in out:
        if n["key"] == "deal_role":  # quote the documents' evidence in the question
            n["why"] = f"{s.role_guess.evidence} Your profile says you are usually the {s.role}."
            n["suggested"] = s.role_guess.role
    return {"needs": out, "mode": mode, "note": note, "role": s.role,
            "profile_source": s.profile_source,
            "profile": s.profile.to_json() if s.profile else None}


class Recurring(BaseModel):
    label: str = Field(max_length=80)
    amount: float = Field(gt=0)
    days: str = Field(max_length=120)  # "15, 45" -- one payment per listed day


class Receipt(BaseModel):
    label: str = Field(max_length=80)
    amount: float = Field(gt=0)
    day: int = Field(ge=0, le=365)


class OfferIn(BaseModel):
    lender: str = Field(min_length=1, max_length=80)
    principal: float = Field(gt=0)
    fee_pct: float = Field(default=0, ge=0, le=100)
    monthly_rate_pct: float = Field(default=0, ge=0, le=100)
    origination: float = Field(default=0, ge=0)
    repay_day: int = Field(ge=1, le=365)


class ProfileReq(BaseModel):
    session_id: str
    use_example: bool = False  # demo shortcut: keep the example business
    name: str = Field(default="My business", max_length=80)
    currency: str = Field(default="USD", max_length=5)
    opening_cash: float | None = None
    reserve: float | None = Field(default=None, ge=0)
    max_financing_cost: float = Field(default=0, ge=0)
    recurring: list[Recurring] = Field(default_factory=list, max_length=20)
    receivables: list[Receipt] = Field(default_factory=list, max_length=20)
    offers: list[OfferIn] = Field(default_factory=list, max_length=6)


@app.post("/api/profile")
def set_profile(req: ProfileReq):
    """The owner's business facts (answers to the intake questions)."""
    s = _session(req.session_id)
    if req.use_example:
        from dataclasses import replace

        s.profile, s.profile_source = s.profile or _default_profile(), "example"
        s.profile = replace(s.profile, currency=_currency(s, s.profile.currency))
        s.log.append("set_profile", "T1", {"example": True}, None, "owner chose the example business")
        return _documents_view(s)
    if req.opening_cash is None or req.reserve is None:
        raise HTTPException(400, "Cash today and the minimum reserve are required.")
    obligations = []
    for r in req.recurring:
        days = [d.strip() for d in r.days.replace(";", ",").split(",") if d.strip()]
        if not days or not all(d.isdigit() and 0 <= int(d) <= 365 for d in days):
            raise HTTPException(400, f"'{r.label}': list the days as numbers 0-365, e.g. 15, 45")
        kind = "payroll" if any(w in r.label.lower() for w in ("payroll", "salar", "wage")) else "obligation"
        obligations += [{"day": int(d), "amount": str(-Decimal(str(r.amount))), "label": r.label,
                         "kind": kind, "counterparty": "Staff" if kind == "payroll" else r.label}
                        for d in days]
    obligations += [{"day": r.day, "amount": str(Decimal(str(r.amount))), "label": r.label,
                     "kind": "receivable", "counterparty": r.label} for r in req.receivables]
    offers = [{"id": f"OFF-{i}", "lender": o.lender, "principal": str(o.principal),
               "fee_pct": str(o.fee_pct), "monthly_rate_pct": str(o.monthly_rate_pct),
               "origination": str(o.origination), "draw_day": 0, "repay_day": o.repay_day,
               "expires_day": 7, "conditions": "Entered by the owner."}
              for i, o in enumerate(req.offers, 1)]
    try:
        s.profile = case_builder.profile_from_json({
            "name": req.name.strip() or (_account(s).business if _account(s) else "") or "My business",
            "currency": _currency(s, req.currency.strip().upper() or "USD"),
            "opening_cash": str(req.opening_cash), "reserve": str(req.reserve),
            "max_financing_cost": str(req.max_financing_cost),
            "obligations": sorted(obligations, key=lambda o: o["day"]), "offers": offers})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    s.profile_source = "owner"
    s.log.append("set_profile", "T1", {"obligations": len(obligations), "offers": len(offers)},
                 None, "owner entered business details")
    return _documents_view(s)


class ResolveReq(BaseModel):
    session_id: str
    code: str
    action: str = "verified_call"
    note: str = Field("", max_length=300)


@app.post("/api/flags/resolve")
def resolve_flag(req: ResolveReq):
    """The owner picks one of the suggested actions for a fraud/integrity check."""
    s = _session(req.session_id)
    stage = doc_extract.to_document_stage(s.facts, s.docs, s.mode, s.note,
                                          currency=_doc_currency(s), role=s.role) if s.facts else None
    flag = next((f for f in (stage.integrity if stage else []) if f.code == req.code), None)
    if flag is None:
        raise HTTPException(404, "Unknown check")
    opt = next((o for o in flag_options(flag.code, flag.blocks_execution) if o[0] == req.action), None)
    if opt is None:
        raise HTTPException(400, "Unknown action for this check")
    _, label, clears, needs_note = opt
    note = req.note.strip()
    if needs_note and len(note) < 5:
        raise HTTPException(400, "Say how you checked (at least 5 characters).")
    s.decisions[req.code] = {"action": req.action, "label": label, "note": note, "clears": clears}
    if clears:
        s.resolved[req.code] = label + (f": {note}" if note else "")
    else:
        s.resolved.pop(req.code, None)
    s.log.append("resolve_flag", "T1", {"code": req.code, "action": req.action, "note": note}, None,
                 f"owner chose for {req.code}: {label}" + ("" if clears else " (payments stay blocked)"))
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
    built = case_builder.build_case(s.facts, profile, req.edits, req.payment_reading, s.role)
    if s.profile_source == "default":  # documents describe the order, not the business
        return {"ok": False, "needs_business": True,
                "missing": built.missing + [BUSINESS_MISSING]}
    if built.case is None:
        return {"ok": False, "missing": built.missing}
    case = built.case
    pay_day = req.pay_day if req.pay_day is not None else built.customer_payment_day
    if not 0 <= pay_day <= 365:
        raise HTTPException(400, "Payment day must be between 0 and 365")

    stage = doc_extract.to_document_stage(s.facts, s.docs, s.mode, s.note,
                                          frozenset(req.confirmed), s.resolved, _doc_currency(s), s.role)
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
                 "role": case.role, "deal": "offer" if case.is_buyer else "order",
                 "opening_cash": num(case.opening_cash), "reserve": num(case.reserve),
                 "order_value": num(case.order_value), "gross_margin": num(case.gross_margin),
                 "advance_received": num(case.advance_received),
                 "balance_due": num(case.balance_due),
                 "costs_already_paid": num(case.costs_already_paid),
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
        "walk": {k: _walk_json(agent.cash_walk(case, run.results[pid].plan, pay_day))
                 for k, pid in (("asis", "accept-as-is"), ("recommended", run.winner.plan.id))},
        "gap": {"amount": num(gap.amount), "from_day": gap.from_day,
                "until_day": gap.until_day, "days": gap.days},
        "plans": [_plan_json(r, run, versions[r.plan.id]) for r in ordered],
        "alerts": [{"rule": a.rule, "day": a.day, "message": a.message, "severity": a.severity}
                   for a in run.alerts],
        "flags": [_flag_json(x, s) for x in run.integrity_flags],
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


def _walk_json(w: dict) -> dict:
    return {**{k: num(w[k]) for k in ("opening", "reserve", "low", "headroom", "end")},
            "plan": w["plan"], "low_day": w["low_day"],
            "out_until_low": {k: num(v) for k, v in w["out_until_low"].items()},
            "in_until_low": {k: num(v) for k, v in w["in_until_low"].items()},
            "rows": [{**r, "amount": num(r["amount"]), "balance": num(r["balance"])}
                     for r in w["rows"]]}


def _approval_json(s: Session) -> dict | None:
    a = s.approvals.get(s.active_approval or "")
    if not a:
        return None
    return {"id": a.approval_id, "plan_id": a.plan_id, "label": a.display_label,
            "override": a.override, "reason": a.reason, "version": a.plan_version,
            "messages": s.messages.get(a.approval_id, []),
            "notified": bool(s.messages.get(a.approval_id))}


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
    polished: bool = False  # send Gemini's verified rewording instead of the engine draft


class PlanReq(BaseModel):
    session_id: str
    plan_id: str | None = None


def _draft_for(s: Session, plan_id: str) -> str:
    """The plan's full message text (all parts joined) -- what execute_plan logs."""
    return "\n\n---\n\n".join(m["body"] for m in _messages_for(s, plan_id))


def _messages_for(s: Session, plan_id: str) -> list[dict]:
    """One engine-drafted message per party the plan involves. The deal's
    counterparty always comes first: the customer when the owner sells (an
    acceptance, or the advance request), the supplier when the owner buys (an
    acceptance, or the request to pay later). Then the supplier for an extension
    (seller) and the lender for a loan."""
    from dataclasses import replace

    last = _last(s)
    run, case = last["run"], last["case"]
    r = run.results.get(plan_id)
    if r is None:
        raise HTTPException(404, "Unknown plan")
    p = r.plan
    if case.is_buyer:
        parts = [("supplier", replace(p, advance_pct=engine.ZERO, financing=None))]
    else:
        parts = [("customer", replace(p, supplier_extension=False, financing=None))]
        if p.supplier_extension:
            parts.append(("supplier", replace(p, advance_pct=engine.ZERO, financing=None)))
    if p.financing is not None:
        parts.append(("lender", replace(p, advance_pct=engine.ZERO, supplier_extension=False)))
    out = []
    for party, part in parts:
        body = agent.draft_message(replace(r, plan=part), case, last["pay_day"], run.min_advance)
        who, to = _recipient(s, case, party, part)
        out.append({"party": party, "to_name": who, "to": to, "body": body,
                    "subject": body.splitlines()[0].removeprefix("Subject:").strip()})
    return out


def _recipient(s: Session, case, party: str, plan) -> tuple[str, str]:
    """(who, address): the email the documents give for the customer or supplier,
    else a mock address. The lender has no address in the documents."""
    import re

    facts = s.facts
    if party == "customer":
        who, email = case.customer, facts.customer_email.value if facts else ""
    elif party == "supplier":
        who, email = case.supplier or "Supplier", facts.supplier_email.value if facts else ""
    else:
        who, email = plan.financing.lender, ""
    email = email.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        slug = re.sub(r"[^a-z0-9]+", "-", who.lower()).strip("-") or "counterparty"
        email = f"accounts@{slug}.example"
    return who, email


@app.post("/api/breakdown")
def breakdown(req: PlanReq):
    """Money in and out for one plan, day by day, with the reasons to accept it or not."""
    s = _session(req.session_id)
    last = _last(s)
    run = last["run"]
    r = run.results.get(req.plan_id or run.winner.plan.id)
    if r is None:
        raise HTTPException(404, "Unknown plan")
    b = agent.plan_breakdown(run, r, last["pay_day"])
    dec = lambda d: {k: num(v) for k, v in d.items()}  # noqa: E731
    return {**b, **{k: num(b[k]) for k in ("opening", "reserve", "end", "low", "headroom",
                                            "total_in", "total_out", "net_change")},
            "money_in": dec(b["money_in"]), "money_out": dec(b["money_out"]),
            "profit": dec(b["profit"]),
            "rows": [{**x, "amount": num(x["amount"]), "balance": num(x["balance"])}
                     for x in b["rows"]]}


@app.post("/api/draft")
def draft(req: PlanReq):
    """The engine's messages for any plan the owner is looking at."""
    s = _session(req.session_id)
    pid = req.plan_id or _last(s)["run"].winner.plan.id
    return {"plan_id": pid, "messages": _messages_for(s, pid)}


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
    # The approval authorises this plan's messages; they go out when the owner
    # presses Notify (see notify), which also books the plan in the sandbox.
    s.messages[aid] = []
    return {"approval": _approval_json(s)}


class NotifyReq(BaseModel):
    session_id: str
    polished: bool = False  # send Gemini's verified rewording instead of the engine draft


@app.post("/api/notify")
def notify(req: NotifyReq, authorization: str | None = Header(default=None)):
    """After approval: email the deal's counterparty (and any other party the plan
    needs) through the mock outbox, book the plan in the sandbox bank, and file the
    approved plan with its emails under the owner's Approved plans."""
    s = _session(req.session_id)
    last = _last(s)
    run, a = last["run"], s.approvals.get(s.active_approval or "")
    if a is None:
        raise HTTPException(409, "Approve a plan first.")
    if s.messages.get(a.approval_id):
        raise HTTPException(409, "Already notified for this approval.")
    r = run.results[a.plan_id]
    sent_all = []
    for i, m in enumerate(_messages_for(s, r.plan.id)):
        body, source = m["body"], "engine"
        if req.polished:
            cached = s.ai_cache.get(("polish", last["sig"], run.winner.plan.id, f"{r.plan.id}#{i}"))
            if cached and cached[1] == "gemini":
                body, source = cached[0], "gemini"
        sent, why = send_on_approval(a, s.approvals, s.gate, s.log, s.outbox,
                                     m["to"], m["subject"], body)
        sent_all.append({**m, "body": body, "source": source, "sent": sent,
                         "status": "sent to the demo outbox (nothing really delivered)" if sent
                         else f"not sent: {why}"})
    s.messages[a.approval_id] = sent_all
    executed = _execute(s)
    record = _approved_record(s, a, r, sent_all, executed)
    u = _owner(authorization) or _account(s)
    if u is not None:
        AUTH.add_approved(u.email, record)
    else:
        s.approved.insert(0, record)
    return {"approval": _approval_json(s), "executed": executed, "record": record}


def _approved_record(s: Session, a, r, mails: list[dict], executed: dict) -> dict:
    """What the Approved plans section keeps: the plan, its key numbers, the reasons,
    the emails sent and the sandbox result."""
    last = s.last
    case = last["case"]
    b = agent.plan_breakdown(last["run"], r, last["pay_day"])
    primary = mails[0] if mails else {}
    return {
        "id": a.approval_id, "time": time.strftime("%d %b %Y, %H:%M"), "case": case.name,
        "business": s.profile.name if s.profile else "", "role": case.role,
        "counterparty": primary.get("to_name", ""), "party": primary.get("party", ""),
        "plan_id": r.plan.id, "plan": r.plan.label, "override": a.override, "reason": a.reason,
        "currency": case.currency, "order_ref": case.order_ref,
        "numbers": {"low": num(r.min_balance), "low_day": r.min_day, "reserve": num(case.reserve),
                    "net_profit": num(r.net_margin), "financing_cost": num(r.financing_cost),
                    "opening": num(case.opening_cash)},
        "summary": b["summary"], "reasons_for": b["reasons_for"],
        "reasons_against": b["reasons_against"],
        "mails": [{k: m[k] for k in ("party", "to_name", "to", "subject", "body", "status", "sent", "source")}
                  for m in mails],
        "sandbox": {"ok": executed["ok"], "consistency": executed["consistency"],
                    "steps": executed["steps"]},
    }


@app.get("/api/approved")
def approved(session_id: str = "", authorization: str | None = Header(default=None)):
    """The owner's approved plans with the emails sent (newest first). In server
    memory only, like the demo accounts."""
    u = _owner(authorization)
    if u is not None:
        return {"plans": u.approved_plans}
    s = _SESSIONS.get(session_id)
    return {"plans": s.approved if s else []}


@app.post("/api/execute")
def execute(req: SessionReq):
    """Kept for the API and tests; the UI books the plan as part of Notify."""
    return _execute(_session(req.session_id))


def _execute(s: Session) -> dict:
    last = _last(s)
    run, a = last["run"], s.approvals.get(s.active_approval or "")
    if a is None:
        raise HTTPException(409, "Approve a plan first.")
    r = run.results[a.plan_id]
    msgs = s.messages.get(a.approval_id, [])
    s.bank = SimulatedBank()  # each execution books into a fresh simulated ledger
    portal = MockLenderPortal({o.id: o for o in last["case"].financing_offers})
    rep = execute_plan(run, r, "\n\n---\n\n".join(m["body"] for m in msgs) or _draft_for(s, r.plan.id),
                       a, s.approvals, s.log, s.gate, s.bank, s.outbox, portal,
                       blocks=run.execution_blocks,
                       message_already_sent=bool(msgs) and all(m["sent"] for m in msgs))
    s.lender += [{**x, "approval_id": a.approval_id,
                  "lender": next((o.lender for o in last["case"].financing_offers
                                  if o.id == x["offer"]), "")} for x in portal.accepted]
    s.bank_approval = a.approval_id if s.bank.booked else ""
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


class PolishReq(PlanReq):
    index: int = 0  # which of the plan's messages


@app.post("/api/ai/polish")
def polish(req: PolishReq):
    s = _session(req.session_id)
    pid = req.plan_id or _last(s)["run"].winner.plan.id
    msgs = _messages_for(s, pid)
    if not 0 <= req.index < len(msgs):
        raise HTTPException(404, "Unknown message")
    original = msgs[req.index]["body"]
    text, mode, note = _ai(s, "polish", f"{pid}#{req.index}",
                           lambda run: gemini_client.polish_draft(run, original))
    return {"text": text, "source": mode, "note": note, "plan_id": pid, "index": req.index}


# Plain-language description of each tool, for the operation log.
TOOL_TEXT = {
    "extract_fields": "Documents read", "manual_entry": "Order typed in by you",
    "set_profile": "Business details saved", "resolve_flag": "Your decision on a check",
    "simulate+rank_plans": "Cash simulated day by day and plans ranked",
    "request_approval": "You approved a plan", "outbox.send": "Email posted to the demo outbox",
    "set_role": "You set your side of the deal",
    "lender.accept": "Loan accepted in the mock lender portal",
    "bank.post": "Payments booked in the simulated bank", "consistency_check":
    "Simulated bank compared with the engine's prediction", "execute_plan": "Execution attempt",
    "gemini.explain": "Gemini explained the decision", "gemini.ask": "Gemini answered a question",
    "gemini.polish": "Gemini reworded a message (numbers checked)",
    "gemini.what_else_needed": "Gemini chose the intake questions",
    "gemini.google_search": "Gemini searched Google for the companies",
    "smtp.send": "Tried to send a REAL email", "bank.live_transfer": "Tried a LIVE bank transfer",
    "lender.create_terms": "Tried to invent loan terms", "documents.edit": "Tried to edit a source document",
}
OWNER_TOOLS = {"manual_entry", "set_profile", "resolve_flag", "request_approval"}


def _where(e: dict) -> str:
    """Which part of SolvOrder ran this step: sandbox | gemini | engine | owner | blocked."""
    if e["result"].startswith("BLOCKED") or e["tier"] == "T3":
        return "blocked"
    if e["tool"].startswith("gemini.") or (e["tool"] == "extract_fields" and "gemini" in e["result"]):
        return "gemini"
    if e["tier"] == "T2":
        return "sandbox"
    if e["tool"] in OWNER_TOOLS:
        return "owner"
    return "engine"


@app.get("/api/log")
def get_log(session_id: str):
    s = _session(session_id)
    return {"entries": [{**e, "where": _where(e), "what": TOOL_TEXT.get(e["tool"], e["tool"])}
                        for e in s.log.as_dicts()]}


@app.get("/api/sandbox")
def sandbox_view(session_id: str):
    """Everything the sandbox holds for this session: mock outbox, simulated bank
    ledger (with running balance) and mock lender portal. Nothing here is real."""
    s = _session(session_id)
    rows, running = [], None
    if s.bank.booked and s.last:
        running = s.last["case"].opening_cash
        for m in sorted(s.bank.booked, key=lambda m: (m["day"], Decimal(str(m["amount"])) >= 0)):
            running += Decimal(str(m["amount"]))
            rows.append({"day": m["day"], "label": m["label"], "amount": num(Decimal(str(m["amount"]))),
                         "balance": num(running)})
    return {"outbox": list(reversed(s.outbox.sent)),
            "bank": {"approval_id": s.bank_approval, "opening": num(s.last["case"].opening_cash)
                     if s.last and rows else None, "rows": rows},
            "lender": list(reversed(s.lender))}


@app.get("/api/log/export")
def export_log(session_id: str):
    s = _session(session_id)
    return Response(json.dumps(s.log.as_dicts(), indent=1), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=solvorder_operation_log.json"})


# ------------------------------------------------------------ demo login

AUTH = auth.AuthStore()


def _auth_call(fn, *args):
    try:
        return fn(*args)
    except auth.AuthError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


def _bearer(authorization: str | None) -> str:
    return (authorization or "").removeprefix("Bearer ").strip()


class SignupReq(BaseModel):
    name: str = Field(max_length=80)
    username: str = Field(max_length=30)
    email: str = Field(max_length=120)
    password: str = Field(max_length=128)


class CodeReq(BaseModel):
    pending_id: str = Field(max_length=40)
    code: str = Field(default="", max_length=10)
    new_password: str = Field(default="", max_length=128)


class LoginReq(BaseModel):
    login: str = Field(max_length=120)
    password: str = Field(max_length=128)


class EmailReq(BaseModel):
    email: str = Field(max_length=120)


class ProfileUpdateReq(BaseModel):
    name: str = Field(max_length=80)
    business: str = Field(default="", max_length=80)
    company_email: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=10)
    currency: str | None = Field(default=None, max_length=5)


class PasswordReq(BaseModel):
    old_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


@app.post("/api/auth/signup")
def signup(req: SignupReq):
    pid, mail = _auth_call(AUTH.start_signup, req.name, req.username, req.email, req.password)
    return {"pending_id": pid, "demo_inbox": mail}


@app.post("/api/auth/resend")
def resend(req: CodeReq):
    pid, mail = _auth_call(AUTH.resend, req.pending_id)
    return {"pending_id": pid, "demo_inbox": mail}


@app.post("/api/auth/verify")
def verify(req: CodeReq):
    token, user = _auth_call(AUTH.verify_signup, req.pending_id, req.code)
    return {"token": token, "user": user.to_json()}


@app.post("/api/auth/login")
def login(req: LoginReq):
    token, user = _auth_call(AUTH.login, req.login, req.password)
    return {"token": token, "user": user.to_json()}


@app.post("/api/auth/demo")
def demo_login():
    token, user = AUTH.demo()
    return {"token": token, "user": user.to_json()}


@app.get("/api/auth/me")
def me(authorization: str | None = Header(default=None)):
    return {"user": _auth_call(AUTH.user_for, _bearer(authorization)).to_json()}


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    AUTH.logout(_bearer(authorization))
    return {"ok": True}


@app.post("/api/auth/profile")
def update_profile(req: ProfileUpdateReq, authorization: str | None = Header(default=None)):
    return {"user": _auth_call(AUTH.update_profile, _bearer(authorization), req.name,
                               req.business, req.company_email, req.role, req.currency).to_json()}


@app.post("/api/auth/password")
def change_password(req: PasswordReq, authorization: str | None = Header(default=None)):
    _auth_call(AUTH.change_password, _bearer(authorization), req.old_password, req.new_password)
    return {"ok": True}


@app.post("/api/auth/forgot")
def forgot(req: EmailReq):
    pid, mail = AUTH.start_reset(req.email)
    return {"pending_id": pid, "demo_inbox": mail,
            "message": "If an account exists for this email, a code is in the demo inbox."}


@app.post("/api/auth/reset")
def reset(req: CodeReq):
    token, user = _auth_call(AUTH.finish_reset, req.pending_id, req.code, req.new_password)
    return {"token": token, "user": user.to_json()}


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
