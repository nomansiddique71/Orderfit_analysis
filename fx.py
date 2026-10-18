"""Currency conversion: every amount in the owner's profile currency.

Documents may be written in another currency (a USD quote for a BDT business).
The amounts keep their original text (shown next to every converted value);
the cash engine works only in the profile currency.

  Gemini + Google Search finds the exchange rate for the document's date
  (lookup); the owner can correct it (owner rate). Gemini only proposes the
  rate: the multiplication is exact Decimal arithmetic here, never the model's.
  A rate far outside a rough reference band is flagged for the owner, so a
  misread (e.g. the inverse rate) is caught before it changes the decision.
  No document date -> today's rate, labelled as such.
"""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from docparse import ParsedAmount, currency_of, parse_amount, parse_date

D = Decimal
CENT = D("0.01")
# Rough value of one unit in USD -- ONLY to sanity-check a looked-up rate
# (flag anything more than 40% away). Never used to convert.
ROUGH_USD = {"USD": D("1"), "EUR": D("1.10"), "GBP": D("1.30"), "INR": D("0.0118"),
             "BDT": D("0.0083")}
SANITY_BAND = D("0.40")


@dataclass
class FxRate:
    currency: str  # what the documents use, e.g. "USD"
    to: str  # the owner's profile currency, e.g. "BDT"
    rate: Decimal | None  # 1 currency = rate `to`; None = still needed
    date: str  # ISO date the rate is for
    date_note: str  # where the date came from
    mode: str  # gemini | owner | missing
    source: str = ""  # e.g. "Bangladesh Bank, via Google Search"
    sources: list = field(default_factory=list)  # grounding links [{title, uri}]
    note: str = ""  # sanity warning or why the lookup failed

    @property
    def suspicious(self) -> bool:
        return bool(self.rate) and not plausible(self.currency, self.to, self.rate)

    def to_json(self) -> dict:
        return {"currency": self.currency, "to": self.to,
                "rate": str(self.rate) if self.rate is not None else None, "date": self.date,
                "date_note": self.date_note, "mode": self.mode, "source": self.source,
                "sources": self.sources[:5], "note": self.note, "suspicious": self.suspicious}


def plausible(cur: str, to: str, rate: Decimal) -> bool:
    if cur not in ROUGH_USD or to not in ROUGH_USD:
        return True
    expected = ROUGH_USD[cur] / ROUGH_USD[to]
    return abs(rate - expected) <= expected * SANITY_BAND


def amount_currency(text: str, span: str, default: str) -> str:
    """The currency an amount is written in: its own marker, else the marker in
    the quoted source text, else the owner's currency."""
    return currency_of(text) or currency_of(span) or default


def foreign_currencies(facts, to: str) -> list[str]:
    """Currencies other than `to` that the documents' amounts are written in."""
    texts = [(f.value, f.span) for f in (facts.order_value, facts.invoice_amount,
                                          facts.advance_received)]
    texts += [(p.amount.value, p.amount.span) for p in facts.supplier_payments]
    out = []
    for value, span in texts:
        if value.strip():
            c = amount_currency(value, span, to)
            if c != to and c not in out:
                out.append(c)
    return out


def document_date(facts, today: dt.date | None = None) -> tuple[dt.date, str]:
    """(date for the rate, where it came from)."""
    today = today or dt.date.today()
    d = parse_date(facts.document_date.value)
    if d:
        return d, f"document date ({facts.document_date.value})"
    return today, "no date in the documents: today's rate used"


_CACHE: dict[tuple, FxRate] = {}
_LOCK = threading.Lock()


def lookup(cur: str, to: str, when: dt.date, date_note: str) -> FxRate:
    """Gemini + Google Search; FxRate(mode="missing") if Gemini is unavailable or
    returns nothing usable. Cached per (cur, to, date)."""
    import gemini_client

    key = (cur, to, when.isoformat())
    with _LOCK:
        if key in _CACHE:
            r = _CACHE[key]
            return FxRate(r.currency, r.to, r.rate, r.date, date_note, r.mode, r.source,
                          list(r.sources), r.note)
    if not gemini_client.gemini_available():
        return FxRate(cur, to, None, when.isoformat(), date_note, "missing",
                      note="Gemini is not configured on this server: enter the rate yourself.")
    try:
        data, sources = gemini_client.exchange_rate(cur, to, when.isoformat())
        rate = D(str(data.get("rate", ""))).quantize(D("0.000001"))
        if rate <= 0:
            raise ValueError("rate must be positive")
    except (Exception, InvalidOperation) as exc:  # never block the case on the lookup
        return FxRate(cur, to, None, when.isoformat(), date_note, "missing",
                      note=f"Gemini could not find the rate ({exc}): enter it yourself.")
    r = FxRate(cur, to, rate, str(data.get("rate_date") or when.isoformat())[:10], date_note,
               "gemini", str(data.get("source", ""))[:120], sources[:5])
    if r.suspicious:
        r.note = (f"Check this rate: 1 {cur} = {rate} {to} is far from the usual range. "
                  f"Correct it if it is wrong.")
    with _LOCK:
        _CACHE[key] = r
    return r


def owner_rate(prev: FxRate, rate: Decimal) -> FxRate:
    if rate <= 0:
        raise ValueError("The exchange rate must be more than 0.")
    r = FxRate(prev.currency, prev.to, rate.quantize(D("0.000001")), prev.date, prev.date_note,
               "owner", "entered by you")
    if r.suspicious:
        r.note = f"1 {r.currency} = {rate} {r.to} is far from the usual range; please double-check."
    return r


@dataclass
class Converter:
    """Turns an amount as written into the profile currency."""

    to: str
    rates: dict[str, FxRate] = field(default_factory=dict)

    def amount(self, text: str, span: str = "") -> tuple[ParsedAmount | None, str | None]:
        """(amount in `to`, missing-rate message). The ParsedAmount's note says
        what the document wrote and the rate used."""
        parsed = parse_amount(text)
        if parsed is None:
            return None, None
        cur = amount_currency(text, span, self.to)
        if cur == self.to:
            return parsed, None
        r = self.rates.get(cur)
        if r is None or r.rate is None:
            return None, f"Exchange rate {cur} to {self.to} (the documents are in {cur})"
        value = (parsed.value * r.rate).quantize(CENT)
        return ParsedAmount(value, parsed.text, f"{cur} {parsed.value:,f} in the document "
                                                f"x {r.rate} ({r.date})"), None

    def original(self, text: str, span: str = "") -> dict | None:
        """What the document wrote, for display next to a converted value."""
        parsed = parse_amount(text)
        cur = amount_currency(text, span, self.to)
        if parsed is None or cur == self.to:
            return None
        r = self.rates.get(cur)
        conv = (parsed.value * r.rate).quantize(CENT) if r and r.rate else None
        return {"text": text, "currency": cur, "amount": float(parsed.value),
                "rate": str(r.rate) if r and r.rate else None, "rate_date": r.date if r else "",
                "converted": float(conv) if conv is not None else None, "to": self.to}
