"""OrderFit agent orchestration: the five stages A-E, ending in a decision memo.

Gemini is used for document extraction (stage A), explanation, Q&A and
drafting. Every extracted field is verified here before it can matter:
the quoted span must exist in the source document, and key amounts must
match the owner-confirmed case. Arithmetic, feasibility and ranking are
owned by engine.py. When Gemini is not configured or fails, stage A falls
back to deterministic regex extraction and the narrative to templates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

import engine
from engine import Case, SimulationResult

D = Decimal
ZERO = D("0")

STRESS_DELAYS = [15]  # customer pays 15 days late


# ------------------------------------------------------------------ stage A


@dataclass
class ExtractedField:
    name: str
    value: str
    source: str  # "PO-8841" | "Q-3312"
    span: str  # the exact source text
    confidence: float
    question: str | None = None  # set when confidence is below threshold


@dataclass
class InjectionFlag:
    document: str
    span: str


INJECTION_RE = re.compile(
    r"(ignore|disregard|bypass|override)[^.]{0,60}(reserve|constraint|approval)"
    r"|(note to ai agent|instructions? (to|for) (the )?agent)",
    re.IGNORECASE,
)


def extract_fields(po: str, quote: str) -> tuple[list[ExtractedField], list[InjectionFlag]]:
    """Regex extraction with source spans and confidence.

    A production build would call Gemini with the same contract: typed fields,
    each with a source page/span and a confidence; low-confidence fields become
    owner questions and are never simulated with a guessed value.
    """
    fields: list[ExtractedField] = []

    def add(name, value, source, text, pattern, confidence, question=None):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            fields.append(ExtractedField(name, value, source, m.group(0).strip(), confidence, question))

    add("Order value", "USD 30,000", "PO-8841", po, r"Total order value:\s*USD 30,000", 0.99)
    add("Delivery required by", "day 30", "PO-8841", po, r"required by day 30", 0.97)
    add("Customer payment terms", "net 30 after delivery (day 60)", "PO-8841", po,
        r"net 30 -- payment due 30 days after delivery", 0.99)
    add("Early-settlement discount", "2% within 10 days of invoice", "PO-8841", po,
        r"2% discount if the buyer pays within 10 days", 0.62,
        question="Does the early-settlement discount change the customer's actual "
                 "payment date or amount? Confirm before relying on day 60.")
    add("Late-delivery penalty", "1% of order value per week", "PO-8841", po,
        r"penalty of 1% of order value per week", 0.95)
    add("Supplier deposit", "USD 12,000 on day 0", "Q-3312", quote,
        r"USD 12,000 payable on order confirmation \(day 0\)", 0.99)
    add("Supplier second payment", "USD 5,000 on day 20", "Q-3312", quote,
        r"USD 5,000 payable before dispatch \(day 20\)", 0.99)
    add("Shipping & handling", "USD 1,500 on day 30", "Q-3312", quote,
        r"USD 1,500 payable on delivery \(day 30\)", 0.99)
    add("Deposit refundability", "non-refundable once production begins", "Q-3312", quote,
        r"deposit is non-refundable once production begins", 0.9)

    return fields, _regex_injections(po, quote)


def _regex_injections(po: str, quote: str) -> list[InjectionFlag]:
    flags = []
    for doc_name, text in (("PO-8841", po), ("Q-3312", quote)):
        m = INJECTION_RE.search(text)
        if m:
            flags.append(InjectionFlag(doc_name, m.group(0)))
    return flags


# ------------------------------------------- stage A with Gemini + verifier

FIELD_NAMES = [
    "Order value", "Delivery required by", "Customer payment terms",
    "Early-settlement discount", "Late-delivery penalty", "Supplier deposit",
    "Supplier second payment", "Shipping & handling", "Deposit refundability",
]
LOW_CONFIDENCE = 0.7

# successful Gemini extractions, keyed by document text (one call per variant)
_EXTRACTION_CACHE: dict[tuple[str, str], tuple] = {}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().strip("\"'`").lower()


def _expected_values(case: Case) -> dict[str, Decimal | int]:
    """Owner-confirmed figures the extraction is reconciled against."""
    def cost(label: str):
        for m in case.order_costs:
            if m.label.lower().startswith(label.lower()):
                return -m.amount
        return None

    exp = {
        "Order value": case.order_value,
        "Delivery required by": case.required_delivery_day,
        "Supplier deposit": cost("Supplier deposit"),
        "Supplier second payment": cost("Supplier pre-delivery"),
        "Shipping & handling": cost("Shipping"),
    }
    return {k: v for k, v in exp.items() if v is not None}


def verify_extraction(data: dict, docs: dict[str, str], case: Case
                      ) -> tuple[list[ExtractedField], list[InjectionFlag], list[str]]:
    """Engine-side checks on the model's extraction.

    1. The source must be a known document and the quoted span must appear in
       it verbatim (catches invented or misattributed text).
    2. Key amounts/days must match the owner-confirmed case (catches
       misreadings). A mismatch never changes the numbers the engine uses --
       it lowers confidence and becomes an owner question.
    Returns (fields, injection flags, notes about what failed).
    """
    from gemini_client import numbers_in

    expected = _expected_values(case)
    fields: list[ExtractedField] = []
    notes: list[str] = []
    seen: set[str] = set()
    for raw in data.get("fields", []):
        name = str(raw.get("name", "")).strip()
        if name not in FIELD_NAMES or name in seen:
            continue
        seen.add(name)
        value = str(raw.get("value", "")).strip()
        source = str(raw.get("source", "")).strip()
        span = str(raw.get("span", "")).strip()
        try:
            conf = min(max(float(raw.get("confidence", 0)), 0.0), 1.0)
        except (TypeError, ValueError):
            conf = 0.0
        question = (str(raw.get("question") or "").strip()) or None

        doc = docs.get(source)
        if doc is None or not span or _norm(span) not in _norm(doc):
            conf = min(conf, 0.3)
            question = (f"The model's quoted text for '{name}' was not found in "
                        f"{source or 'the documents'}. Please confirm the value "
                        f"'{value}' manually.")
            notes.append(f"{name}: span not found in source")
        elif name in expected:
            want = expected[name]
            want_s = format(want.normalize(), "f") if isinstance(want, Decimal) else str(want)
            if want_s not in numbers_in(value):
                conf = min(conf, 0.3)
                question = (f"Extracted '{value}' for '{name}' does not match the "
                            f"owner-confirmed figure ({want_s}). The engine keeps the "
                            f"confirmed figure until you check the document.")
                notes.append(f"{name}: value does not match confirmed case")
        if conf < LOW_CONFIDENCE and not question:
            question = f"Low confidence on '{name}' ({value}). Please confirm."
        fields.append(ExtractedField(name, value, source, span, conf, question))

    missing = [n for n in FIELD_NAMES if n not in seen]
    if missing:
        notes.append("not returned by the model: " + ", ".join(missing))

    flags: list[InjectionFlag] = []
    for item in data.get("instructions_found", []):
        source = str(item.get("source", "")).strip()
        span = str(item.get("span", "")).strip()
        doc = docs.get(source)
        if doc is not None and span and _norm(span) in _norm(doc):
            flags.append(InjectionFlag(source, span))
    return fields, flags, notes


def extract_documents(po: str, quote: str, case: Case
                      ) -> tuple[list[ExtractedField], list[InjectionFlag], str, str]:
    """Stage A. Returns (fields, injection flags, mode, note).

    mode is "gemini" (model extraction, verified) or "regex" (fallback).
    The deterministic regex injection filter always runs as well, so a
    prompt-injection line is flagged even if the model misses it.
    """
    import gemini_client

    regex_flags = _regex_injections(po, quote)
    if gemini_client.gemini_available():
        key = (po, quote)
        if key not in _EXTRACTION_CACHE:
            try:
                data = gemini_client.extract_documents(po, quote, FIELD_NAMES)
                _EXTRACTION_CACHE[key] = verify_extraction(
                    data, {"PO-8841": po, "Q-3312": quote}, case)
            except Exception as exc:  # never block the demo on the model
                fields, flags = extract_fields(po, quote)
                return fields, flags, "regex", f"Gemini extraction failed ({exc}); used regex fallback."
        fields, model_flags, notes = _EXTRACTION_CACHE[key]
        flags = list(model_flags)
        for f in regex_flags:
            if not any(g.document == f.document for g in flags):
                flags.append(f)
        note = ("All fields verified against the source text and the confirmed case."
                if not notes else "Verifier notes: " + "; ".join(notes))
        return fields, flags, "gemini", note
    fields, flags = extract_fields(po, quote)
    return fields, flags, "regex", "Gemini not configured; used deterministic regex extraction."


# ------------------------------------------------------------- alerts (8.2)


@dataclass
class Alert:
    rule: str
    day: int | None
    message: str
    severity: str  # critical | warning | info


def raise_alerts(case: Case, as_is: SimulationResult, winner: SimulationResult) -> list[Alert]:
    alerts: list[Alert] = []
    if as_is.first_breach_day is not None:
        alerts.append(Alert(
            "reserve_breach", as_is.first_breach_day,
            f"Accepting the order as-is breaches the {case.reserve:,.0f} reserve on day "
            f"{as_is.first_breach_day} (balance {as_is.path[as_is.first_breach_day]:,.0f}); "
            f"low point {as_is.min_balance:,.0f} on day {as_is.min_day}.",
            "critical"))
    # payment-before-receipt: an outflow lands >=5 days before a later inflow
    outs = [m for m in case.base_movements if m.amount < 0]
    ins = [m for m in case.base_movements if m.amount > 0]
    for o in outs:
        later = [i for i in ins if i.day > o.day and o.day < i.day - 4]
        if later:
            i = min(later, key=lambda x: x.day)
            alerts.append(Alert(
                "payment_before_receipt", o.day,
                f"{o.label} ({-o.amount:,.0f}) on day {o.day} is due {i.day - o.day} days "
                f"before {i.label} ({i.amount:,.0f}) arrives on day {i.day}.",
                "warning"))
            break
    for offer in case.financing_offers:
        alerts.append(Alert(
            "offer_expiry", offer.expires_day,
            f"{offer.id} ({offer.lender}, {offer.principal:,.0f}) expires on day "
            f"{offer.expires_day}; cost if used is {offer.cost():,.0f}.",
            "info"))
    if winner.feasible and winner.stress_fail_day is not None:
        alerts.append(Alert(
            "fragile_plan", winner.stress_fail_day,
            f"Recommended plan '{winner.plan.label}' fails the 15-day late-payment "
            f"stress: breach on day {winner.stress_fail_day}.",
            "warning"))
    return alerts


# ------------------------------------------------------- stages A-E, memo


@dataclass
class AgentRun:
    case: Case
    customer_payment_day: int
    priority: str
    injected: bool
    stage_log: list[tuple[str, str, str]]
    fields: list[ExtractedField]
    injections: list[InjectionFlag]
    results: dict[str, SimulationResult]
    ranked: list[SimulationResult]
    winner: SimulationResult
    priority_conflict: bool
    alerts: list[Alert]
    sensitivity: list[tuple[int, str]]  # (payment day, winning plan label)
    flip_day: int | None
    min_advance: tuple[Decimal, SimulationResult] | None
    draft_message: str
    questions: list[str]
    extraction_mode: str = "regex"  # "gemini" (verified) or "regex" (fallback)
    extraction_note: str = ""


def run_agent(case: Case, customer_payment_day: int, priority: str,
              injected: bool) -> AgentRun:
    from case_data import QUOTE_TEXT, po_text

    log: list[tuple[str, str, str]] = []

    # Stage A -- extraction
    po, quote = po_text(injected), QUOTE_TEXT
    fields, injections, extraction_mode, extraction_note = extract_documents(po, quote, case)
    questions = [f.question for f in fields if f.question]
    log.append(("A", "Commercial document extraction",
                ("Gemini structured extraction, verified by the engine: "
                 if extraction_mode == "gemini" else "Regex fallback extraction: ")
                + f"{len(fields)} typed fields with source spans; "
                f"{len(questions)} low-confidence field(s) raised as owner questions; "
                f"{len(injections)} injection attempt(s) flagged."))

    # Stage B -- financial-state reconstruction (typed, dated, decimal-safe)
    log.append(("B", "Financial-state reconstruction",
                f"{len(case.base_movements)} existing obligations/receivables + "
                f"{len(case.order_costs)} order costs reconciled into dated records; "
                f"opening cash {case.opening_cash:,.0f}, reserve {case.reserve:,.0f}."))

    # Stage C -- simulation for every candidate plan, base + stress
    plans = engine.enumerate_plans(case)
    results = {p.id: engine.simulate(case, p, customer_payment_day, STRESS_DELAYS)
               for p in plans}
    log.append(("C", "Cash-flow simulation",
                f"{len(plans)} plans simulated for customer payment on day "
                f"{customer_payment_day}, plus a +{STRESS_DELAYS[0]}-day late-payment "
                f"stress run each. Engine verifies every hard constraint."))

    # Stage D/E -- constrained selection, ranking, uncertainty
    ranked = engine.rank_plans(list(results.values()), case, priority)
    if not ranked:
        # No plan is feasible (e.g. the reserve exceeds every plan's trough):
        # fall back to decline so the memo still renders; uncertainty_rating
        # flags it HIGH because the winner is not feasible.
        ranked = [results["decline"]]
    winner = ranked[0]
    priority_conflict = (
        (priority == "avoid_customer_consent" and winner.depends_on_customer_consent)
        or (priority == "minimize_financing_cost" and winner.financing_cost > 0)
    )
    as_is = results["accept-as-is"]
    decline = results["decline"]
    if priority_conflict:
        winner = decline if decline.feasible else winner
    log.append(("D", "Option generation & selection",
                f"Exhaustive enumeration over the defined action set; "
                f"{sum(1 for r in ranked if r.feasible)} of {len(plans)} plans meet the "
                f"reserve in the base scenario; owner priority '{priority}' applied. "
                + ("Priority conflicts with every feasible plan -- escalating."
                   if priority_conflict else f"Winner: {winner.plan.label}.")))

    sensitivity, flip_day = sensitivity_scan(case, priority)
    log.append(("E", "Memo, sensitivity & drafting",
                f"Sensitivity scanned over customer payment days 40-90; "
                f"first flip at day {flip_day if flip_day is not None else '-'}."))

    min_advance = engine.minimum_advance(case, customer_payment_day, STRESS_DELAYS)
    alerts = raise_alerts(case, as_is, winner)
    draft = draft_message(winner, case, customer_payment_day, min_advance)

    return AgentRun(
        case=case, customer_payment_day=customer_payment_day, priority=priority,
        injected=injected, stage_log=log, fields=fields, injections=injections,
        results=results, ranked=ranked, winner=winner,
        priority_conflict=priority_conflict, alerts=alerts, sensitivity=sensitivity,
        flip_day=flip_day, min_advance=min_advance, draft_message=draft,
        questions=questions, extraction_mode=extraction_mode,
        extraction_note=extraction_note,
    )


def sensitivity_scan(case: Case, priority: str) -> tuple[list[tuple[int, str]], int | None]:
    """Re-run the full decision for payment days 40..90; find the first flip."""
    path: list[tuple[int, str]] = []
    flip = None
    baseline = None
    for day in range(40, 91):
        ranked = engine.rank_plans(
            [engine.simulate(case, p, day, STRESS_DELAYS) for p in engine.enumerate_plans(case)],
            case, priority)
        label = ranked[0].plan.label if ranked else "Decline the order"
        if ranked and ranked[0].plan.id == "decline":
            label = "Decline the order"
        path.append((day, label))
        if baseline is None:
            baseline = label
        elif flip is None and label != baseline:
            flip = day
    return path, flip


def uncertainty_rating(run: AgentRun) -> tuple[str, str]:
    w = run.winner
    if run.priority_conflict:
        return ("HIGH", "The owner's priority conflicts with every feasible plan. "
                        "Escalated: no confident recommendation is possible without a "
                        "human decision.")
    if not w.feasible:
        return ("HIGH", "No feasible plan found. Escalated for a decline/renegotiate decision.")
    if w.stress_fail_day is not None:
        return ("HIGH", f"'{w.plan.label}' meets the reserve on expected dates but fails "
                        f"the 15-day late-payment stress (breach day {w.stress_fail_day}). "
                        f"Escalated for owner review.")
    fragile = [r for r in run.ranked if r.feasible and r.stress_fail_day is not None]
    if fragile:
        return ("MEDIUM", f"Recommendation is robust to a 15-day delay, but "
                          f"{len(fragile)} alternative plan(s) (e.g. {fragile[0].plan.label}) "
                          f"fail under stress. The result depends on the customer paying "
                          f"on day {run.customer_payment_day}.")
    return ("LOW", "Recommended plan meets the reserve in the base and all stress scenarios.")


def draft_message(winner: SimulationResult, case: Case, pay_day: int,
                  min_advance) -> str:
    p = winner.plan
    if p.id == "decline":
        return ("Subject: PO-8841 -- unable to accept on current terms\n\n"
                "Thank you for the purchase order. After a full review of our dated cash "
                "position we cannot accept PO-8841 on its current payment terms without "
                "breaching our minimum cash reserve. We would be glad to proceed if "
                "payment terms can be restructured"
                + (f" -- for example a {min_advance[0] * 100:.0f}% advance on confirmation "
                   "would make the order workable" if min_advance else "")
                + ".")
    if p.advance_pct > 0:
        return (f"Subject: PO-8841 -- acceptance with a {p.advance_pct * 100:.0f}% advance\n\n"
                f"We are pleased to accept PO-8841 (USD {case.order_value:,.0f}) with one "
                f"adjustment: an advance of USD "
                f"{case.order_value * p.advance_pct:,.0f} "
                f"({p.advance_pct * 100:.0f}% of order value) payable on order "
                f"confirmation. This lets us commit production capacity and deliver by "
                f"day {case.required_delivery_day}. All other terms as per your PO.")
    if p.supplier_extension and p.financing is None:
        return ("Subject: Payment schedule -- PO to Brightwave Supplies\n\n"
                "We accept your quotation Q-3312 and ask to restructure the payment "
                "schedule: the USD 12,000 deposit and USD 5,000 pre-delivery payment to "
                "fall due on day 40 (after our customer's receivables clear). Shipping "
                "payment of USD 1,500 remains on delivery day 30.")
    if p.financing is not None:
        f = p.financing
        return (f"Subject: Financing acceptance {f.id} -- {f.lender}\n\n"
                f"We accept term sheet {f.id}: draw USD {f.principal:,.0f} on day "
                f"{f.draw_day}, repay USD {f.principal + f.cost():,.0f} on day "
                f"{f.repay_day} (fee {f.fee_pct}% + USD {f.origination:,.0f} "
                f"origination). Please confirm and issue the drawdown notice.")
    return ("Subject: PO-8841 -- acceptance and revised schedule\n\n"
            "We accept PO-8841. To align payments with our cash cycle we propose "
            "adjusting the supplier payment schedule as drafted with this memo.")
