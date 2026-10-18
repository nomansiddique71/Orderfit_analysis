"""The owner chooses: any safe plan (not only the recommended one), what to do
about each fraud/integrity check, and approval sends that plan's message."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_api import _analyze, _sample, _session, client  # noqa: E402


def _approve(sid, plan_id, **kw):
    r = client.post("/api/approve", json={"session_id": sid, "plan_id": plan_id, **kw})
    assert r.status_code == 200, r.text
    return r.json()["approval"]


def test_owner_can_approve_a_non_recommended_safe_plan_and_its_message_is_sent():
    sid = _session()
    _sample(sid, "clean")
    a = _analyze(sid)
    other = next(p for p in a["plans"] if p["feasible"] and p["financing"] and not p["recommended"]
                 and p["advance_pct"] == 0 and not p["supplier_extension"])
    d = client.post("/api/draft", json={"session_id": sid, "plan_id": other["id"]}).json()["messages"]
    # the customer always hears that the order is accepted; the lender gets the loan acceptance
    assert [m["party"] for m in d] == ["customer", "lender"]
    assert d[0]["to"] == "ap@meridianretail.example"  # the address from the purchase order
    assert "Financing acceptance" in d[1]["body"] and d[1]["to"].endswith(".example")
    appr = _approve(sid, other["id"])
    msg = appr["messages"][1]
    assert msg["sent"] and msg["body"] == d[1]["body"] and msg["to"] == d[1]["to"]
    log = client.get(f"/api/log?session_id={sid}").json()["entries"]
    assert any(e["tool"] == "outbox.send" and e["approval_id"] == appr["id"] for e in log)
    ex = client.post("/api/execute", json={"session_id": sid}).json()
    assert ex["ok"] and "already sent" in ex["steps"][0]
    assert sum(e["tool"] == "outbox.send" for e in
               client.get(f"/api/log?session_id={sid}").json()["entries"]) == 2  # not sent twice


def test_recommended_plan_message_goes_to_the_customer():
    sid = _session()
    _sample(sid, "clean")
    a = _analyze(sid)
    msgs = _approve(sid, a["verdict"]["winner"])["messages"]
    assert [m["to_name"] for m in msgs] == ["Meridian Retail Group"] and "advance" in msgs[0]["body"]


def test_combined_plan_messages_every_party():
    sid = _session()
    _sample(sid, "clean")
    a = _analyze(sid)
    combo = next(p for p in a["plans"] if p["feasible"] and p["advance_pct"] > 0
                 and p["supplier_extension"] and p["financing"])
    msgs = _approve(sid, combo["id"])["messages"]
    assert [m["to_name"] for m in msgs] == ["Meridian Retail Group", "Brightwave Supplies",
                                            combo["financing"]["lender"]]
    assert all(m["sent"] for m in msgs)
    assert "Payment schedule" in msgs[1]["subject"] and "Financing" in msgs[2]["subject"]


def test_fraud_check_options_hold_keeps_block_and_original_account_clears_it():
    sid = _session()
    view = _sample(sid, "fraud")
    flag = next(f for f in view["flags"] if f["code"] == "BANK_CHANGE")
    ids = {o["id"]: o for o in flag["options"]}
    assert {"verified_call", "use_original", "hold", "report"} <= set(ids)
    assert not ids["hold"]["clears"] and ids["verified_call"]["needs_note"]
    v = client.post("/api/flags/resolve", json={"session_id": sid, "code": "BANK_CHANGE",
                                                "action": "hold"}).json()
    f = next(f for f in v["flags"] if f["code"] == "BANK_CHANGE")
    assert not f["resolved"] and f["decision"]["action"] == "hold"
    assert _analyze(sid)["verdict"]["execution_blocks"]
    client.post("/api/flags/resolve", json={"session_id": sid, "code": "BANK_CHANGE",
                                            "action": "use_original"})
    assert _analyze(sid)["verdict"]["execution_blocks"] == ["Look-alike supplier email domain"]
    client.post("/api/flags/resolve", json={"session_id": sid, "code": "LOOKALIKE_DOMAIN",
                                            "action": "verified_call", "note": "Called on our saved number"})
    assert _analyze(sid)["verdict"]["execution_blocks"] == []
    assert client.post("/api/flags/resolve", json={"session_id": sid, "code": "BANK_CHANGE",
                                                   "action": "made_up"}).status_code == 400
    assert client.post("/api/flags/resolve", json={"session_id": sid, "code": "NOPE",
                                                   "action": "hold"}).status_code == 404


def test_non_blocking_check_decision_is_recorded():
    sid = _session()
    view = _sample(sid, "fraud")
    flag = next(f for f in view["flags"] if not f["blocks_execution"])
    opt = flag["options"][0]
    v = client.post("/api/flags/resolve", json={"session_id": sid, "code": flag["code"],
                                                "action": opt["id"], "note": "ok"}).json()
    f = next(x for x in v["flags"] if x["code"] == flag["code"])
    assert f["resolved"] and f["decision"]["label"] == opt["label"]


def test_log_says_where_each_step_ran_and_sandbox_shows_what_it_did():
    sid = _session()
    _sample(sid, "clean")
    a = _analyze(sid)
    appr = _approve(sid, a["verdict"]["winner"])
    assert client.post("/api/execute", json={"session_id": sid}).json()["ok"]
    client.post("/api/t3", json={"session_id": sid, "action": "live_transfer"})
    entries = client.get(f"/api/log?session_id={sid}").json()["entries"]
    where = {e["tool"]: e["where"] for e in entries}
    assert where["outbox.send"] == where["bank.post"] == "sandbox"
    assert where["request_approval"] == "owner" and where["simulate+rank_plans"] == "engine"
    assert where["bank.live_transfer"] == "blocked"
    assert all(e["what"] for e in entries)
    sb = client.get(f"/api/sandbox?session_id={sid}").json()
    assert sb["outbox"][0]["approval_id"] == appr["id"] and sb["outbox"][0]["to"].endswith(".example")
    assert sb["bank"]["approval_id"] == appr["id"] and sb["bank"]["rows"]
    winner = next(p for p in a["plans"] if p["id"] == a["verdict"]["winner"])
    assert min(r["balance"] for r in sb["bank"]["rows"]) == winner["min_balance"]
    assert sb["lender"] == []  # the 50% advance plan uses no loan
