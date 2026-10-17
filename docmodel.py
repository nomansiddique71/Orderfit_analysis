"""Typed facts read from uploaded commercial documents.

Every fact keeps the document it came from and the exact quoted span, so the
verifier can check it against the source text and the owner can see where it
came from. Values stay as the text the reader saw; docparse.py turns them into
exact numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Document:
    doc_id: str  # "DOC-1", ...
    filename: str
    kind: str  # purchase_order | supplier_quote | invoice | email | other
    text: str  # extracted text layer ("" for a scanned PDF)
    pdf_bytes: bytes | None = None  # kept only for scanned PDFs sent to Gemini

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


@dataclass
class Fact:
    value: str
    source: str = ""  # doc_id
    span: str = ""  # verbatim text in the source document
    confidence: float = 0.0
    verified: bool = False  # span found in source text and value consistent with it
    note: str = ""  # verifier or parser note shown to the owner

    @property
    def present(self) -> bool:
        return bool(self.value.strip())


@dataclass
class SupplierPayment:
    label: str
    amount: Fact
    day: Fact
    already_paid: bool = False  # paid before today: counts for margin, not a future outflow


@dataclass
class BankDetail:
    source: str  # doc_id
    payee: str
    bank_name: str
    account_number: str
    span: str = ""
    confidence: float = 0.0
    verified: bool = False


@dataclass
class LineItem:
    description: str
    amount: Fact


@dataclass
class Facts:
    """Everything the order decision needs from the documents."""

    customer_name: Fact = field(default_factory=lambda: Fact(""))
    order_ref: Fact = field(default_factory=lambda: Fact(""))
    order_value: Fact = field(default_factory=lambda: Fact(""))
    delivery_day: Fact = field(default_factory=lambda: Fact(""))
    payment_terms_days: Fact = field(default_factory=lambda: Fact(""))
    payment_terms_basis: Fact = field(default_factory=lambda: Fact(""))  # after_delivery | after_invoice | after_order | unspecified
    late_penalty_pct_per_week: Fact = field(default_factory=lambda: Fact(""))
    cancellation_clause: Fact = field(default_factory=lambda: Fact(""))
    supplier_name: Fact = field(default_factory=lambda: Fact(""))
    invoice_amount: Fact = field(default_factory=lambda: Fact(""))
    advance_received: Fact = field(default_factory=lambda: Fact(""))  # customer advance already paid
    customer_email: Fact = field(default_factory=lambda: Fact(""))
    supplier_email: Fact = field(default_factory=lambda: Fact(""))
    supplier_payments: list[SupplierPayment] = field(default_factory=list)
    line_items: list[LineItem] = field(default_factory=list)
    bank_details: list[BankDetail] = field(default_factory=list)
    instructions_found: list[tuple[str, str]] = field(default_factory=list)  # (doc_id, span)
    model_conflicts: list[str] = field(default_factory=list)  # conflicts the reader noticed

    SCALAR_FIELDS = (
        "customer_name", "order_ref", "order_value", "delivery_day", "payment_terms_days",
        "payment_terms_basis", "late_penalty_pct_per_week", "cancellation_clause",
        "supplier_name", "invoice_amount", "advance_received", "customer_email", "supplier_email",
    )

    def scalars(self) -> dict[str, Fact]:
        return {name: getattr(self, name) for name in self.SCALAR_FIELDS}


# Human labels shown in the UI and used as ExtractedField names.
FACT_LABELS = {
    "customer_name": "Customer",
    "order_ref": "Order reference",
    "order_value": "Order value",
    "delivery_day": "Delivery required by (day)",
    "payment_terms_days": "Customer payment terms (days)",
    "payment_terms_basis": "Payment terms start from",
    "late_penalty_pct_per_week": "Late-delivery penalty (% per week)",
    "cancellation_clause": "Cancellation clause",
    "supplier_name": "Supplier",
    "invoice_amount": "Supplier invoice amount",
    "advance_received": "Advance already received from the customer",
    "customer_email": "Customer email",
    "supplier_email": "Supplier email",
}

# Facts that change a dated cash movement or a hard constraint: a
# low-confidence or unverified value here makes the result provisional.
SIMULATION_FACTS = {"order_value", "delivery_day", "payment_terms_days", "payment_terms_basis",
                    "late_penalty_pct_per_week", "advance_received"}
