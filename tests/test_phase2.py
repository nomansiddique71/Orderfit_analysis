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


# ------------------------------------------------------- delay tolerance


def test_tolerance_matches_brute_force_day_scan():
    """Binary search result == scanning every payment day one by one."""
    for plan in engine.enumerate_plans(CASE):
        tol = engine.delay_tolerance(CASE, plan, 60)
        ok = [engine.feasible_at(CASE, plan, 60 + d) for d in range(0, 120)]
        if tol.kind == "fails_on_time":
            assert not ok[0]
        elif tol.kind == "never_pays_safe":
            assert all(ok) and engine.feasible_at(CASE, plan, None)
        else:
            assert all(ok[: tol.days + 1]) and not any(ok[tol.days + 1:]), plan.id


def test_x01_safe_even_if_never_paid():
    # 50% advance: low point 10,500 on day 45 comes before any balance payment.
    assert engine.delay_tolerance(CASE, _plan("adv50_ext0_nofin"), 60).kind == "never_pays_safe"
    assert engine.delay_tolerance(CASE, _plan("decline"), 60).kind == "never_pays_safe"


def test_x02_fails_even_if_paid_on_time():
    assert engine.delay_tolerance(CASE, _plan("accept-as-is"), 60).kind == "fails_on_time"


def test_tolerance_days_hand_checked():
    # OFF-1: repay 15,675 on day 61. Paying on day 61 is too late (outflows first):
    # 10,500 - 15,675 = -5,175. So the customer may be 0 days late.
    t = engine.delay_tolerance(CASE, _plan("adv0_ext0_OFF-1"), 60)
    assert (t.kind, t.days, t.last_safe_pay_day) == ("days", 0, 60)
    # 25% advance + OFF-3 (12,000, repay 12,640 on day 90): unpaid, day 45 = 15,000,
    # day 90 = 15,000 - 12,640 = 2,360 < 8,000 -> customer must pay by day 89.
    t = engine.delay_tolerance(CASE, _plan("adv25_ext0_OFF-3"), 60)
    assert (t.days, t.last_safe_pay_day) == (29, 89)
    assert t.survives(15) and not t.survives(30)


def test_stress_choice_changes_robustness():
    import agent
    r15 = agent.run_agent(CASE, 60, "maximize_margin", False, stress_delay=15)
    r30 = agent.run_agent(CASE, 60, "maximize_margin", False, stress_delay=30)
    assert r15.results["adv25_ext0_OFF-3"].robust
    assert not r30.results["adv25_ext0_OFF-3"].robust
