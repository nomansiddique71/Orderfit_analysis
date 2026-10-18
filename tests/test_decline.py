"""No way of accepting keeps the reserve: decline is the one recommendation, with
every option's failure, a polite justified mail to the counterparty, and a record
under Approved / declined plans."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_api import _analyze, _sample, _session, client  # noqa: E402
from test_company_profile import _login  # noqa: E402
from test_needs import ACME, _manual  # noqa: E402


def _no_plan_case(reserve=12000):
    sid = _session()
    _manual(sid)
    client.post("/api/profile", json={**ACME, "session_id": sid, "reserve": reserve})
    a = client.post("/api/analyze", json={"session_id": sid}).json()
    assert a["ok"] and a["verdict"]["no_plan_survives"] and a["verdict"]["winner"] == "decline"
    return sid, a


def test_decline_lists_why_every_option_fails_and_what_would_work():
    _, a = _no_plan_case()
    options = [t["option"] for t in a["decline"]["tried"]]
    assert options[0] == "Accept as it is" and "Ask the customer for an advance" in options
    assert all("below your USD 12,000 reserve" in t["why"] for t in a["decline"]["tried"])
    assert a["decline"]["ask"].startswith("an advance of 55% (USD 16,500)")  # engine-verified


def test_decline_breakdown_and_polite_mail_to_the_customer():
    sid, _ = _no_plan_case()
    b = client.post("/api/breakdown", json={"session_id": sid, "plan_id": "decline"}).json()
    assert b["verdict"] == "decline" and b["summary"].startswith("Recommended: decline")
    assert any("SolvOrder tried every option" in t for t in b["reasons_for"])
    m = client.post("/api/draft", json={"session_id": sid, "plan_id": "decline"}).json()["messages"]
    assert [x["party"] for x in m] == ["customer"]
    body = m[0]["body"]
    assert body.startswith("Subject: Your order -- unable to proceed on the current terms")
    assert "Dear Meridian" in body and "Thank you for your purchase order. We have" in body
    assert "asking you for an advance" in body and "advance of 55%" in body
    assert "Kind regards" in body


def test_decline_is_sent_and_filed_without_booking_payments():
    h, _ = _login()
    sid, _ = _no_plan_case()
    r = client.post("/api/decline", headers=h, json={"session_id": sid}).json()
    rec = r["record"]
    assert rec["status"] == "declined" and rec["id"].startswith("DEC-") and rec["sandbox"] is None
    assert rec["mails"][0]["sent"] and rec["party"] == "customer"
    assert client.get(f"/api/sandbox?session_id={sid}").json()["bank"]["rows"] == []
    assert [p["status"] for p in client.get("/api/approved", headers=h).json()["plans"]] == ["declined"]
    assert client.post("/api/decline", json={"session_id": sid}).status_code == 409  # sent once


def test_buyer_declines_to_the_supplier():
    sid = _session()
    _sample(sid, "buyer_bdt")
    a = _analyze(sid, reserve=900000)
    assert a["verdict"]["winner"] == "decline"
    assert all(t["option"] != "Ask the customer for an advance" for t in a["decline"]["tried"])
    m = client.post("/api/draft", json={"session_id": sid, "plan_id": "decline"}).json()["messages"]
    assert m[0]["party"] == "supplier" and m[0]["to"] == "sales@meghnafabrics.example"
    assert "Thank you for your offer PG-0417" in m[0]["body"] and "BDT 4,00,000 on day 0" in m[0]["body"]


def test_no_decline_when_a_safe_plan_exists():
    sid = _session()
    _sample(sid, "clean")
    a = _analyze(sid)
    assert a["decline"] is None
    assert client.post("/api/decline", json={"session_id": sid}).status_code == 409
