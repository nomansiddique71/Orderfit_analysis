"""Money that moved before today: a customer advance already received and
supplier payments already made. Both are already in today's cash, so neither
is a future movement, but both still count for the order's margin."""

import sys
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import engine  # noqa: E402
from case_data import CASE  # noqa: E402
from test_api import _analyze, _sample, _session  # noqa: E402

ASIS = next(p for p in engine.enumerate_plans(CASE) if p.id == "accept-as-is")
ADV50 = next(p for p in engine.enumerate_plans(CASE) if p.id == "adv50_ext0_nofin")


def _customer(movs, kind):
    return [m for m in movs if m.kind == kind]


def test_no_advance_received_keeps_the_original_numbers():
    assert CASE.advance_received == 0 and CASE.balance_due == CASE.order_value
    pay = _customer(engine.plan_movements(CASE, ASIS, 60), "order_revenue")
    assert [m.amount for m in pay] == [D("30000")]


def test_advance_received_reduces_what_the_customer_still_owes():
    case = replace(CASE, advance_received=D("6000"))
    pay = _customer(engine.plan_movements(case, ASIS, 60), "order_revenue")
    assert [m.amount for m in pay] == [D("24000")]
    # a plan's 50% advance is 50% of the balance still owed
    movs = engine.plan_movements(case, ADV50, 60)
    assert [m.amount for m in _customer(movs, "advance")] == [D("12000")]
    assert [m.amount for m in _customer(movs, "order_revenue")] == [D("12000")]
    assert case.gross_margin == CASE.gross_margin  # same order, same margin


def test_costs_already_paid_count_for_margin_but_not_cash():
    first = CASE.order_costs[0]
    case = replace(CASE, order_costs=CASE.order_costs[1:], costs_already_paid=-first.amount)
    assert case.gross_margin == CASE.gross_margin
    assert all(m.label != first.label for m in engine.plan_movements(case, ASIS, 60))
    risk = engine.money_at_risk(case, ASIS)
    assert risk[0] == (0, -first.amount)


def test_api_advance_and_paid_supplier_row():
    sid = _session()
    view = _sample(sid, "clean")
    assert any(f["key"] == "advance_received" for f in view["facts"])
    base = _analyze(sid)
    pays = [{"label": p["label"], "amount": p["amount"]["value"], "day": p["day"]["value"],
             "paid": i == 0} for i, p in enumerate(view["supplier_payments"])]
    r = _analyze(sid, edits={"advance_received": "USD 6,000", "supplier_payments": pays})
    assert r["ok"]
    assert r["case"]["gross_margin"] == base["case"]["gross_margin"]
    labels = [m["label"] for m in r["case"]["movements"]]
    assert view["supplier_payments"][0]["label"] not in labels
    revenue = [m for m in next(p for p in r["plans"] if p["id"] == "accept-as-is")["path"]]
    assert revenue  # still simulates
    assert any("already paid 6,000" in a for a in r["case"]["assumptions"])


def test_api_rejects_advance_larger_than_order():
    sid = _session()
    _sample(sid, "clean")
    r = _analyze(sid, edits={"advance_received": "USD 90,000"})
    assert not r["ok"] and any("larger than the order value" in m for m in r["missing"])


def test_draft_uses_case_currency():
    sid = _session()
    _sample(sid, "ambiguous")
    r = _analyze(sid)
    assert "USD" not in r["draft"] and "INR" in r["draft"]
