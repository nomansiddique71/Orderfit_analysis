"""Build an engine Case from owner-confirmed document facts + a business profile.

The documents describe the order (value, delivery, payment terms, what we pay
the supplier). The business profile describes the company (cash today, the
minimum reserve, existing bills/payroll/receivables, available lenders). Both
are owner-confirmed before the engine runs; nothing here guesses a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from docmodel import Facts
from docparse import parse_amount, parse_day, parse_percent
from engine import Case, FinancingOffer, Movement

D = Decimal
SHIPPING_WORDS = ("ship", "freight", "logistic", "courier", "transport", "delivery charge")
EXTENSION_DAYS_AFTER_DELIVERY = 10  # assumption: what a supplier extension asks for


@dataclass
class BusinessProfile:
    name: str
    currency: str
    opening_cash: Decimal
    reserve: Decimal
    max_financing_cost: Decimal
    obligations: list[Movement]
    offers: list[FinancingOffer]

    def to_json(self) -> dict:
        return {
            "name": self.name, "currency": self.currency,
            "opening_cash": str(self.opening_cash), "reserve": str(self.reserve),
            "max_financing_cost": str(self.max_financing_cost),
            "obligations": [{"day": m.day, "amount": str(m.amount), "label": m.label,
                             "kind": m.kind, "counterparty": m.counterparty,
                             "due_day": m.due_day} for m in self.obligations],
            "offers": [{"id": o.id, "lender": o.lender, "principal": str(o.principal),
                        "terms": o.terms_text(), "draw_day": o.draw_day,
                        "repay_day": o.repay_day} for o in self.offers],
        }


def _doc_note(a) -> str:
    """'In the document: USD 12,000 x 121.4 (2026-03-12)' for a converted amount."""
    return f"In the document: {a.note}" if a is not None and "in the document" in a.note else ""


def _zero_amount(text: str):
    """'0', 'none', 'nil' -> an amount of 0 (parse_amount ignores zero-only text)."""
    from docparse import ParsedAmount

    t = text.strip().lower()
    if t in ("0", "0.0", "none", "nil", "no", "zero", "-"):
        return ParsedAmount(D(0), text)
    return None


def profile_from_json(data: dict) -> BusinessProfile:
    """Validated profile from JSON (sample packs or the owner's edits)."""
    def dec(v, name):
        try:
            return D(str(v).replace(",", ""))
        except Exception as exc:
            raise ValueError(f"profile field '{name}' is not a number: {v!r}") from exc

    obligations = []
    for o in data.get("obligations", []):
        day = int(o["day"])
        if not 0 <= day <= 365:
            raise ValueError(f"obligation day {day} is outside 0-365")
        obligations.append(Movement(day, dec(o["amount"], "amount"), str(o.get("label", ""))[:80],
                                    str(o.get("kind", "obligation")), str(o.get("counterparty", ""))[:80],
                                    due_day=o.get("due_day")))
    offers = []
    for o in data.get("offers", []):
        offers.append(FinancingOffer(
            str(o["id"]), str(o["lender"]), dec(o["principal"], "principal"),
            dec(o.get("fee_pct", 0), "fee_pct"), dec(o.get("origination", 0), "origination"),
            int(o["draw_day"]), int(o["repay_day"]), int(o.get("expires_day", 7)),
            str(o.get("conditions", "")), dec(o.get("monthly_rate_pct", 0), "monthly_rate_pct"),
            dec(o["min_principal"], "min_principal") if o.get("min_principal") else None,
            dec(o["max_principal"], "max_principal") if o.get("max_principal") else None))
    reserve = dec(data["reserve"], "reserve")
    if reserve < 0:
        raise ValueError("the minimum reserve cannot be negative")
    return BusinessProfile(str(data.get("name", "My business"))[:80], str(data.get("currency", "USD"))[:5],
                           dec(data["opening_cash"], "opening_cash"), reserve,
                           dec(data.get("max_financing_cost", 2000), "max_financing_cost"),
                           obligations, offers)


@dataclass
class BuildResult:
    case: Case | None
    customer_payment_day: int | None
    missing: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    payment_readings: dict[str, int] = field(default_factory=dict)  # basis -> day (D-01)
    basis_used: str = ""


def build_case(facts: Facts, profile: BusinessProfile, edits: dict | None = None,
               payment_reading: str | None = None, role: str = "seller",
               fx=None) -> BuildResult:
    """edits: owner corrections keyed by fact name, plus optional
    'supplier_payments': [{"label", "amount", "day"}] replacing the extracted list.

    role "buyer": the deal is a supplier's offer. Costs are the supplier payments;
    the income is what the owner expects to earn from the goods ('expected_income',
    may be 0) arriving 'income_days' after delivery. Customer advances and the
    customer's payment terms do not apply.

    fx: fx.Converter -- amounts written in another currency are converted to the
    profile currency at the rate the owner confirmed; a missing rate is reported
    as missing, never guessed."""
    edits = edits or {}
    buyer = role == "buyer"
    fx_missing: list[str] = []

    def val(name: str) -> str:
        return str(edits[name]) if name in edits else getattr(facts, name).value

    def span(name: str) -> str:
        return "" if name in edits else getattr(facts, name).span

    def money_of(text: str, src: str = ""):
        """(amount in the profile currency, raw text unreadable?)"""
        if fx is None:
            return parse_amount(text)
        a, miss = fx.amount(text, src)
        if miss and miss not in fx_missing:
            fx_missing.append(miss)
        return a

    def unreadable(text: str) -> bool:
        return parse_amount(text) is None

    missing, assumptions = [], []
    delivery = parse_day(val("delivery_day"))
    if buyer:
        income_text = (val("expected_income") or "").strip()
        order_value = (money_of(income_text) or _zero_amount(income_text)) if income_text else None
        terms = parse_day(val("income_days")) if (val("income_days") or "").strip() else None
        if terms is None and order_value is not None and order_value.value == 0:
            terms = 0  # no income: its day does not matter
        if order_value is None and (not income_text or unreadable(income_text) and not _zero_amount(income_text)):
            missing.append("Income you expect from these goods (0 if none)")
        if terms is None:
            missing.append("Days after delivery that income arrives")
    else:
        order_value = money_of(val("order_value"), span("order_value"))
        terms = parse_day(val("payment_terms_days"))
        if order_value is None and unreadable(val("order_value")):
            missing.append("Order value")
        if terms is None:
            missing.append("Customer payment terms (days)")
    if delivery is None:
        missing.append("Goods arrive by (day)" if buyer else "Delivery day")

    advance_text = "" if buyer else (val("advance_received") or "").strip()
    advance = money_of(advance_text, span("advance_received")) if advance_text else None
    if advance_text and advance is None and unreadable(advance_text):
        missing.append("Advance already received (not a readable amount)")
    elif advance and order_value and advance.value > order_value.value:
        missing.append("Advance already received (larger than the order value)")

    if "supplier_payments" in edits:
        spans = [p.amount.span for p in facts.supplier_payments]
        raw_payments = [(str(p.get("label", "Supplier payment")), str(p.get("amount", "")),
                         str(p.get("day", "")), bool(p.get("paid", False)),
                         spans[i] if i < len(spans) else "")
                        for i, p in enumerate(edits["supplier_payments"])]
    else:
        raw_payments = [(p.label, p.amount.value, p.day.value, p.already_paid, p.amount.span)
                        for p in facts.supplier_payments]
    payments, already_paid = [], D(0)
    for label, amount, day, paid, src in raw_payments:
        a = money_of(amount, src)
        if paid and a is not None:  # already out of the bank: no date needed
            already_paid += a.value
            continue
        d = parse_day(day)
        if a is None and not unreadable(amount):
            continue  # its exchange rate is missing: reported once below
        if a is None or d is None:
            missing.append(f"Amount/day for '{label}'")
        else:
            payments.append((label, a.value, d, _doc_note(a)))
    if not payments and not already_paid:
        missing.append("At least one supplier payment")

    missing += fx_missing
    if missing:
        return BuildResult(None, None, missing)

    basis = "after_delivery" if buyer else (val("payment_terms_basis") or "unspecified").strip().lower()
    readings = {}
    if basis in ("after_delivery", "after_invoice"):
        pay_day = delivery + terms
        if basis == "after_invoice":
            assumptions.append("Invoice assumed to be issued on the delivery day.")
    elif basis == "after_order":
        pay_day = terms
    else:  # D-01: "Net N" with no start date -- two readings, safer one by default
        readings = {"after_order": terms, "after_delivery": delivery + terms}
        chosen = payment_reading if payment_reading in readings else "after_delivery"
        pay_day = readings[chosen]
        basis = chosen
        assumptions.append(f"Payment terms have no start date; using the "
                           f"{'later, safer' if chosen == 'after_delivery' else 'owner-chosen'} "
                           f"reading (day {pay_day}).")

    supplier = (val("supplier_name") or "Supplier").strip()
    costs = []
    for label, amount, day, note in payments:
        shipping = any(w in label.lower() for w in SHIPPING_WORDS)
        costs.append(Movement(
            day, -amount, label, "order_cost",
            "Logistics" if shipping else supplier,
            deferrable_to=(None if shipping or day > delivery
                           else max(day, delivery) + EXTENSION_DAYS_AFTER_DELIVERY),
            tied_to_delivery=day == delivery, note=note))
    assumptions.append(f"A supplier extension, if asked for, moves supplier payments due by "
                       f"delivery to day {delivery + EXTENSION_DAYS_AFTER_DELIVERY}.")
    penalty = D(0) if buyer else parse_percent(val("late_penalty_pct_per_week") or "") or D(0)

    customer = ("Your sales of the goods" if buyer
                else (val("customer_name") or "Customer").strip())
    ref = (val("order_ref") or ("the offer" if buyer else "the order")).strip()
    case = Case(
        name=(f"{profile.name} -- {ref} (offer from {supplier})" if buyer
              else f"{profile.name} -- {ref} ({customer})"),
        opening_cash=profile.opening_cash, reserve=profile.reserve,
        order_value=order_value.value, delivery_day=delivery, required_delivery_day=delivery,
        base_movements=tuple(profile.obligations), order_costs=tuple(costs),
        financing_offers=tuple(profile.offers), max_financing_cost=profile.max_financing_cost,
        supplier=supplier, late_penalty_pct_per_week=penalty, customer=customer, order_ref=ref,
        advance_received=advance.value if advance else D(0), costs_already_paid=already_paid,
        currency=profile.currency, role=role, income_note=_doc_note(order_value))
    if buyer:
        assumptions.append(
            f"You are the buyer: you pay {supplier} {sum(a for _, a, _, _ in payments) + already_paid:,.0f} "
            + (f"and expect {order_value.value:,.0f} from the goods on day {pay_day}."
               if order_value.value else "and expect no income from these goods within the plan."))
    if advance:
        assumptions.append(f"The customer already paid {advance.value:,.0f} in advance; it is "
                           f"already in today's cash, so they still owe {case.balance_due:,.0f}.")
    if already_paid:
        assumptions.append(f"{already_paid:,.0f} already paid to the supplier is already out of "
                           f"today's cash; it still counts as an order cost for margin.")
    return BuildResult(case, pay_day, [], assumptions, readings, basis)
