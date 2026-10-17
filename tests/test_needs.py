"""Intake questions (what else SolvOrder needs) and the owner's business details."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gemini_client  # noqa: E402
import needs  # noqa: E402
from test_api import _analyze, _sample, _session, client  # noqa: E402

MANUAL = {"order_value": "30000", "delivery_day": "day 30", "payment_terms_days": "30",
          "payment_terms_basis": "after_delivery", "customer_name": "Meridian"}
PAYS = [{"label": "Deposit", "amount": "12000", "day": 0},
        {"label": "Pre-delivery", "amount": "5000", "day": 20},
        {"label": "Shipping", "amount": "1500", "day": 30}]
# The clean sample's business, typed by the owner through the form.
ACME = {"name": "Acme Trading Co.", "currency": "USD", "opening_cash": 30000, "reserve": 8000,
        "max_financing_cost": 2000,
        "recurring": [{"label": "Payroll", "amount": 7000, "days": "15, 45"},
                      {"label": "Supplier bill (existing stock)", "amount": 3000, "days": "10, 40"}],
        "receivables": [{"label": "Northlake Stores", "amount": 4000, "day": 25}]}


def _manual(sid, facts=MANUAL):
    r = client.post("/api/documents/manual", json={"session_id": sid, "facts": facts,
                                                   "supplier_payments": PAYS})
    assert r.status_code == 200, r.text
    return r.json()


def test_rule_needs_ask_for_business_and_missing_order_facts():
    sid = _session()
    _manual(sid, {"order_value": "30000"})
    r = client.post("/api/needs", json={"session_id": sid}).json()
    keys = {n["key"]: n for n in r["needs"]}
    assert r["mode"] == "rules"
    assert {"opening_cash", "reserve", "recurring", "delivery_day", "payment_terms_days"} <= set(keys)
    assert keys["opening_cash"]["required"] and not keys["loan_offers"]["required"]
    assert "order_value" not in keys  # already given


def test_samples_ask_no_business_questions():
    sid = _session()
    _sample(sid, "clean")
    keys = {n["key"] for n in client.post("/api/needs", json={"session_id": sid}).json()["needs"]}
    assert not keys & set(needs.BUSINESS_KEYS)


def test_owner_business_details_give_the_same_answer_as_the_sample():
    sid = _session()
    _manual(sid)
    view = client.post("/api/profile", json={"session_id": sid, **ACME}).json()
    assert view["profile_source"] == "owner"
    a = _analyze(sid)
    assert a["ok"] and a["verdict"]["winner"] == "adv50_ext0_nofin"
    assert a["walk"]["asis"]["low"] == -4500 and a["walk"]["asis"]["low_day"] == 45
    # business details survive loading a new order in the same session
    _manual(sid)
    assert _analyze(sid)["ok"]


def test_profile_validation():
    sid = _session()
    _manual(sid)
    bad_days = {**ACME, "recurring": [{"label": "Rent", "amount": 100, "days": "fifteen"}]}
    assert client.post("/api/profile", json={"session_id": sid, **bad_days}).status_code == 400
    assert client.post("/api/profile", json={"session_id": sid, "name": "x"}).status_code == 400
    assert client.post("/api/profile", json={"session_id": sid, **ACME, "reserve": -1}).status_code == 422


def test_gemini_needs_are_filtered_to_known_keys(monkeypatch):
    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "what_else_needed", lambda known, docs, keys: [
        {"key": "recurring", "question": "What payroll is due before day 60?", "why": "Customer pays day 60."},
        {"key": "credit_score", "question": "Invented field", "why": "x"},
        {"key": "recurring", "question": "duplicate", "why": "x"}])
    sid = _session()
    _manual(sid)
    r = client.post("/api/needs", json={"session_id": sid}).json()
    keys = [n["key"] for n in r["needs"]]
    assert r["mode"] == "gemini" and keys[0] == "recurring" and "credit_score" not in keys
    assert keys.count("recurring") == 1 and r["needs"][0]["required"]
    assert {"opening_cash", "reserve"} <= set(keys)  # rule needs Gemini skipped are kept


def test_gemini_needs_failure_falls_back_to_rules(monkeypatch):
    def boom(*a):
        raise RuntimeError("503")

    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "what_else_needed", boom)
    sid = _session()
    _manual(sid)
    r = client.post("/api/needs", json={"session_id": sid}).json()
    assert r["mode"] == "rules" and "Gemini could not" in r["note"] and r["needs"]
