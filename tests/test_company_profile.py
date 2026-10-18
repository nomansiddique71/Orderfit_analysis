"""Company profile on the account: role and currency, and how a case uses them."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_api import _session, client  # noqa: E402
from test_needs import ACME, _manual  # noqa: E402


def _login():
    r = client.post("/api/auth/demo").json()
    return {"Authorization": f"Bearer {r['token']}"}, r["user"]


def _profile(h, **kw):
    body = {"name": "Rey", "business": "Padma Traders", **kw}
    return client.post("/api/auth/profile", json=body, headers=h)


def test_profile_saves_role_currency_and_company_email():
    h, u = _login()
    assert u["role"] == "seller" and u["currency"] == "USD"
    r = _profile(h, company_email="Accounts@PadmaTraders.example", role="buyer", currency="bdt")
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    assert (user["role"], user["currency"], user["company_email"]) == (
        "buyer", "BDT", "accounts@padmatraders.example")
    assert client.get("/api/auth/me", headers=h).json()["user"]["currency"] == "BDT"


def test_profile_rejects_unknown_currency_role_and_bad_email():
    h, _ = _login()
    assert _profile(h, currency="JPY").status_code == 400
    assert _profile(h, role="broker").status_code == 400
    assert _profile(h, company_email="not-an-email").status_code == 400


def test_owner_case_uses_profile_currency_everywhere():
    h, _ = _login()
    _profile(h, currency="BDT")
    sid = _session()
    r = client.post("/api/documents/manual", headers=h, json={
        "session_id": sid, "facts": {"order_value": "300000", "delivery_day": "30",
                                     "payment_terms_days": "30", "payment_terms_basis": "after_delivery"},
        "supplier_payments": [{"label": "Deposit", "amount": "120000", "day": 0}]})
    assert r.status_code == 200
    keys = {n["key"] for n in client.post("/api/needs", json={"session_id": sid},
                                          headers=h).json()["needs"]}
    assert "currency" not in keys and "business_name" not in keys  # the profile answers both
    p = client.post("/api/profile", headers=h, json={
        **ACME, "session_id": sid, "currency": "USD", "opening_cash": 500000, "reserve": 100000})
    assert p.json()["profile"]["currency"] == "BDT"  # the profile wins over the form
    a = client.post("/api/analyze", json={"session_id": sid}).json()
    assert a["ok"] and a["case"]["currency"] == "BDT"


def test_samples_keep_their_document_currency():
    h, _ = _login()
    _profile(h, currency="EUR")
    sid = _session()
    view = client.post("/api/documents/sample", headers=h,
                       json={"session_id": sid, "pack": "ambiguous"}).json()
    assert view["profile"]["currency"] == "INR"


def test_anonymous_api_still_asks_for_currency():
    sid = _session()
    _manual(sid, {"order_value": "30000"})
    keys = {n["key"] for n in client.post("/api/needs", json={"session_id": sid}).json()["needs"]}
    assert "currency" in keys
