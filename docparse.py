"""Deterministic parsing of money amounts and day references found in documents.

Gemini returns the *text* it read (e.g. "USD 5,00,000", "5L", "0.5 crore",
"day 30"); this module turns that text into exact Decimal / int values. The
model never does the conversion, so a misread can be caught by comparing the
parsed value with the quoted source span.

Supported money formats (D-10):
  30,000   30000   30,000.50   USD 30,000   $30k
  5,00,000 (South Asian grouping)   5L / 5 lakh / 5 lakhs   0.5 crore / 1.2 Cr
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

D = Decimal

_MULTIPLIERS = {
    "k": D("1000"), "thousand": D("1000"),
    "l": D("100000"), "lac": D("100000"), "lacs": D("100000"),
    "lakh": D("100000"), "lakhs": D("100000"),
    "cr": D("10000000"), "crore": D("10000000"), "crores": D("10000000"),
    "m": D("1000000"), "mn": D("1000000"), "million": D("1000000"),
}

# a number (with optional grouping commas and decimals) and an optional unit word
_AMOUNT_RE = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<unit>crores?|cr|lakhs?|lacs?|lac|l|k|thousand|million|mn|m)?\b",
    re.IGNORECASE,
)
_SOUTH_ASIAN_RE = re.compile(r"^\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d+)?$")  # 5,00,000 / 12,50,000


@dataclass(frozen=True)
class ParsedAmount:
    value: Decimal
    text: str  # the exact text that was parsed
    note: str = ""  # set when the format needed interpretation (D-10)


def parse_amounts(text: str) -> list[ParsedAmount]:
    """Every money-like amount in a piece of text, in order of appearance."""
    out: list[ParsedAmount] = []
    for m in _AMOUNT_RE.finditer(text or ""):
        raw, unit = m.group("num"), (m.group("unit") or "").lower()
        try:
            value = D(raw.replace(",", ""))
        except InvalidOperation:
            continue
        note = ""
        if unit:
            value *= _MULTIPLIERS[unit]
            note = f"'{m.group(0).strip()}' read as {value:,.0f} ({unit} = {_MULTIPLIERS[unit]:,.0f})"
        elif _SOUTH_ASIAN_RE.match(raw):
            note = f"'{raw}' uses South Asian digit grouping; read as {value:,.0f}"
        out.append(ParsedAmount(value, m.group(0).strip(), note))
    return out


def parse_amount(text: str) -> ParsedAmount | None:
    """The largest amount in the text (labels such as 'Net 30' or 'day 0' are
    smaller than the money figure in every realistic field value)."""
    amounts = [a for a in parse_amounts(text) if not _looks_like_day(text, a)]
    return max(amounts, key=lambda a: a.value) if amounts else None


def _looks_like_day(text: str, a: ParsedAmount) -> bool:
    i = text.find(a.text)
    before = text[max(0, i - 6):i].lower()
    return "day" in before or "net" in before


_DAY_RE = re.compile(r"\bday\s*(\d{1,3})\b|\b(\d{1,3})\s*days?\b", re.IGNORECASE)


def parse_day(text: str) -> int | None:
    """'day 30' -> 30, 'within 30 days' -> 30, '30' -> 30. None if absent."""
    if text is None:
        return None
    m = _DAY_RE.search(text)
    if m:
        return int(m.group(1) or m.group(2))
    t = text.strip()
    return int(t) if t.isdigit() else None


def parse_percent(text: str) -> Decimal | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text or "")
    return D(m.group(1)) if m else None


def same_amount(a: str, b: str) -> bool:
    """True if two texts contain the same money figure after normalisation."""
    pa, pb = parse_amount(a), parse_amount(b)
    return pa is not None and pb is not None and pa.value == pb.value


def normalise_account(text: str) -> str:
    """Bank account / IBAN reduced to letters+digits, upper-case, for comparison."""
    return re.sub(r"[^0-9A-Za-z]", "", text or "").upper()


def mask_account(text: str) -> str:
    n = normalise_account(text)
    return ("****" + n[-4:]) if len(n) > 4 else n
