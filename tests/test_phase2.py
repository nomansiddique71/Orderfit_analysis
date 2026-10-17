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
