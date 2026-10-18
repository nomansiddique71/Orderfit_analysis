"""Per-plan money breakdown: every movement, totals that add up, and reasons."""

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import amount_text  # noqa: E402
from test_api import _analyze, _sample, _session, client  # noqa: E402


def _bd(sid, pid):
    r = client.post("/api/breakdown", json={"session_id": sid, "plan_id": pid})
    assert r.status_code == 200, r.text
    return r.json()


def test_totals_add_up_to_the_running_balance():
    sid = _session()
    _sample(sid, "clean")
    a = _analyze(sid)
    for p in a["plans"]:
        b = _bd(sid, p["id"])
        assert b["total_in"] == sum(b["money_in"].values())
        assert b["total_out"] == sum(b["money_out"].values())
        assert b["opening"] + b["total_in"] - b["total_out"] == b["end"]
        assert b["low"] == p["min_balance"] and b["low_day"] == p["min_day"]
        assert b["rows"][-1]["balance"] == b["end"]


def test_reasons_follow_the_engine():
    sid = _session()
    _sample(sid, "clean")
    _analyze(sid)
    asis = _bd(sid, "accept-as-is")
    assert asis["verdict"] == "reject"
    assert any("below your USD 8,000 reserve" in t and "day 20" in t for t in asis["reasons_against"])
    rec = _bd(sid, "adv50_ext0_nofin")
    assert rec["verdict"] == "accept" and rec["summary"].startswith("Recommended")
    assert any("50% (USD 15,000) upfront" in t for t in rec["reasons_against"])
    assert rec["profit"] == {"income": 30000.0, "costs": 18500.0, "financing": 0.0, "net": 11500.0}
    assert _bd(sid, "decline")["verdict"] == "neutral"


def test_unknown_plan_is_404():
    sid = _session()
    _sample(sid, "clean")
    _analyze(sid)
    assert client.post("/api/breakdown", json={"session_id": sid, "plan_id": "nope"}).status_code == 404


def test_lakh_grouping_for_bdt_and_inr():
    assert amount_text(Decimal("12500000"), "BDT") == "BDT 1,25,00,000"
    assert amount_text(Decimal("500000"), "INR") == "INR 5,00,000"
    assert amount_text(Decimal("-4500"), "USD") == "USD -4,500"
