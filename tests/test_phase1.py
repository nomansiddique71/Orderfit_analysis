"""Phase 1: correctness and honesty rules in the engine and agent."""

import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_data import CASE  # noqa: E402
from engine import Movement, Plan, daily_balances, simulate  # noqa: E402

D = Decimal


def _plan(pid):
    from engine import enumerate_plans
    return {p.id: p for p in enumerate_plans(CASE)}[pid]


# ------------------------------------------------------------ M-10 same day


def test_same_day_outflows_applied_before_inflows():
    # opening 10,000; day 5: pay 8,000 and receive 8,000.
    # End of day is 10,000 but the intra-day low is 10,000 - 8,000 = 2,000.
    movs = [Movement(5, D("8000"), "in", "receivable"),
            Movement(5, D("-8000"), "out", "obligation")]
    low, end = daily_balances(D("10000"), movs)
    assert low == {5: D("2000")}
    assert end == {5: D("10000")}


def test_same_day_order_independent():
    a = [Movement(5, D("8000"), "in", "receivable"), Movement(5, D("-8000"), "out", "obligation")]
    assert daily_balances(D("10000"), a) == daily_balances(D("10000"), a[::-1])


def test_intraday_dip_is_a_breach():
    # Move the day-25 receivable onto payroll day 15 (7,000 out, 4,000 in).
    # Decline path: 30,000 -3,000 (d10) = 27,000; d15 low = 27,000 - 7,000 = 20,000.
    # Lower the reserve trigger so only the intra-day low can breach it:
    # end of day 15 = 24,000, intra-day low = 20,000; reserve 21,000 must breach on day 15.
    base = tuple(replace(m, day=15) if m.label.startswith("Receivable") else m
                 for m in CASE.base_movements)
    case = replace(CASE, base_movements=base, reserve=D("21000"))
    r = simulate(case, _plan("decline"), 60)
    assert r.path[15] == D("24000")
    assert r.low_path[15] == D("20000")
    assert r.first_breach_day == 15
    assert not r.feasible


# ------------------------------------------------------ hard constraints


def test_financing_cost_cap_is_enforced():
    # OFF-1 costs 675 (3.5% of 15,000 + 150). A cap of 600 must exclude it.
    case = replace(CASE, max_financing_cost=D("600"))
    r = simulate(case, _plan("adv0_ext0_OFF-1"), 60)
    assert any("exceeds the cap" in v for v in r.violations)
    assert not r.feasible
    # OFF-2 costs 500, under the cap: no violation
    r2 = simulate(case, _plan("adv50_ext1_OFF-2"), 60)
    assert r2.violations == [] and r2.feasible


def test_late_delivery_makes_accept_plans_infeasible():
    case = replace(CASE, delivery_day=35)
    r = simulate(case, _plan("adv50_ext0_nofin"), 60)
    assert r.reserve_ok  # cash is fine...
    assert not r.feasible  # ...but delivery misses day 30
    assert any("misses the required day 30" in v for v in r.violations)
    assert simulate(case, _plan("decline"), 60).feasible


def test_violations_raise_alert_and_winner_is_decline():
    import agent
    run = agent.run_agent(replace(CASE, delivery_day=35), 60, "maximize_margin", False)
    assert run.winner.plan.id == "decline"
    assert any(a.rule == "constraint_violation" for a in run.alerts)


# ------------------------------------------------------ overdue receivable


def test_overdue_receivable_alert_shows_breach_effect():
    import agent
    run = agent.run_agent(CASE, 60, "maximize_margin", False)
    assert run.winner.plan.id == "adv50_ext0_nofin"
    alert = next(a for a in run.alerts if a.rule == "overdue_receivable")
    assert "5 day(s) overdue" in alert.message
    # By hand, 50% advance without the 4,000 receivable: d0 30,000-12,000+15,000 = 33,000;
    # d10 30,000; d15 23,000; d20 18,000; d25 18,000 (no receipt); d30 16,500;
    # d40 13,500; d45 6,500 < 8,000 reserve -> first breach day 45.
    assert "no breach → day 45" in alert.message
    assert alert.severity == "critical"
    # As-is already breaches on day 20 (before day 25), so that date is unchanged.
    assert "as-is first breach day 20 → day 20" in alert.message


# ------------------------------------------------------ low confidence


def test_low_confidence_simulation_field_makes_result_provisional():
    import agent
    run = agent.run_agent(CASE, 60, "maximize_margin", False)
    # regex extraction gives the early-settlement discount 0.62 (< 0.7): it can
    # move the customer's payment date, so the day-60 result is only provisional.
    assert run.provisional
    assert [f.name for f in run.provisional_fields] == ["Early-settlement discount"]
    assert agent.uncertainty_rating(run)[1].startswith("PROVISIONAL")
    assert any(a.rule == "provisional" for a in run.alerts)

    key = run.provisional_fields[0].key
    confirmed = agent.run_agent(CASE, 60, "maximize_margin", False, frozenset({key}))
    assert not confirmed.provisional
    assert confirmed.winner.plan.id == run.winner.plan.id  # numbers unchanged


def test_low_confidence_non_simulation_field_is_not_provisional():
    import agent
    f = agent.ExtractedField("Deposit refundability", "x", "Q-3312", "x", 0.4)
    assert f.low_confidence and not f.affects_simulation


# ------------------------------------------------------------ near tie


def test_default_acme_has_no_near_tie():
    # 50% advance + supplier extension has the same margin but is dominated
    # (same headroom, more consents), so the owner is not asked.
    import agent
    assert agent.run_agent(CASE, 60, "maximize_margin", False).near_tie is None


def test_near_tie_detected_and_owner_choice_wins():
    import agent
    case = replace(CASE, reserve=D("5000"))
    run = agent.run_agent(case, 60, "avoid_customer_consent", False)
    top, other = run.near_tie
    # OFF-2 costs 500. The minimum safe OFF-3 loan is 9,500 (-4,500 + P >= 5,000 on
    # day 45), costing 9,500 x 1.5% x 3 months + 100 = 527.50: 27.50 apart, inside
    # 1% of 30,000 (= 300). OFF-2 fails the 15-day stress (repays day 61); the
    # sized loan (repaid day 90) survives it.
    assert top.plan.id == "adv0_ext0_OFF-2" and other.plan.id == "minloan_OFF-3"
    assert run.winner.plan.id == "adv0_ext0_OFF-2"
    assert "higher net margin (+28)" in agent.plan_strengths(top, other)
    assert agent.plan_strengths(other, top) == ["survives the late-payment stress"]

    chosen = agent.run_agent(case, 60, "avoid_customer_consent", False,
                             tie_choice="minloan_OFF-3")
    assert chosen.winner.plan.id == "minloan_OFF-3"
    assert chosen.owner_tie_choice == "minloan_OFF-3"
    # a choice outside the tied pair is ignored
    bogus = agent.run_agent(case, 60, "avoid_customer_consent", False, tie_choice="decline")
    assert bogus.winner.plan.id == "adv0_ext0_OFF-2"
