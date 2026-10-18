"""Every amount in the profile currency: Gemini (Google Search) finds the rate for
the document date, the engine converts exactly, the original stays visible."""

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fx  # noqa: E402
import gemini_client  # noqa: E402
from docmodel import Fact, Facts  # noqa: E402
from test_api import _session, client  # noqa: E402
from test_company_profile import _login, _profile  # noqa: E402

USD_ORDER = {"order_value": "USD 30,000", "delivery_day": "30", "payment_terms_days": "30",
             "payment_terms_basis": "after_delivery", "customer_name": "Meridian",
             "document_date": "12 March 2026"}
USD_PAYS = [{"label": "Deposit", "amount": "USD 12,000", "day": 0},
            {"label": "Shipping", "amount": "USD 1,500", "day": 30}]
BUSINESS = {"name": "Padma", "opening_cash": 5000000, "reserve": 1000000,
            "recurring": [{"label": "Payroll", "amount": 350000, "days": "15, 45"}]}


@pytest.fixture(autouse=True)
def _clear_cache():
    fx._CACHE.clear()
    yield
    fx._CACHE.clear()


@pytest.fixture
def gemini_rate(monkeypatch):
    calls = []

    def fake(cur, to, date):
        calls.append((cur, to, date))
        return {"rate": 121.4, "rate_date": date, "source": "Bangladesh Bank"}, [
            {"title": "bb.org.bd", "uri": "https://www.bb.org.bd/"}]
    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "exchange_rate", fake)
    return calls


def _case(h, facts=USD_ORDER, pays=USD_PAYS):
    sid = _session()
    r = client.post("/api/documents/manual", headers=h, json={
        "session_id": sid, "facts": facts, "supplier_payments": pays, "role": "seller"})
    assert r.status_code == 200, r.text
    return sid, r.json()


def test_gemini_rate_for_the_document_date_converts_every_amount(gemini_rate):
    h, _ = _login()
    _profile(h, currency="BDT")
    sid, v = _case(h)
    assert gemini_rate == [("USD", "BDT", "2026-03-12")]
    rate = v["fx"]["rates"][0]
    assert (rate["rate"], rate["mode"], rate["source"]) == ("121.400000", "gemini", "Bangladesh Bank")
    assert rate["date_note"].startswith("document date")
    ov = next(f for f in v["facts"] if f["key"] == "order_value")
    assert ov["original"] == {"text": "USD 30,000", "currency": "USD", "amount": 30000.0,
                              "rate": "121.400000", "rate_date": "2026-03-12",
                              "converted": 3642000.0, "to": "BDT"}
    client.post("/api/profile", headers=h, json={**BUSINESS, "session_id": sid})
    a = client.post("/api/analyze", json={"session_id": sid}).json()
    assert a["ok"] and a["case"]["currency"] == "BDT"
    assert a["case"]["order_value"] == 3642000.0  # 30,000 x 121.4, exact
    dep = next(m for m in a["case"]["movements"] if m["label"] == "Deposit")
    assert dep["amount"] == -1456800.0 and "USD 12,000" in dep["note"]


def test_no_document_date_uses_todays_rate_labelled(gemini_rate):
    h, _ = _login()
    _profile(h, currency="BDT")
    _, v = _case(h, {k: x for k, x in USD_ORDER.items() if k != "document_date"})
    assert gemini_rate[0][2] == dt.date.today().isoformat()
    assert "today's rate" in v["fx"]["rates"][0]["date_note"]


def test_without_gemini_the_owner_is_asked_for_the_rate_and_can_correct_it():
    h, _ = _login()
    _profile(h, currency="BDT")
    sid, v = _case(h)
    assert v["fx"]["rates"][0]["mode"] == "missing" and v["questions"] > 0
    needs = {n["key"]: n for n in client.post("/api/needs", json={"session_id": sid},
                                              headers=h).json()["needs"]}
    assert needs["fx_rates"]["required"] and needs["fx_rates"]["rates"][0]["currency"] == "USD"
    client.post("/api/profile", headers=h, json={**BUSINESS, "session_id": sid})
    a = client.post("/api/analyze", json={"session_id": sid}).json()
    assert not a["ok"] and any("Exchange rate USD to BDT" in m for m in a["missing"])
    assert client.post("/api/fx", json={"session_id": sid, "rates": {"USD": "abc"}}).status_code == 400
    v = client.post("/api/fx", json={"session_id": sid, "rates": {"USD": "120"}}).json()
    assert v["fx"]["rates"][0]["mode"] == "owner" and not v["fx"]["rates"][0]["suspicious"]
    a = client.post("/api/analyze", json={"session_id": sid}).json()
    assert a["ok"] and a["case"]["order_value"] == 3600000.0


def test_an_implausible_rate_is_flagged_for_the_owner(monkeypatch):
    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "exchange_rate",
                        lambda c, t, d: ({"rate": 0.0082, "source": "x"}, []))  # inverted
    r = fx.lookup("USD", "BDT", dt.date(2026, 3, 12), "document date")
    assert r.suspicious and "Check this rate" in r.note


def test_same_currency_and_samples_are_not_converted(gemini_rate):
    h, _ = _login()
    _profile(h, currency="USD")
    _, v = _case(h)
    assert v["fx"]["rates"] == [] and gemini_rate == []
    _profile(h, currency="BDT")
    sid = _session()
    v = client.post("/api/documents/sample", headers=h,
                    json={"session_id": sid, "pack": "clean"}).json()
    assert not v["fx"]["active"] and v["profile"]["currency"] == "USD"


def test_converter_reads_the_currency_from_the_quoted_span():
    conv = fx.Converter("BDT", {"USD": fx.FxRate("USD", "BDT", Decimal("120"), "2026-03-12",
                                                 "document date", "owner")})
    a, missing = conv.amount("30,000", "Total order value: USD 30,000")
    assert a.value == Decimal("3600000.00") and missing is None
    a, missing = conv.amount("INR 5,00,000")
    assert a is None and "INR to BDT" in missing
    f = Facts()
    f.order_value = Fact("USD 30,000")
    f.supplier_payments = []
    assert fx.foreign_currencies(f, "BDT") == ["USD"]
