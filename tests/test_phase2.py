"""Phase 2: stress testing, financing model, scenarios, decision depth."""

import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine  # noqa: E402
from case_data import CASE  # noqa: E402
from engine import plan_movements  # noqa: E402

D = Decimal


def _plan(pid, case=CASE):
    return {p.id: p for p in engine.enumerate_plans(case)}[pid]


def test_advance_is_part_of_order_value_not_extra_cash():
    # 50% advance on a 30,000 order: 15,000 on day 0 + 15,000 on payment day = 30,000 total.
    movs = plan_movements(CASE, _plan("adv50_ext0_nofin"), 60)
    received = [m.amount for m in movs if m.kind in ("advance", "order_revenue")]
    assert sorted(received) == [D("15000.00"), D("15000.00")]
    # end of horizon: same cash as accept-as-is (same order, money just arrives earlier)
    r_adv = engine.simulate(CASE, _plan("adv50_ext0_nofin"), 60)
    r_asis = engine.simulate(CASE, _plan("accept-as-is"), 60)
    last = max(r_asis.path)
    assert r_adv.path[last] == r_asis.path[last]


# ------------------------------------------------------- financing model


def test_monthly_interest_plus_fee():
    # 5,000 at 1.5% per month for 60 days (= 2 months) + 100 fee = 150 + 100 = 250
    o = engine.FinancingOffer("L", "Lender", D("5000"), D("0"), D("100"), draw_day=25,
                              repay_day=85, expires_day=99, monthly_rate_pct=D("1.5"))
    assert o.cost() == D("250.00")
    assert o.with_principal(D("9000")).cost() == D("370.00")  # 9,000 x 3% + 100


def test_flat_fee_offers_unchanged():
    offs = {o.id: o for o in CASE.financing_offers}
    assert offs["OFF-1"].cost() == D("675.00") and offs["OFF-2"].cost() == D("500.00")
    assert offs["OFF-3"].cost() == D("640.00")  # 12,000 x 1.5% x 3 months + 100


def test_ineligible_offer_is_marked_not_offered():
    bad = dict((o.id, why) for o, why in engine.ineligible_offers(CASE))
    assert list(bad) == ["OFF-4"] and "below Northwind Microfinance's minimum 5,000" in bad["OFF-4"]
    assert not any(p.financing and p.financing.id == "OFF-4" for p in engine.enumerate_plans(CASE))
    import agent
    run = agent.run_agent(CASE, 60, "maximize_margin", False)
    assert any(a.rule == "ineligible_offer" for a in run.alerts)
