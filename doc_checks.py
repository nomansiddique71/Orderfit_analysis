"""Deterministic fraud and document-integrity checks on extracted facts.

The model reads; these rules decide. Each check compares facts across
documents or against arithmetic the engine can verify, and returns a flag the
owner must see. Flags with blocks_execution=True stop every sandbox action
(sandbox.execute_plan) until the owner resolves them with a recorded note.

Checks
  BANK_CHANGE       supplier bank account differs between documents (payment
                    diversion / business-email-compromise pattern)
  PAYEE_MISMATCH    payee on an invoice or email is not the supplier on the quote
  AMOUNT_MISMATCH   invoice amount matches no quoted supplier payment
  LINE_ITEMS        line items do not add up to the order total (D-03)
  NET_TERMS         "Net N" with no start date: two readings (D-01)
  CANCELLATION      unilateral cancellation clause (P-05)
  NUMBER_FORMAT     lakh / crore / South Asian grouping normalised (D-10)
  EMAIL_CONFLICT    an email states terms that differ from the order (D-06)
  PRESSURE_LANGUAGE urgency / secrecy / "new account" wording in an email
  INJECTION         instruction addressed to the AI found in a document
  LOOKALIKE_DOMAIN  supplier document from a near-identical email domain (company_check)
  FREE_EMAIL        a company writing from free webmail (company_check)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from docmodel import Document, Facts
from docparse import mask_account, normalise_account, parse_amount, parse_amounts, parse_day


@dataclass
class IntegrityFlag:
    code: str
    severity: str  # critical | warning | info
    title: str
    message: str
    documents: list[str] = field(default_factory=list)
    blocks_execution: bool = False
    resolved: bool = False
    resolution_note: str = ""
    category: str = "integrity"  # fraud | integrity | ambiguity | security


PRESSURE_RE = re.compile(
    r"\b(urgent(ly)?|immediately|today only|confidential|do not (call|phone|contact)|"
    r"new (bank|account)|changed? (our )?(bank|account)|updated (bank|account) details|"
    r"account (has|was) changed)\b",
    re.IGNORECASE,
)


def _doc_kind(docs: dict[str, Document], doc_id: str) -> str:
    d = docs.get(doc_id)
    return d.kind if d else "other"


def check_integrity(facts: Facts, docs: list[Document],
                    currency: str | None = None) -> list[IntegrityFlag]:
    """currency: the owner's profile currency; documents in another currency are
    flagged (SolvOrder never converts)."""
    by_id = {d.doc_id: d for d in docs}
    flags: list[IntegrityFlag] = []
    if currency:
        flags += _currency_checks(facts, currency)
    flags += _bank_checks(facts, by_id)
    flags += _amount_checks(facts, by_id)
    flags += _terms_checks(facts, by_id)
    flags += _email_checks(facts, docs)
    from company_check import domain_flags

    for code, sev, title, msg, docs_, blocks in domain_flags(facts, docs):
        flags.append(IntegrityFlag(code, sev, title, msg, docs_, blocks_execution=blocks,
                                   category="fraud"))
    for doc_id, span in facts.instructions_found:
        flags.append(IntegrityFlag(
            "INJECTION", "critical", "Instruction to the AI found in a document",
            f"{doc_id} contains text addressed to the agent: \"{span}\". Documents are "
            f"treated as data: the instruction was ignored and the verdict is unchanged.",
            [doc_id], blocks_execution=False, category="security"))
    return flags


def _currency_checks(facts: Facts, currency: str) -> list[IntegrityFlag]:
    from docparse import currency_of

    amounts = [facts.order_value, facts.invoice_amount] + [p.amount for p in facts.supplier_payments]
    for f in amounts:
        found = currency_of(f.value) or currency_of(f.span)
        if found and found != currency:
            return [IntegrityFlag(
                "CURRENCY_MISMATCH", "warning", f"Documents are in {found}, your business runs in {currency}",
                f"'{f.span or f.value}' is in {found}, but your company profile says {currency}. "
                f"SolvOrder never converts currencies: every amount is used as written and shown "
                f"in {currency}. Confirm the amounts are right for your business before you rely "
                f"on the result.", [f.source], blocks_execution=False, category="integrity")]
    return []


# ------------------------------------------------------------------ fraud


def _bank_checks(facts: Facts, docs: dict[str, Document]) -> list[IntegrityFlag]:
    out: list[IntegrityFlag] = []
    banks = [b for b in facts.bank_details if normalise_account(b.account_number)]
    if len(banks) >= 2:
        reference = next((b for b in banks if _doc_kind(docs, b.source) == "supplier_quote"),
                         banks[0])
        ref_acct = normalise_account(reference.account_number)
        changed = [b for b in banks if b is not reference
                   and normalise_account(b.account_number) != ref_acct]
        if changed:
            asks = "; ".join(
                f"{b.source} asks for account {mask_account(b.account_number)}"
                f" ({b.bank_name or 'bank not stated'}"
                + (f", payee '{b.payee}'" if b.payee.strip() else "") + ")"
                for b in changed)
            out.append(IntegrityFlag(
                "BANK_CHANGE", "critical", "Supplier bank details changed",
                f"{asks}, but {reference.source} gave {mask_account(reference.account_number)} "
                f"({reference.bank_name or 'bank not stated'}). This is the classic "
                f"payment-diversion fraud pattern. Verify the change by calling the "
                f"supplier on a number you already had, not one in these documents. "
                f"All payments are blocked until you record that check.",
                [reference.source] + [b.source for b in changed], blocks_execution=True,
                category="fraud"))
    supplier = facts.supplier_name.value.strip().lower()
    if supplier:
        for b in banks:
            payee = b.payee.strip().lower()
            if payee and supplier not in payee and payee not in supplier:
                out.append(IntegrityFlag(
                    "PAYEE_MISMATCH", "critical", "Payee is not the supplier",
                    f"{b.source} names the payee '{b.payee}', but the supplier is "
                    f"'{facts.supplier_name.value}'. Paying a third party is a common "
                    f"fraud route. Confirm with the supplier before any payment.",
                    [b.source], blocks_execution=True, category="fraud"))
    return out


def _amount_checks(facts: Facts, docs: dict[str, Document]) -> list[IntegrityFlag]:
    out: list[IntegrityFlag] = []
    inv = parse_amount(facts.invoice_amount.value) if facts.invoice_amount.present else None
    quoted = [parse_amount(p.amount.value) for p in facts.supplier_payments]
    quoted_vals = {q.value for q in quoted if q}
    if inv and quoted_vals and inv.value not in quoted_vals and inv.value != sum(quoted_vals):
        out.append(IntegrityFlag(
            "AMOUNT_MISMATCH", "critical", "Invoice amount differs from the quote",
            f"{facts.invoice_amount.source} asks for {inv.value:,.2f}, which matches no "
            f"payment in the quote ({', '.join(f'{v:,.0f}' for v in sorted(quoted_vals))}). "
            f"Do not pay until the supplier explains the difference.",
            [facts.invoice_amount.source], blocks_execution=True, category="fraud"))

    total = parse_amount(facts.order_value.value) if facts.order_value.present else None
    items = [parse_amount(li.amount.value) for li in facts.line_items]
    if total and items and all(items):
        s = sum((i.value for i in items), Decimal(0))
        if s != total.value:
            out.append(IntegrityFlag(
                "LINE_ITEMS", "warning", "Line items do not add up to the order total",
                f"The line items sum to {s:,.2f} but the stated total is {total.value:,.2f} "
                f"(difference {total.value - s:+,.2f}). The engine uses the stated total; "
                f"confirm which figure is right before relying on the result.",
                [facts.order_value.source], blocks_execution=False, category="integrity"))

    for name, fact in facts.scalars().items():
        if name in ("order_value", "invoice_amount") and fact.present:
            for a in parse_amounts(fact.value):
                if a.note:
                    out.append(IntegrityFlag(
                        "NUMBER_FORMAT", "info", "Number format interpreted",
                        f"{a.note}. Please check this figure.", [fact.source],
                        category="ambiguity"))
    return out


# ---------------------------------------------------------------- terms


def _terms_checks(facts: Facts, docs: dict[str, Document]) -> list[IntegrityFlag]:
    out: list[IntegrityFlag] = []
    basis = facts.payment_terms_basis.value.strip().lower()
    terms = parse_day(facts.payment_terms_days.value) if facts.payment_terms_days.present else None
    delivery = parse_day(facts.delivery_day.value) if facts.delivery_day.present else None
    if terms is not None and basis in ("", "unspecified", "unknown"):
        readings = [f"from the order date: day {terms}"]
        if delivery is not None:
            readings.append(f"from delivery: day {delivery + terms}")
        out.append(IntegrityFlag(
            "NET_TERMS", "warning", f"'Net {terms}' has no start date",
            f"The terms do not say when the {terms} days start. Two readings: "
            + "; ".join(readings) + ". The engine uses the later, safer date until you "
            "confirm which one the customer means.",
            [facts.payment_terms_days.source], category="ambiguity"))
    if facts.cancellation_clause.present and facts.cancellation_clause.value.strip().lower() not in (
            "none", "no", "n/a", "not stated"):
        out.append(IntegrityFlag(
            "CANCELLATION", "warning", "The customer can cancel",
            f"Clause: \"{facts.cancellation_clause.value.strip().rstrip('.')}\". Money already paid to "
            f"the supplier is at risk if the order is cancelled. See 'money at risk by "
            f"date' in the What-if panel.",
            [facts.cancellation_clause.source], category="integrity"))
    return out


def _email_checks(facts: Facts, docs: list[Document]) -> list[IntegrityFlag]:
    out: list[IntegrityFlag] = []
    order_total = parse_amount(facts.order_value.value) if facts.order_value.present else None
    for d in docs:
        if d.kind != "email" or not d.text:
            continue
        m = PRESSURE_RE.search(d.text)
        if m:
            out.append(IntegrityFlag(
                "PRESSURE_LANGUAGE", "warning", "Pressure or account-change wording",
                f"{d.doc_id} says \"{m.group(0)}\". Urgency, secrecy and new-account "
                f"requests are typical of business-email-compromise fraud.",
                [d.doc_id], category="fraud"))
        if order_total:
            mentioned = [a.value for a in parse_amounts(d.text) if a.value >= 1000]
            if mentioned and order_total.value not in mentioned and any(
                    abs(v - order_total.value) <= order_total.value / 2 for v in mentioned):
                out.append(IntegrityFlag(
                    "EMAIL_CONFLICT", "warning", "Email conflicts with the order",
                    f"{d.doc_id} mentions {', '.join(f'{v:,.0f}' for v in mentioned)} "
                    f"but the order total is {order_total.value:,.0f}. The order document "
                    f"is used; confirm with the customer.",
                    [d.doc_id, facts.order_value.source], category="integrity"))
    for c in facts.model_conflicts:
        out.append(IntegrityFlag("MODEL_CONFLICT", "warning", "Conflicting terms noticed",
                                 c, [], category="integrity"))
    return out
