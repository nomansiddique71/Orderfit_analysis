"""SolvOrder API end to end (offline: deterministic parser, no Gemini)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TestClient = pytest.importorskip("fastapi.testclient").TestClient
import server  # noqa: E402

client = TestClient(server.app)


def _session():
    return client.post("/api/session").json()["session_id"]


def _sample(sid, pack):
    r = client.post("/api/documents/sample", json={"session_id": sid, "pack": pack})
    assert r.status_code == 200, r.text
    return r.json()


def _analyze(sid, **kw):
    r = client.post("/api/analyze", json={"session_id": sid, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_samples():
    assert client.get("/api/health").json()["ok"]
    packs = client.get("/api/samples").json()
    assert {p["id"] for p in packs} == {"clean", "fraud", "injection", "ambiguous"}
    pdf = client.get("/api/samples/clean/purchase_order.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get("/api/samples/clean/..%2Fprofile.json").status_code == 404
    assert client.get("/api/samples/clean/profile.json").status_code == 404  # not whitelisted


def test_clean_flow_approve_execute():
    sid = _session()
    view = _sample(sid, "clean")
    assert view["mode"] == "parser" and not [f for f in view["flags"] if f["severity"] == "critical"]
    a = _analyze(sid)
    assert a["verdict"]["winner"] == "adv50_ext0_nofin"
    assert a["gap"] == {"amount": 12500.0, "from_day": 20, "until_day": 60, "days": 41}
    assert "day 20" in a["verdict"]["headline"]
    r = client.post("/api/approve", json={"session_id": sid, "plan_id": "adv50_ext0_nofin"})
    assert r.status_code == 200 and r.json()["approval"]["id"].startswith("APP-")
    ex = client.post("/api/execute", json={"session_id": sid}).json()
    assert ex["ok"] and ex["consistency"] == "passed"


def test_infeasible_plan_needs_override_with_reason():
    sid = _session()
    _sample(sid, "clean")
    _analyze(sid)
    r = client.post("/api/approve", json={"session_id": sid, "plan_id": "accept-as-is"})
    assert r.status_code == 409
    r = client.post("/api/approve", json={"session_id": sid, "plan_id": "accept-as-is",
                                          "override": True, "reason": "owner adds funds"})
    assert r.status_code == 200 and r.json()["approval"]["override"]
    ex = client.post("/api/execute", json={"session_id": sid}).json()
    assert ex["override"] and ex["steps"][0].startswith("[RESERVE OVERRIDE]")


def test_fraud_blocks_execution_until_resolved():
    sid = _session()
    view = _sample(sid, "fraud")
    assert any(f["code"] == "BANK_CHANGE" for f in view["flags"])
    a = _analyze(sid)
    assert a["verdict"]["execution_blocks"] == ["Supplier bank details changed"]
    client.post("/api/approve", json={"session_id": sid, "plan_id": a["verdict"]["winner"]})
    ex = client.post("/api/execute", json={"session_id": sid}).json()
    assert not ex["ok"] and "fraud" in ex["steps"][0].lower()
    assert client.post("/api/flags/resolve", json={"session_id": sid, "code": "BANK_CHANGE",
                                                   "note": "x"}).status_code == 422  # too short
    client.post("/api/flags/resolve", json={"session_id": sid, "code": "BANK_CHANGE",
                                            "note": "Called Brightwave on the number we had"})
    a = _analyze(sid)
    assert a["verdict"]["execution_blocks"] == []
    client.post("/api/approve", json={"session_id": sid, "plan_id": a["verdict"]["winner"]})
    assert client.post("/api/execute", json={"session_id": sid}).json()["ok"]


def test_ambiguous_pack_readings_and_currency():
    sid = _session()
    _sample(sid, "ambiguous")
    a = _analyze(sid)
    assert a["case"]["currency"] == "INR"
    assert a["case"]["payment_readings"] == {"after_order": 45, "after_delivery": 80}
    assert a["case"]["pay_day"] == 80
    b = _analyze(sid, payment_reading="after_order")
    assert b["case"]["pay_day"] == 45


def test_upload_pdf_and_pasted_text():
    sid = _session()
    files = [("files", ("po.pdf", (ROOT / "samples/clean/purchase_order.pdf").read_bytes(),
                        "application/pdf"))]
    pasted = ("QUOTATION Q-1\nSupplier: Brightwave Supplies\n"
              "Payment schedule:\n1. Deposit: USD 12,000 due day 0")
    r = client.post("/api/documents/upload", data={"session_id": sid, "pasted": pasted},
                    files=files)
    assert r.status_code == 200, r.text
    view = r.json()
    assert [d["kind"] for d in view["documents"]] == ["purchase_order", "supplier_quote"]
    assert view["profile_source"] == "default"
    blocked = _analyze(sid)  # documents describe the order, not the business
    assert not blocked["ok"] and blocked["needs_business"]
    assert client.post("/api/profile", json={"session_id": sid, "use_example": True}).status_code == 200
    assert _analyze(sid)["ok"]


def test_manual_entry_runs_engine_without_ai():
    sid = _session()
    r = client.post("/api/documents/manual", json={
        "session_id": sid,
        "facts": {"order_value": "30000", "delivery_day": "day 30", "payment_terms_days": "30",
                  "payment_terms_basis": "after_delivery", "customer_name": "Meridian"},
        "supplier_payments": [{"label": "Deposit", "amount": "12000", "day": 0},
                              {"label": "Pre-delivery", "amount": "5000", "day": 20},
                              {"label": "Shipping", "amount": "1500", "day": 30}]})
    assert r.status_code == 200
    client.post("/api/profile", json={"session_id": sid, "use_example": True})
    a = _analyze(sid)
    assert a["ok"] and a["verdict"]["winner"] == "adv50_ext0_nofin"


def test_missing_facts_reported():
    sid = _session()
    client.post("/api/documents/manual", json={"session_id": sid, "facts": {"order_value": "100"}})
    a = client.post("/api/analyze", json={"session_id": sid}).json()
    assert a["ok"] is False and "Delivery day" in a["missing"]


def test_scenarios_t3_and_log():
    sid = _session()
    _sample(sid, "clean")
    _analyze(sid)
    sc = client.post("/api/scenarios", json={"session_id": sid, "plan_id": "adv50_ext0_nofin"}).json()
    assert sc["max_loss"] == 3500.0
    assert client.post("/api/t3", json={"session_id": sid, "action": "live_transfer"}).json()["blocked"]
    entries = client.get(f"/api/log?session_id={sid}").json()["entries"]
    assert any(e["tier"] == "T3" and e["result"] == "BLOCKED" for e in entries)
    assert client.get(f"/api/log/export?session_id={sid}").status_code == 200


def test_unknown_session_and_bad_input():
    assert client.post("/api/analyze", json={"session_id": "nope"}).status_code == 404
    sid = _session()
    _sample(sid, "clean")
    assert client.post("/api/analyze", json={"session_id": sid, "priority": "x"}).status_code == 400
    assert client.post("/api/analyze", json={"session_id": sid, "stress_delay": 7}).status_code == 400


@pytest.mark.parametrize("pack", ["clean", "fraud", "injection", "ambiguous"])
def test_cash_walk_matches_engine_lowest_point(pack):
    """The owner-facing explanation uses the engine's own numbers: its lowest
    point and day equal the plan's simulated minimum on every sample."""
    sid = _session()
    _sample(sid, pack)
    r = _analyze(sid)
    plans = {p["id"]: p for p in r["plans"]}
    for key, pid in (("asis", "accept-as-is"), ("recommended", r["verdict"]["winner"])):
        w = r["walk"][key]
        assert (w["low"], w["low_day"]) == (plans[pid]["min_balance"], plans[pid]["min_day"]), (key, pid)
        assert w["headroom"] == w["low"] - r["case"]["reserve"]
        assert sum(w["out_until_low"].values()) - sum(w["in_until_low"].values()) == w["opening"] - w["low"]
