"""What else SolvOrder needs to know before it can judge the order.

After the owner uploads documents (option 2) or types the order (option 3),
the documents describe the ORDER but not the BUSINESS: cash in the bank, the
reserve, payroll and other bills, money owed to the business, loan offers.
Without these the cash simulation would be meaningless.

  rule_needs()   deterministic checklist: missing order facts + every business
                 fact the owner has not given yet. Always available.
  gemini_needs() Gemini reads the documents and the facts so far and picks,
                 from the SAME fixed list of keys, what it needs, phrased for
                 this case and with a reason tied to the documents. It cannot
                 add a field the engine does not understand: unknown keys are
                 dropped, and every rule-based need is kept.

The answers come back through /api/profile (business facts) and the normal
fact edits (order facts); the engine, not the model, uses them.
"""

from __future__ import annotations

from dataclasses import dataclass

from docparse import parse_amount, parse_day

# key -> (widget, default question, why it matters)
NEEDS: dict[str, tuple[str, str, str]] = {
    "business_name": ("text", "What is your business called?",
                      "Used in drafted messages and the report."),
    "currency": ("currency", "Which currency do you work in?",
                 "All amounts are read and shown in this currency."),
    "opening_cash": ("amount", "How much cash is in your business bank account today?",
                     "Every day's balance starts from this number."),
    "reserve": ("amount", "What is the lowest cash balance you never want to go below?",
                "A plan is only safe if cash stays above this reserve every day."),
    "recurring": ("payments", "What regular payments are due in the next 90 days (payroll, rent, "
                              "supplier bills, loan instalments)?",
                  "These leave your account while you wait for the customer to pay; they "
                  "usually decide whether the order fits."),
    "receivables": ("receipts", "Who already owes you money, how much, and when do you expect it?",
                    "Money arriving before your tightest day can carry the order."),
    "loan_offers": ("offers", "Do you have any loan or credit-line offers you could use?",
                    "SolvOrder can size the smallest safe loan, but only from real offers: "
                    "it never invents loan terms."),
    "max_financing_cost": ("amount", "What is the most you would pay in fees and interest to "
                                     "finance this order?",
                           "Loans costing more than this are ruled out."),
    "order_value": ("amount", "What is the total value of the order?",
                    "The money the customer will pay you."),
    "delivery_day": ("day", "By which day must you deliver (days from today)?",
                     "Order costs and the customer's payment are timed from delivery."),
    "payment_terms_days": ("day", "How many days after delivery does the customer pay?",
                           "This sets the day the money arrives."),
    "advance_received": ("amount", "Has the customer already paid you an advance for this order? "
                                   "How much?",
                         "Money already received is in today's cash and reduces what they still owe."),
    # buyer deals: the owner pays a supplier; what comes back is the owner's own income
    "expected_income": ("amount", "How much do you expect to earn from these goods (selling or using "
                                  "them)? Enter 0 if none within the next months.",
                        "This is the money that comes back in after you pay the supplier; without "
                        "it SolvOrder only sees the payments going out."),
    "income_days": ("day", "How many days after the goods arrive do you expect that money?",
                    "Sets the day the income reaches your account."),
    "deal_role": ("role", "In this deal, are you the seller or the buyer?",
                  "The documents and your profile disagree."),
    "fx_rates": ("fx", "Which exchange rate should SolvOrder use for the document amounts?",
                 "Your documents are in another currency than your business. Every amount is "
                 "converted to your profile currency; Gemini could not find the rate for the "
                 "document date, so please enter it."),
}

BUSINESS_KEYS = ("business_name", "currency", "opening_cash", "reserve", "recurring",
                 "receivables", "loan_offers", "max_financing_cost")
ORDER_KEYS = ("order_value", "delivery_day", "payment_terms_days", "advance_received",
              "expected_income", "income_days", "deal_role", "fx_rates")
SELLER_KEYS = {"order_value", "payment_terms_days", "advance_received"}
BUYER_KEYS = {"expected_income", "income_days"}


def allowed_keys(role: str) -> list[str]:
    """Keys Gemini may pick for this side of the deal."""
    drop = SELLER_KEYS if role == "buyer" else BUYER_KEYS
    return [k for k in NEEDS if k not in drop and k not in ("deal_role", "fx_rates")]
MAX_TEXT = 300


@dataclass
class Need:
    key: str
    question: str
    why: str
    widget: str
    source: str  # "gemini" | "rules"
    required: bool

    def to_json(self) -> dict:
        return {"key": self.key, "question": self.question, "why": self.why,
                "widget": self.widget, "source": self.source, "required": self.required}


def _rule(key: str, required: bool) -> Need:
    widget, question, why = NEEDS[key]
    return Need(key, question, why, widget, "rules", required)


def rule_needs(facts, edits: dict, profile_source: str,
               known: frozenset[str] = frozenset(), role: str = "seller",
               role_conflict: bool = False, fx_missing: list[str] | None = None) -> list[Need]:
    """Missing deal facts first, then business facts the owner has not given.
    known: keys the owner's company profile already answers (e.g. currency).
    role: the owner's side; a buyer is asked about income from the goods instead
    of the customer's payment. role_conflict: documents and profile disagree."""
    def val(name: str) -> str:
        return str(edits[name]) if name in edits else getattr(facts, name).value

    out: list[Need] = []
    if role_conflict:
        out.append(_rule("deal_role", True))
    if fx_missing:  # currencies whose rate Gemini could not find
        out.append(_rule("fx_rates", True))
    if role == "buyer":
        income = val("expected_income").strip()
        if not income:
            out.append(_rule("expected_income", True))
        if (not income or income not in ("0", "none", "nil")) and parse_day(val("income_days")) is None:
            out.append(_rule("income_days", True))
    else:
        if parse_amount(val("order_value")) is None:
            out.append(_rule("order_value", True))
        if parse_day(val("payment_terms_days")) is None:
            out.append(_rule("payment_terms_days", True))
        if not val("advance_received").strip():
            out.append(_rule("advance_received", False))
    if parse_day(val("delivery_day")) is None:
        out.append(_rule("delivery_day", True))
    if profile_source == "default":  # nobody has given business facts yet
        for key in BUSINESS_KEYS:
            if key not in known:
                out.append(_rule(key, key in ("opening_cash", "reserve", "recurring")))
    return sorted(out, key=lambda n: not n.required)  # required first, order kept


def merge(rules: list[Need], model: list[dict], known: frozenset[str] = frozenset()) -> list[Need]:
    """Gemini's picks (allowed keys only, its wording) first, then every rule need
    it skipped. A need the rules mark required stays required. Keys the company
    profile already answers are never asked, whoever picks them."""
    required = {n.key: n.required for n in rules}
    out: dict[str, Need] = {}
    for item in model:
        key = str(item.get("key", "")).strip()
        if key not in NEEDS or key in out or key in known or key in ("deal_role", "fx_rates"):
            continue
        widget, question, why = NEEDS[key]
        q = str(item.get("question", "")).strip()[:MAX_TEXT] or question
        w = str(item.get("why", "")).strip()[:MAX_TEXT] or why
        out[key] = Need(key, q, w, widget, "gemini", required.get(key, False))
    for n in rules:
        out.setdefault(n.key, n)
    return list(out.values())
