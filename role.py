"""Which side of the deal is the owner on: seller (a customer's order) or buyer
(a supplier's offer)?

The owner states a usual role on the company profile; for each case SolvOrder
also reads the documents and compares the parties with the owner's company name
and email. If the documents point the other way, the owner is asked -- the role
is never switched silently.

  detect_role()   deterministic: company name / email domain against the
                  'Buyer', 'Seller', 'To', 'Bill to' and email fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from docmodel import Document, Facts

SUFFIXES = {"ltd", "limited", "co", "company", "inc", "llc", "plc", "pvt", "private", "corp",
            "corporation", "the", "and", "group"}
ROLE_TEXT = {"seller": "the seller (a customer's order)", "buyer": "the buyer (a supplier's offer)"}


@dataclass(frozen=True)
class RoleGuess:
    role: str | None  # seller | buyer | None (documents do not say)
    evidence: str  # quoted reason, shown to the owner


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in SUFFIXES}


def same_company(a: str, b: str) -> bool:
    """'Acme Trading Co.' == 'ACME TRADING' -- every core word of the shorter name
    appears in the longer one (suffixes such as Ltd/Co/Pvt ignored)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return small <= big


def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""


_LINE = r"^\s*{label}\s*[:\-]\s*(?P<v>.+)$"


def _line(doc: Document, *labels: str) -> str:
    for label in labels:
        m = re.search(_LINE.format(label=label), doc.text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group("v").strip()
    return ""


def detect_role(facts: Facts, docs: list[Document], company: str, company_email: str = "") -> RoleGuess:
    """The owner's side of this deal according to the documents, or None."""
    company, domain = company.strip(), _domain(company_email)
    if not company and not domain:
        return RoleGuess(None, "Add your company name on the profile so SolvOrder can check the documents.")
    me = lambda name: bool(name) and same_company(company, name)  # noqa: E731
    mine = lambda email: bool(domain) and _domain(email) == domain  # noqa: E731

    if me(facts.customer_name.value) or mine(facts.customer_email.value):
        return RoleGuess("buyer", f"The documents name you as the buyer "
                                  f"('{facts.customer_name.value or facts.customer_email.value}').")
    for d in docs:
        seller = _line(d, "Seller", "Vendor", "Sold by")
        if me(seller) or mine(_line(d, "Seller email", "Vendor email")):
            return RoleGuess("seller", f"{d.filename} names you as the seller ('{seller or company}').")
    if me(facts.supplier_name.value) or mine(facts.supplier_email.value):
        return RoleGuess("seller", f"The documents name you as the supplier "
                                   f"('{facts.supplier_name.value or facts.supplier_email.value}').")
    has_po = any(d.kind == "purchase_order" for d in docs)
    for d in docs:
        if d.kind in ("supplier_quote", "invoice"):
            to = _line(d, "To", "Bill to", "Customer", "Buyer")
            if me(to) and not has_po:
                return RoleGuess("buyer", f"{d.filename} is a supplier's offer addressed to you ('{to}').")
    if facts.customer_name.present and not me(facts.customer_name.value) and has_po:
        return RoleGuess("seller", f"The purchase order comes from another company "
                                   f"('{facts.customer_name.value}'), so you are selling to them.")
    return RoleGuess(None, "The documents do not show which side you are on.")
