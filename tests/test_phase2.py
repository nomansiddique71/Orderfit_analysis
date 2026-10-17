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


# ------------------------------------------------------ most robust priority


def test_most_robust_ranks_by_tolerance_then_cost_decline_last():
    import agent
    run = agent.run_agent(replace(CASE, reserve=D("11000")), 60, "most_robust", False,
                          stress_delay=15)
    # Only the OFF-3 credit line (repaid day 90) keeps 11,000; it tolerates 29 days.
    assert run.winner.plan.id == "adv25_ext0_OFF-3"
    assert run.winner.tolerance.days == 29
    assert run.ranked[-1].plan.id == "decline"
    tols = [r.tolerance.rank_value for r in run.ranked[:-1]]
    assert tols == sorted(tols, reverse=True)


def test_most_robust_recommends_decline_when_no_accept_plan_survives_stress():
    import agent
    run = agent.run_agent(replace(CASE, reserve=D("11000")), 60, "most_robust", False,
                          stress_delay=30)  # 29 days of tolerance < 30
    assert run.winner.plan.id == "decline"


def test_default_acme_most_robust():
    import agent
    run = agent.run_agent(CASE, 60, "most_robust", False)
    assert run.winner.plan.id == "adv50_ext0_nofin"  # never-pays-safe and free


# ------------------------------------------------------ minimum safe loan


def test_minimum_safe_loan_acme_off3():
    # As-is with the customer 15 days late (day 75): day-45 low is -4,500, so the
    # loan must be >= 12,500 to keep 8,000. Repaid day 90, after the late payment.
    offer = {o.id: o for o in CASE.financing_offers}["OFF-3"]
    principal, r = engine.minimum_safe_loan(CASE, offer, 60, 15)
    assert principal == D("12500")
    assert r.financing_cost == D("662.50")  # 12,500 x 1.5% x 3 + 100
    assert r.robust and r.min_balance == D("8000.00")
    # one step smaller fails
    smaller = offer.with_principal(D("12000"))
    assert not engine.simulate(CASE, engine.Plan("p", "p", D(0), False, smaller), 60, [15]).robust


def test_minimum_safe_loan_none_within_limits():
    # 12,500 is needed (see above); a lender capped at 12,000 cannot make it work.
    offer = {o.id: o for o in CASE.financing_offers}["OFF-3"]
    tight = replace(offer, max_principal=D("12000"))
    assert engine.minimum_safe_loan(CASE, tight, 60, 15) is None


def test_minimum_safe_loan_offered_as_plan_and_portal_checks_range():
    import agent
    import sandbox
    run = agent.run_agent(CASE, 60, "maximize_margin", False)
    assert "minloan_OFF-3" in run.results
    portal = sandbox.MockLenderPortal({o.id: o for o in CASE.financing_offers})
    f = run.results["minloan_OFF-3"].plan.financing
    terms = {"principal": str(f.principal), "fee_pct": str(f.fee_pct),
             "origination": str(f.origination), "monthly_rate_pct": str(f.monthly_rate_pct),
             "draw_day": f.draw_day, "repay_day": f.repay_day}
    assert portal.accept("OFF-3", terms)[0]
    assert not portal.accept("OFF-3", {**terms, "principal": "25000"})[0]  # above max
    assert not portal.accept("OFF-3", {**terms, "monthly_rate_pct": "0.5"})[0]  # invented rate


# ------------------------------------------------------------- scenarios


def _outcomes(pid):
    import agent
    return {o.scenario.key: o for o in agent.scenario_table(
        CASE, engine.simulate(CASE, _plan(pid), 60), 60, agent.standard_scenarios())}


def test_scenarios_hand_checked_for_50pct_advance():
    o = _outcomes("adv50_ext0_nofin")
    assert o["base"].order_net == D("11500.00")
    # 70% of the 15,000 balance = 10,500; 15,000 + 10,500 - 18,500 costs = 7,000
    assert o["partial"].order_net == D("7000.00") and o["partial"].reserve_ok
    # never pays: 15,000 advance - 18,500 costs = -3,500 (maximum loss 3,500)
    assert o["never"].order_net == D("-3500.00")
    # +10% on Brightwave's 12,000 + 5,000 = +1,700 -> low 10,500 - 1,700 = 8,800
    assert o["price"].min_balance == D("8800.00") and o["price"].order_net == D("9800.00")
    # 14 days late = 2 started weeks x 1% x 30,000 = 600 penalty; delivery day 44 > 30
    assert o["late"].penalty == D("600.00") and o["late"].order_net == D("10900.00")
    assert any("day 44" in v for v in o["late"].violations)


def test_price_increase_moves_as_is_breach_earlier():
    # 30,000 - 13,200 = 16,800; -3,000 (d10) = 13,800; -7,000 (d15) = 6,800 < 8,000
    o = _outcomes("accept-as-is")
    assert o["base"].first_breach_day == 20 and o["price"].first_breach_day == 15


def test_money_at_risk_by_cancellation_day():
    assert engine.money_at_risk(CASE, _plan("accept-as-is")) == [
        (0, D("12000")), (20, D("17000")), (30, D("18500"))]
    # the 15,000 advance covers the deposit; risk starts with the day-20 payment
    assert engine.money_at_risk(CASE, _plan("adv50_ext0_nofin")) == [
        (0, D("0")), (20, D("2000.00")), (30, D("3500.00"))]


# ------------------------------------------------------ no plan survives


def test_no_plan_survives_recommends_decline_and_smallest_change():
    import agent
    # reserve 11,000 and no financing allowed: 50% advance bottoms at 10,500 < 11,000.
    case = replace(CASE, reserve=D("11000"), max_financing_cost=D("0"))
    run = agent.run_agent(case, 60, "maximize_margin", False)
    assert run.no_plan_survives and run.winner.plan.id == "decline"
    assert agent.uncertainty_rating(run)[0] == "HIGH"
    # 55% advance: -4,500 + 16,500 = 12,000 on day 45 >= 11,000 (50% gives 10,500)
    assert run.smallest_changes[0].startswith("Ask the customer for a 55% advance (16,500)")
    assert "lowest balance becomes 12,000 on day 45" in run.smallest_changes[0]


def test_no_plan_survives_names_the_hard_constraint():
    import agent
    run = agent.run_agent(replace(CASE, delivery_day=35), 60, "maximize_margin", False)
    assert run.no_plan_survives
    assert any("misses the required day 30" in c for c in run.smallest_changes)


def test_default_acme_has_surviving_plans():
    import agent
    assert not agent.run_agent(CASE, 60, "maximize_margin", False).no_plan_survives


# ------------------------------------------------------------ funding gap


def test_funding_gap_as_is_hand_checked():
    # As-is: d20 3,000 < 8,000 (first breach); d25 7,000; d30 5,500; d40 2,500;
    # d45 -4,500; d60 the 30,000 arrives *during* the day (same-day rule), so the
    # start-of-day balance is still -4,500. Below the reserve from day 20 through
    # day 60 = 41 days. Need: 8,000 - (-4,500) = 12,500.
    gap = engine.funding_gap(engine.simulate(CASE, _plan("accept-as-is"), 60), CASE.reserve)
    assert (gap.amount, gap.from_day, gap.until_day, gap.days) == (D("12500"), 20, 60, 41)
    assert engine.funding_gap(engine.simulate(CASE, _plan("decline"), 60), CASE.reserve).days == 0
