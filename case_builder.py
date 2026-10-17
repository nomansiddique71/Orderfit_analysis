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
               payment_reading: str | None = None) -> BuildResult:
    """edits: owner corrections keyed by fact name, plus optional
    'supplier_payments': [{"label", "amount", "day"}] replacing the extracted list."""
    edits = edits or {}

    def val(name: str) -> str:
        return str(edits[name]) if name in edits else getattr(facts, name).value

    missing, assumptions = [], []
    order_value = parse_amount(val("order_value"))
    delivery = parse_day(val("delivery_day"))
    terms = parse_day(val("payment_terms_days"))
    if order_value is None:
        missing.append("Order value")
    if delivery is None:
        missing.append("Delivery day")
    if terms is None:
        missing.append("Customer payment terms (days)")

    if "supplier_payments" in edits:
        raw_payments = [(str(p.get("label", "Supplier payment")), str(p.get("amount", "")),
                         str(p.get("day", ""))) for p in edits["supplier_payments"]]
    else:
        raw_payments = [(p.label, p.amount.value, p.day.value) for p in facts.supplier_payments]
    payments = []
    for label, amount, day in raw_payments:
        a, d = parse_amount(amount), parse_day(day)
        if a is None or d is None:
            missing.append(f"Amount/day for '{label}'")
        else:
            payments.append((label, a.value, d))
    if not payments:
        missing.append("At least one supplier payment")

    if missing:
        return BuildResult(None, None, missing)

    basis = (val("payment_terms_basis") or "unspecified").strip().lower()
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
    for label, amount, day in payments:
        shipping = any(w in label.lower() for w in SHIPPING_WORDS)
        costs.append(Movement(
            day, -amount, label, "order_cost",
            "Logistics" if shipping else supplier,
            deferrable_to=(None if shipping or day > delivery
                           else max(day, delivery) + EXTENSION_DAYS_AFTER_DELIVERY),
            tied_to_delivery=day == delivery))
    assumptions.append(f"A supplier extension, if asked for, moves supplier payments due by "
                       f"delivery to day {delivery + EXTENSION_DAYS_AFTER_DELIVERY}.")
    penalty = parse_percent(val("late_penalty_pct_per_week") or "") or D(0)

    customer = (val("customer_name") or "Customer").strip()
    ref = (val("order_ref") or "the order").strip()
    case = Case(
        name=f"{profile.name} -- {ref} ({customer})",
        opening_cash=profile.opening_cash, reserve=profile.reserve,
        order_value=order_value.value, delivery_day=delivery, required_delivery_day=delivery,
        base_movements=tuple(profile.obligations), order_costs=tuple(costs),
        financing_offers=tuple(profile.offers), max_financing_cost=profile.max_financing_cost,
        supplier=supplier, late_penalty_pct_per_week=penalty, customer=customer, order_ref=ref)
    return BuildResult(case, pay_day, [], assumptions, readings, basis)
