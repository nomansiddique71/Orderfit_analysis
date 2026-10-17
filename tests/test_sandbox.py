"""Approval binding and reserve-override marking in the sandbox (T2)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent  # noqa: E402
import sandbox  # noqa: E402
from case_data import CASE  # noqa: E402
from sandbox import OVERRIDE_TAG, Approval  # noqa: E402


def _env():
    log = sandbox.OperationLog()
    return (log, sandbox.PermissionGate(log), sandbox.SimulatedBank(),
            sandbox.MockOutbox(), sandbox.MockLenderPortal({f.id for f in CASE.financing_offers}))


def _run():
    return agent.run_agent(CASE, 60, "maximize_margin", False)


def test_approved_plan_executes_and_matches_engine():
    run = _run()
    appr = Approval("APP-1", "pv-1", run.winner.plan.id, run.winner.plan.label)
    log, gate, bank, outbox, portal = _env()
    rep = sandbox.execute_plan(run, run.winner, run.draft_message, appr, {"APP-1": appr},
                               log, gate, bank, outbox, portal)
    assert rep.ok and rep.consistency == "passed" and not rep.override
    assert not any(OVERRIDE_TAG in e.result for e in log.entries)


def test_unknown_or_rebound_approval_is_blocked():
    run = _run()
    appr = Approval("APP-1", "pv-1", run.winner.plan.id, run.winner.plan.label)
    log, gate, bank, outbox, portal = _env()
    rep = sandbox.execute_plan(run, run.winner, "x", appr, {}, log, gate, bank, outbox, portal)
    assert not rep.ok and "unknown approval ID" in rep.steps[-1]
    # same ID, but the stored approval is for a different plan version
    other = Approval("APP-1", "pv-OTHER", run.winner.plan.id, run.winner.plan.label)
    rep = sandbox.execute_plan(run, run.winner, "x", appr, {"APP-1": other},
                               log, gate, bank, outbox, portal)
    assert not rep.ok and "different plan version" in rep.steps[-1]
    assert not outbox.sent and not bank.booked


def test_override_is_marked_in_report_and_every_t2_log_entry():
    run = _run()
    as_is = run.results["accept-as-is"]
    assert not as_is.reserve_ok
    appr = Approval("APP-2-OVR", "pv-2", as_is.plan.id, as_is.plan.label,
                    override=True, reason="owner adds personal funds")
    assert appr.display_label.startswith(OVERRIDE_TAG)
    log, gate, bank, outbox, portal = _env()
    rep = sandbox.execute_plan(run, as_is, agent.draft_message(as_is, CASE, 60, None), appr,
                               {"APP-2-OVR": appr}, log, gate, bank, outbox, portal)
    assert rep.ok and rep.override
    assert rep.steps[0].startswith(OVERRIDE_TAG) and "owner adds personal funds" in rep.steps[0]
    assert log.entries and all(OVERRIDE_TAG in e.result for e in log.entries)
    assert "as issued" in outbox.sent[0]["body"]
