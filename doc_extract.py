"""Stage A for uploaded documents: read files, extract facts, verify them.

  read_upload()      PDF -> text layer (pypdf); .txt/.eml -> text
  extract_facts()    Gemini structured extraction (cached per document set),
                     falling back to a deterministic label parser that reads
                     the sample-document layout. Never raises.
  verify_facts()     every quoted span must appear in its source text, and
                     the value must be consistent with the span; otherwise the
                     fact is downgraded and becomes an owner question.
  to_document_stage() packages facts + integrity flags for agent.run_agent.
"""

from __future__ import annotations

import copy
import hashlib
import io
import re
import threading

from docmodel import (FACT_LABELS, SIMULATION_FACTS, BankDetail, Document, Fact, Facts,
                      LineItem, SupplierPayment)
from docparse import parse_amount, parse_amounts, parse_day, parse_percent

LOW_CONFIDENCE = 0.7
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # per file
_CACHE: dict[str, tuple[Facts, str, str, dict]] = {}  # key -> facts, mode, note, doc kinds
_KEY_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


# ------------------------------------------------------------------ reading


def read_upload(doc_id: str, filename: str, data: bytes) -> Document:
    """Turn an uploaded file into a Document. Raises ValueError on bad input."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{filename}: file is larger than 8 MB")
    name = (filename or "document").strip()[:120]
    if data[:5] == b"%PDF-" or name.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:20])
        except Exception as exc:  # corrupt or encrypted PDF
            raise ValueError(f"{name}: could not read this PDF ({exc})") from exc
        text = _clean(text)
        return Document(doc_id, name, classify(text), text,
                        pdf_bytes=None if text.strip() else data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    text = _clean(text)
    if not text.strip():
        raise ValueError(f"{name}: the file is empty")
    return Document(doc_id, name, classify(text), text)


def from_text(doc_id: str, title: str, text: str) -> Document:
    text = _clean(text)
    return Document(doc_id, title, classify(text), text)


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\x00", "")
    return re.sub(r"[ \t]+\n", "\n", text).strip()


def classify(text: str) -> str:
    head = text[:400].upper()
    if "PURCHASE ORDER" in head:
        return "purchase_order"
    if "INVOICE" in head:
        return "invoice"
    if "QUOTATION" in head or "QUOTE" in head:
        return "supplier_quote"
    if re.search(r"^(FROM|SUBJECT|TO):", text[:400], re.IGNORECASE | re.MULTILINE):
        return "email"
    return "other"


# --------------------------------------------------------------- extraction


def extract_facts(docs: list[Document]) -> tuple[Facts, str, str]:
    """(facts, mode, note). mode: gemini | gemini-pdf | parser. Never raises.

    Results are cached per document set. A per-key lock means two requests for
    the same documents (e.g. the startup warm-up and a visitor) share one
    Gemini call. Callers get a deep copy, so one session can't alter another's.
    """
    key = hashlib.sha256(b"".join(
        d.doc_id.encode() + (d.text.encode() or (d.pdf_bytes or b"")) for d in docs)).hexdigest()
    with _LOCKS_GUARD:
        lock = _KEY_LOCKS.setdefault(key, threading.Lock())
    with lock:
        if key in _CACHE:
            facts, mode, note, kinds = _CACHE[key]
        else:
            facts, mode, note, kinds, cacheable = _extract_uncached(docs)
            if cacheable:  # a failed Gemini call is not cached, so a retry can succeed
                _CACHE[key] = (facts, mode, note, kinds)
    for d in docs:
        d.kind = kinds.get(d.doc_id, d.kind)
    return copy.deepcopy(facts), mode, note


def _extract_uncached(docs: list[Document]) -> tuple[Facts, str, str, dict, bool]:
    """(facts, mode, note, doc kinds, cacheable)."""
    import gemini_client

    scanned = [d for d in docs if not d.has_text]
    if gemini_client.gemini_available():
        try:
            data = gemini_client.extract_order_documents(docs)
            facts = facts_from_model(data, docs)
            verify_facts(facts, docs)
            mode = "gemini-pdf" if scanned else "gemini"
            note = (f"Read by {gemini_client.backend_label()}. Every quoted span was checked "
                    f"against the document text.")
            if scanned:
                note += (f" {len(scanned)} scanned PDF(s) have no text layer: their facts "
                         f"cannot be checked automatically and need your confirmation.")
            return facts, mode, note, {d.doc_id: d.kind for d in docs}, True
        except Exception as exc:  # never block the demo on the model
            facts = parse_template(docs)
            verify_facts(facts, docs)
            return facts, "parser", (f"Gemini could not read the documents ({exc}); used the "
                                     f"deterministic parser. Please check every field."), \
                {d.doc_id: d.kind for d in docs}, False
    facts = parse_template(docs)
    verify_facts(facts, docs)
    note = "Gemini is not configured; used the deterministic parser for the standard layout."
    if scanned:
        note += " Scanned PDFs cannot be read without Gemini: enter their facts manually."
    return facts, "parser", note, {d.doc_id: d.kind for d in docs}, True


def facts_from_model(data: dict, docs: list[Document]) -> Facts:
    kinds = {k.get("source"): k.get("kind") for k in data.get("documents", []) if k}
    for d in docs:
        if kinds.get(d.doc_id) in ("purchase_order", "supplier_quote", "invoice", "email", "other"):
            d.kind = kinds[d.doc_id]

    def fact(raw) -> Fact:
        raw = raw or {}
        try:
            conf = min(max(float(raw.get("confidence", 0)), 0.0), 1.0)
        except (TypeError, ValueError):
            conf = 0.0
        return Fact(str(raw.get("value", "")).strip(), str(raw.get("source", "")).strip(),
                    str(raw.get("span", "")).strip(), conf)

    f = Facts(**{name: fact(data.get(name)) for name in Facts.SCALAR_FIELDS})
    for p in data.get("supplier_payments", [])[:12]:
        f.supplier_payments.append(SupplierPayment(str(p.get("label", "Supplier payment"))[:80],
                                                   fact(p.get("amount")), fact(p.get("due_day")),
                                                   p.get("already_paid") is True))
    for li in data.get("line_items", [])[:40]:
        f.line_items.append(LineItem(str(li.get("description", ""))[:120], fact(li.get("amount"))))
    for b in data.get("bank_details", [])[:10]:
        f.bank_details.append(BankDetail(
            str(b.get("source", "")), str(b.get("payee", ""))[:120],
            str(b.get("bank_name", ""))[:120], str(b.get("account_number", ""))[:60],
            str(b.get("span", "")), float(b.get("confidence", 0) or 0)))
    f.instructions_found = [(str(i.get("source", "")), str(i.get("span", "")))
                            for i in data.get("instructions_found", [])[:10]]
    f.model_conflicts = [str(c)[:300] for c in data.get("conflicts", [])[:10] if c]
    return f


# --------------------------------------------------- deterministic fallback

_LABEL = r"^\s*{label}\s*[:\-]\s*(?P<v>.+)$"


def _find(doc: Document, *labels: str) -> Fact:
    for label in labels:
        m = re.search(_LABEL.format(label=label), doc.text, re.IGNORECASE | re.MULTILINE)
        if m:
            return Fact(m.group("v").strip(), doc.doc_id, m.group(0).strip(), 0.9)
    return Fact("")


def parse_template(docs: list[Document]) -> Facts:
    """Reads the 'Label: value' layout used by the sample documents.

    It is a fallback for when Gemini is unavailable, not a general reader:
    fields it cannot find stay empty and the owner fills them in.
    """
    f = Facts()
    for d in docs:
        if d.kind == "purchase_order":
            f.customer_name = _find(d, "Buyer", "Customer")
            f.order_ref = _find(d, "PO number", "Purchase order")
            f.order_value = _find(d, "Total order value", "Order total", "Total")
            f.delivery_day = _find(d, "Delivery required by", "Delivery")
            terms = _find(d, "Payment terms")
            if terms.present:
                days = re.search(r"(\d+)", terms.value)
                f.payment_terms_days = Fact(days.group(1) if days else "", d.doc_id, terms.span, 0.9)
                v = terms.value.lower()
                basis = ("after_delivery" if "deliver" in v else "after_invoice" if "invoice" in v
                         else "after_order" if "order" in v else "unspecified")
                f.payment_terms_basis = Fact(basis, d.doc_id, terms.span,
                                             0.9 if basis != "unspecified" else 0.5)
            f.late_penalty_pct_per_week = _find(d, "Late delivery penalty", "Late delivery")
            f.cancellation_clause = _find(d, "Cancellation")
            f.advance_received = _find(d, "Advance received", "Advance paid", "Deposit received")
            if not f.customer_email.present:
                f.customer_email = _find(d, "Buyer contact", "Buyer email", "Customer email")
            for m in re.finditer(r"^\s*Item\s*\d+\s*[:\-]\s*(?P<desc>.+?)\s+(?P<amt>(USD|INR|Rs\.?|\$)\s*[\d,\.]+\s*\w*)\s*$",
                                 d.text, re.IGNORECASE | re.MULTILINE):
                f.line_items.append(LineItem(m.group("desc").strip(),
                                             Fact(m.group("amt"), d.doc_id, m.group(0).strip(), 0.9)))
        elif d.kind == "supplier_quote":
            f.supplier_name = _find(d, "Supplier", "From")
            for m in re.finditer(r"^\s*\d+\.\s*(?P<label>[^:]+):\s*(?P<amt>.+?)\s+due\s+(?P<day>day\s*\d+)",
                                 d.text, re.IGNORECASE | re.MULTILINE):
                span = m.group(0).strip()
                f.supplier_payments.append(SupplierPayment(
                    m.group("label").strip(), Fact(m.group("amt").strip(), d.doc_id, span, 0.9),
                    Fact(m.group("day"), d.doc_id, span, 0.9)))
        elif d.kind == "invoice":
            f.invoice_amount = _find(d, "Amount due", "Invoice amount", "Total due")
        if d.kind in ("supplier_quote", "invoice") and not f.supplier_email.present:
            f.supplier_email = _find(d, "Supplier email", "Email")
        if d.kind in ("supplier_quote", "invoice", "email"):
            acct = _find(d, "Account number", "Account no", "IBAN")
            if acct.present:
                f.bank_details.append(BankDetail(
                    d.doc_id, _find(d, "Payee", "Account name", "Beneficiary").value,
                    _find(d, "Bank").value, acct.value, acct.span, 0.9))
    from agent import INJECTION_RE

    for d in docs:
        m = INJECTION_RE.search(d.text)
        if m:
            f.instructions_found.append((d.doc_id, m.group(0)))
    return f


# --------------------------------------------------------------- verifier


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().strip("\"'`").lower()


def _verify(fact: Fact, docs: dict[str, Document], kind: str) -> None:
    if not fact.present:
        return
    doc = docs.get(fact.source)
    if doc is None:
        fact.confidence, fact.verified = min(fact.confidence, 0.3), False
        fact.note = "Source document not recognised; please confirm."
        return
    if not doc.has_text:
        fact.confidence, fact.verified = min(fact.confidence, 0.5), False
        fact.note = "Read from a scanned PDF; no text layer to check against. Please confirm."
        return
    if not fact.span or _norm(fact.span) not in _norm(doc.text):
        fact.confidence, fact.verified = min(fact.confidence, 0.3), False
        fact.note = f"Quoted text not found in {doc.doc_id}; please confirm the value."
        return
    ok = True
    if kind == "amount":
        v = parse_amount(fact.value)
        ok = v is not None and any(a.value == v.value for a in parse_amounts(fact.span))
        if v and v.note:
            fact.note = v.note
    elif kind == "day":
        ok = parse_day(fact.value) is not None and str(parse_day(fact.value)) in re.findall(r"\d+", fact.span)
    elif kind == "percent":
        ok = parse_percent(fact.value) is not None or parse_percent(fact.span) is not None
    if not ok:
        fact.confidence, fact.verified = min(fact.confidence, 0.3), False
        fact.note = f"Value '{fact.value}' does not match the quoted text; please confirm."
        return
    fact.verified = True


KINDS = {"order_value": "amount", "invoice_amount": "amount", "advance_received": "amount",
         "delivery_day": "day",
         "payment_terms_days": "day", "late_penalty_pct_per_week": "percent"}


def verify_facts(facts: Facts, docs: list[Document]) -> None:
    by_id = {d.doc_id: d for d in docs}
    for name, fact in facts.scalars().items():
        _verify(fact, by_id, KINDS.get(name, "text"))
    for p in facts.supplier_payments:
        _verify(p.amount, by_id, "amount")
        _verify(p.day, by_id, "day")
    for li in facts.line_items:
        _verify(li.amount, by_id, "amount")
    for b in facts.bank_details:
        doc = by_id.get(b.source)
        b.verified = bool(doc and doc.has_text and b.span and _norm(b.span) in _norm(doc.text)
                          and re.sub(r"\W", "", b.account_number).lower()
                          in re.sub(r"\W", "", doc.text).lower())
    by_text = {d.doc_id: _norm(d.text) for d in docs}
    facts.instructions_found = [(s, sp) for s, sp in facts.instructions_found
                                if s in by_text and sp and _norm(sp) in by_text[s]]


# -------------------------------------------------------- hand-off to agent


def to_document_stage(facts: Facts, docs: list[Document], mode: str, note: str,
                      confirmed: frozenset[str] = frozenset(),
                      resolved: dict[str, str] | None = None):
    """Package verified facts as an agent.DocumentStage (fields, flags)."""
    from agent import DocumentStage, ExtractedField, InjectionFlag
    from doc_checks import check_integrity

    fields: list[ExtractedField] = []
    for name, fact in facts.scalars().items():
        if not fact.present:
            continue
        q = None
        if fact.confidence < LOW_CONFIDENCE or not fact.verified:
            q = fact.note or f"Low confidence on '{FACT_LABELS[name]}'. Please confirm."
        fields.append(ExtractedField(FACT_LABELS[name], fact.value, fact.source, fact.span,
                                     fact.confidence, q, simulation=name in SIMULATION_FACTS))
    for i, p in enumerate(facts.supplier_payments, 1):
        conf = min(p.amount.confidence, p.day.confidence)
        verified = p.amount.verified and p.day.verified
        fields.append(ExtractedField(
            f"Supplier payment {i}: {p.label}", f"{p.amount.value} on {p.day.value}",
            p.amount.source, p.amount.span, conf,
            None if verified and conf >= LOW_CONFIDENCE else
            (p.amount.note or p.day.note or "Please confirm this payment."), simulation=True))
    flags = check_integrity(facts, docs)
    for f in flags:
        if resolved and f.code in resolved:
            f.resolved, f.resolution_note = True, resolved[f.code]
    injections = [InjectionFlag(s, sp) for s, sp in facts.instructions_found]
    return DocumentStage(fields, injections, mode, note, flags)
