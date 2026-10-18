"""Seller or buyer: the owner's role from the profile, checked against the
documents, and how a buyer deal is analysed (option 1 samples, options 2 and 3)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docmodel import Fact, Facts  # noqa: E402
from role import detect_role, same_company  # noqa: E402
from test_api import _analyze, _sample, _session, client  # noqa: E402
from test_company_profile import _login, _profile  # noqa: E402

BUYER_FACTS = {"customer_name": "Padma Garments Ltd", "supplier_name": "Meghna Fabrics Ltd",
               "order_ref": "Q-77", "order_value": "800000", "delivery_day": "25",
               "expected_income": "1200000", "income_days": "5"}
BUYER_PAYS = [{"label": "Advance", "amount": "400000", "day": 0},
              {"label": "Balance on delivery", "amount": "350000", "day": 25}]
PADMA = {"name": "Padma Garments Ltd", "opening_cash": 1000000, "reserve": 300000,
         "max_financing_cost": 40000,
         "recurring": [{"label": "Payroll", "amount": 350000, "days": "15, 45"}]}


# ------------------------------------------------------------ option 1: samples

def test_seller_sample_is_detected_as_seller_and_keeps_advance_plans():
    sid = _session()
    v = _sample(sid, "seller_bdt")
    assert (v["role"], v["role_guess"]["role"], v["currency"]) == ("seller", "seller", "BDT")
    a = _analyze(sid)
    assert a["case"]["role"] == "seller" and a["verdict"]["winner"] == "adv50_ext0_nofin"
    assert any(p["advance_pct"] > 0 for p in a["plans"])


def test_buyer_sample_is_detected_as_buyer_with_no_customer_advance():
    sid = _session()
    v = _sample(sid, "buyer_bdt")
    assert (v["role"], v["role_guess"]["role"]) == ("buyer", "buyer")
    keys = {f["key"] for f in v["facts"]}
    assert {"expected_income", "income_days"} <= keys and "payment_terms_days" not in keys
    assert not any(f["code"] == "NET_TERMS" for f in v["flags"])  # customer terms don't apply
    assert v["questions"] == 0
    a = _analyze(sid)
    assert a["ok"] and a["case"]["role"] == "buyer" and a["case"]["deal"] == "offer"
    assert all(p["advance_pct"] == 0 for p in a["plans"])
    assert a["case"]["order_value"] == 1200000  # the income from the goods, not the price
    assert a["case"]["gross_margin"] == 1200000 - 800000
    assert a["verdict"]["winner"] == "minloan_JCB-1" and not a["verdict"]["provisional"]
    assert any(m["label"] == "Income from the goods" and m["day"] == 55
               for m in a["walk"]["recommended"]["rows"])


# ------------------------------------------------------------ detection rules

def _facts(**kw):
    f = Facts()
    for k, v in kw.items():
        setattr(f, k, Fact(v, "DOC-1", v, 1.0, True))
    return f


def test_company_names_match_without_suffixes():
    assert same_company("Acme Trading Co.", "ACME TRADING")
    assert same_company("Padma Garments Ltd", "Padma Garments Limited")
    assert not same_company("Acme Trading", "Meridian Retail Group")


def test_detect_role_from_buyer_name_email_or_purchase_order():
    assert detect_role(_facts(customer_name="Padma Garments"), [], "Padma Garments Ltd").role == "buyer"
    assert detect_role(_facts(customer_email="ap@padma.example"), [], "Padma",
                       "accounts@padma.example").role == "buyer"
    assert detect_role(_facts(supplier_name="Padma Garments"), [], "Padma Garments Ltd").role == "seller"
    assert detect_role(_facts(), [], "").role is None


# --------------------------------------------- options 2 and 3: owner's own case

def _manual(h, facts, pays, role=None):
    sid = _session()
    r = client.post("/api/documents/manual", headers=h, json={
        "session_id": sid, "facts": facts, "supplier_payments": pays, "role": role})
    assert r.status_code == 200, r.text
    return sid, r.json()


def test_profile_role_applies_and_a_conflict_is_asked_not_switched():
    h, _ = _login()
    _profile(h, business="Padma Garments Ltd", role="seller", currency="BDT")
    sid, v = _manual(h, BUYER_FACTS, BUYER_PAYS)  # documents name Padma as the buyer
    assert v["role"] == "seller" and v["role_guess"]["role"] == "buyer"
    needs = {n["key"]: n for n in client.post("/api/needs", json={"session_id": sid},
                                              headers=h).json()["needs"]}
    assert needs["deal_role"]["required"] and needs["deal_role"]["suggested"] == "buyer"
    assert "name you as the buyer" in needs["deal_role"]["why"]
    v = client.post("/api/role", json={"session_id": sid, "role": "buyer"}, headers=h).json()
    assert (v["role"], v["role_source"]) == ("buyer", "owner")
    keys = {n["key"] for n in client.post("/api/needs", json={"session_id": sid},
                                          headers=h).json()["needs"]}
    assert "deal_role" not in keys and "payment_terms_days" not in keys


def test_buyer_without_income_is_asked_for_it():
    h, _ = _login()
    _profile(h, business="Padma Garments Ltd", role="buyer", currency="BDT")
    facts = {k: v for k, v in BUYER_FACTS.items() if k not in ("expected_income", "income_days")}
    sid, v = _manual(h, facts, BUYER_PAYS, role="buyer")
    assert v["role"] == "buyer" and v["questions"] > 0
    keys = {n["key"] for n in client.post("/api/needs", json={"session_id": sid},
                                          headers=h).json()["needs"]}
    assert {"expected_income", "income_days"} <= keys
    assert not keys & {"order_value", "payment_terms_days", "advance_received", "currency"}
    client.post("/api/profile", headers=h, json={**PADMA, "session_id": sid})
    a = client.post("/api/analyze", json={"session_id": sid}).json()
    assert not a["ok"] and any("Income you expect" in m for m in a["missing"])
    a = client.post("/api/analyze", json={"session_id": sid,
                                          "edits": {"expected_income": "0"}}).json()
    assert a["ok"] and a["case"]["order_value"] == 0  # no income: income day not needed


def test_buyer_messages_go_to_the_supplier():
    h, _ = _login()
    _profile(h, business="Padma Garments Ltd", role="buyer", currency="BDT")
    sid, _ = _manual(h, BUYER_FACTS, BUYER_PAYS, role="buyer")
    client.post("/api/profile", headers=h, json={**PADMA, "session_id": sid})
    a = client.post("/api/analyze", json={"session_id": sid}).json()
    assert a["ok"]
    for pid in ("accept-as-is", "adv0_ext1_nofin"):
        msgs = client.post("/api/draft", json={"session_id": sid, "plan_id": pid}).json()["messages"]
        assert [m["to_name"] for m in msgs] == ["Meghna Fabrics Ltd"]
    asis = client.post("/api/draft", json={"session_id": sid, "plan_id": "accept-as-is"}).json()
    assert "We accept your offer Q-77 (BDT 7,50,000)" in asis["messages"][0]["body"]
