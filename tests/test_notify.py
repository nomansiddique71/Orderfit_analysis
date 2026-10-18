"""Notify after approval: one button for the deal's counterparty (customer when
the owner sells, supplier when the owner buys), the email in the demo outbox,
the plan booked in the sandbox, and the record under Approved plans."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_api import _analyze, _session, client  # noqa: E402
from test_company_profile import _login  # noqa: E402


def _case(h, pack):
    sid = _session()
    client.post("/api/documents/sample", headers=h, json={"session_id": sid, "pack": pack})
    a = _analyze(sid)
    client.post("/api/approve", headers=h, json={"session_id": sid, "plan_id": a["verdict"]["winner"]})
    return sid, a


def test_seller_notifies_customer_and_the_plan_is_filed_with_its_email():
    h, _ = _login()
    sid, a = _case(h, "seller_bdt")
    n = client.post("/api/notify", headers=h, json={"session_id": sid}).json()
    rec = n["record"]
    assert rec["role"] == "seller" and rec["party"] == "customer"
    assert rec["counterparty"] == "Rupsha Fashion House"
    assert rec["mails"][0]["to"] == "purchase@rupshafashion.example"
    assert rec["mails"][0]["sent"] and "nothing really delivered" in rec["mails"][0]["status"]
    assert rec["currency"] == "BDT" and rec["plan_id"] == a["verdict"]["winner"]
    assert rec["sandbox"]["ok"] and rec["sandbox"]["consistency"] == "passed"
    assert rec["reasons_for"] and rec["summary"].startswith("Recommended")
    plans = client.get("/api/approved", headers=h).json()["plans"]
    assert [p["id"] for p in plans] == [rec["id"]]


def test_buyer_notifies_supplier_first():
    h, _ = _login()
    sid, _ = _case(h, "buyer_bdt")
    rec = client.post("/api/notify", headers=h, json={"session_id": sid}).json()["record"]
    assert rec["role"] == "buyer" and rec["party"] == "supplier"
    assert rec["counterparty"] == "Meghna Fabrics Ltd"
    assert rec["mails"][0]["to"] == "sales@meghnafabrics.example"
    assert "We accept your offer" in rec["mails"][0]["body"]
    assert [m["party"] for m in rec["mails"]] == ["supplier", "lender"]  # the loan plan


def test_approved_plans_belong_to_the_account_and_survive_a_new_case():
    h, _ = _login()
    for pack in ("seller_bdt", "buyer_bdt"):
        sid, _ = _case(h, pack)
        client.post("/api/notify", headers=h, json={"session_id": sid})
    plans = client.get("/api/approved", headers=h).json()["plans"]
    assert [p["role"] for p in plans] == ["buyer", "seller"]  # newest first
    other, _ = _login()
    assert client.get("/api/approved", headers=other).json()["plans"] == []


def test_notify_needs_an_approval():
    sid = _session()
    client.post("/api/documents/sample", json={"session_id": sid, "pack": "clean"})
    _analyze(sid)
    assert client.post("/api/notify", json={"session_id": sid}).status_code == 409
