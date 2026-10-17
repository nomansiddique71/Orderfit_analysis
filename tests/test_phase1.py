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
