"""Regression tests locking the worked example (proposal section 6).

The reference values were computed by hand from the dated cash table, i.e.
independently of the engine's aggregation path.
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent  # noqa: E402
from case_data import CASE  # noqa: E402
from engine import Plan, enumerate_plans, simulate  # noqa: E402

D = Decimal


def _plan(pid):
    return {p.id: p for p in enumerate_plans(CASE)}[pid]


def test_accept_as_is_breaches():
    r = simulate(CASE, _plan("accept-as-is"), 60)
    assert r.min_balance == D("-4500.00")
    assert r.min_day == 45
    assert r.first_breach_day == 20
    assert not r.feasible


def test_decline_is_feasible():
    r = simulate(CASE, _plan("decline"), 60)
    assert r.min_balance == D("14000.00")
    assert r.min_day == 45
    assert r.first_breach_day is None
    assert r.financing_cost == 0


def test_advance_50_feasible_and_robust():
    r = simulate(CASE, _plan("adv50_ext0_nofin"), 60, agent.STRESS_DELAYS)
    assert r.feasible and r.robust
    assert r.min_balance == D("10500.00")
    assert r.net_margin == D("11500.00")


def test_supplier_extension_alone_fails():
    r = simulate(CASE, _plan("adv0_ext1_nofin"), 60)
    assert not r.feasible
    assert r.first_breach_day == 40  # deferred supplier payments land on day 40
    assert r.min_balance == D("-4500.00")


def test_financing_cost():
    r = simulate(CASE, _plan("adv0_ext0_OFF-1"), 60, agent.STRESS_DELAYS)
    assert r.financing_cost == D("675.00")  # 3.5% of 15,000 = 525 + 150 origination
    assert r.net_margin == D("10825.00")
    assert r.robust is False
    assert r.stress_fail_day == 61
    # stress path bottoms out at 10,500 - 15,675
    r2 = simulate(CASE, _plan("adv0_ext0_OFF-1"), 75)
    assert r2.min_balance == D("-5175.00")


def test_advance_plus_extension_plus_financing_is_robust():
    r = simulate(CASE, _plan("adv50_ext1_OFF-2"), 60, agent.STRESS_DELAYS)
    assert r.feasible and r.robust
    assert r.financing_cost == D("500.00")  # 3.5% of 10,000 = 350 + 150
    assert r.net_margin == D("11000.00")


def test_default_ranking_prefers_cheapest():
    ranked = agent.run_agent(CASE, 60, "maximize_margin", False).ranked
    assert ranked[0].plan.id == "adv50_ext0_nofin"  # 50% advance: zero cost, top margin


def test_priority_change_flips_ranking():
    ranked = agent.run_agent(CASE, 60, "avoid_customer_consent", False).ranked
    assert ranked[0].depends_on_customer_consent is False


def test_injection_flagged_verdict_unchanged():
    clean = agent.run_agent(CASE, 60, "maximize_margin", False)
    dirty = agent.run_agent(CASE, 60, "maximize_margin", True)
    assert dirty.injections, "injection must be flagged"
    assert clean.winner.plan.id == dirty.winner.plan.id, "verdict must not change"
