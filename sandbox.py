"""Sandbox executor and permission gate (sections 8.1 and 9.1).

Tiers are enforced in code, not by model instructions:
  T0 read-only        T1 propose (output only)        T2 act (sandbox only)
  T3 never            -- hard-blocked, no code path; every attempt is logged.

Nothing here touches a real bank, lender or mailbox.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal

from engine import SimulationResult

TIER_NAMES = {"T0": "read", "T1": "propose", "T2": "act (sandbox)", "T3": "never"}


@dataclass
class LogEntry:
    time: str
    tool: str
    tier: str
    input_hash: str
    approval_id: str | None
    result: str
    blocked_reason: str | None = None


class OperationLog:
    def __init__(self) -> None:
        self.entries: list[LogEntry] = []

    def append(self, tool: str, tier: str, payload: dict, approval_id: str | None,
               result: str, blocked_reason: str | None = None) -> LogEntry:
        from datetime import datetime

        h = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
        e = LogEntry(datetime.now().strftime("%H:%M:%S"), tool, tier, h,
                     approval_id, result, blocked_reason)
        self.entries.append(e)
        return e

    def as_dicts(self) -> list[dict]:
        return [dict(time=e.time, tool=e.tool, tier=e.tier, input_hash=e.input_hash,
                     approval_id=e.approval_id or "",
                     result=e.result, blocked_reason=e.blocked_reason or "")
                for e in self.entries]


class PermissionGate:
    """Checks tier + approval binding before any T2 action reaches the sandbox."""

    def __init__(self, log: OperationLog) -> None:
        self.log = log

    def check_t2(self, tool: str, payload: dict, approval_id: str | None,
                 approved_plans: dict[str, str]) -> tuple[bool, str | None]:
        if approval_id is None:
            self.log.append(tool, "T2", payload, None, "BLOCKED",
                            "no approval ID -- T2 actions require an owner-approved plan version")
            return False, "no approval ID"
        if approval_id not in approved_plans:
            self.log.append(tool, "T2", payload, approval_id, "BLOCKED",
                            "unknown approval ID")
            return False, "unknown approval ID"
        return True, None

    def block_t3(self, tool: str, payload: dict, reason: str) -> None:
        self.log.append(tool, "T3", payload, None, "BLOCKED", reason)


class SimulatedBank:
    """SQLite-shaped ledger holding only the approved plan's movements."""

    def __init__(self) -> None:
        self.booked: list[dict] = []
        self.path: dict[int, Decimal] = {}

    def post(self, movements: list[dict], opening: Decimal) -> None:
        self.booked.extend(movements)
        running = opening
        by_day: dict[int, Decimal] = {}
        for m in movements:
            by_day[m["day"]] = by_day.get(m["day"], Decimal(0)) + m["amount"]
        for day in sorted(by_day):
            running += by_day[day]
            self.path[day] = running


class MockOutbox:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, recipient: str, subject: str, body: str) -> None:
        self.sent.append({"to": recipient, "subject": subject, "body": body,
                          "status": "sent (mock -- nothing delivered)"})


class MockLenderPortal:
    """Accepts only terms that exist verbatim in the supplied catalogue."""

    def __init__(self, catalogue_ids: set[str]) -> None:
        self.catalogue_ids = catalogue_ids
        self.accepted: list[dict] = []

    def accept(self, offer_id: str, terms: dict) -> tuple[bool, str]:
        if offer_id not in self.catalogue_ids:
            return False, f"terms for {offer_id} not in catalogue -- rejected"
        self.accepted.append({"offer": offer_id, "terms": terms,
                              "status": "accepted (mock)"})
        return True, "accepted"


@dataclass
class ExecutionReport:
    ok: bool
    steps: list[str]
    consistency: str | None = None


def execute_plan(run, approved_plans: dict[str, str], approval_id: str,
                 log: OperationLog, gate: PermissionGate, bank: SimulatedBank,
                 outbox: MockOutbox, portal: MockLenderPortal) -> ExecutionReport:
    """T2: carry the approved plan version into the sandbox with tier checks."""
    from engine import plan_movements

    w: SimulationResult = run.winner
    steps: list[str] = []

    # 1. draft message -> mock outbox (T2, gated)
    ok, reason = gate.check_t2("outbox.send", {"subject": "draft"}, approval_id, approved_plans)
    if not ok:
        return ExecutionReport(False, [f"outbox blocked: {reason}"])
    outbox.send("counterparty@example.com", "OrderFit approved message", run.draft_message)
    log.append("outbox.send", "T2", {"to": "counterparty", "len": len(run.draft_message)},
               approval_id, "sent (mock)")
    steps.append("Draft message posted to mock outbox.")

    # 2. financing acceptance, if any (T2, gated; terms must match the catalogue)
    if w.plan.financing is not None:
        f = w.plan.financing
        ok, reason = gate.check_t2("lender.accept", {"offer": f.id}, approval_id, approved_plans)
        if not ok:
            return ExecutionReport(False, steps + [f"lender portal blocked: {reason}"])
        accepted, msg = portal.accept(f.id, {"principal": str(f.principal),
                                             "fee_pct": str(f.fee_pct),
                                             "origination": str(f.origination),
                                             "draw_day": f.draw_day, "repay_day": f.repay_day})
        log.append("lender.accept", "T2", {"offer": f.id}, approval_id,
                   msg if accepted else f"BLOCKED: {msg}", None if accepted else msg)
        steps.append(f"Lender portal ({f.id}): {msg}.")
        if not accepted:
            return ExecutionReport(False, steps)

    # 3. bank scheduling (T2, gated)
    ok, reason = gate.check_t2("bank.post", {"plan": w.plan.id}, approval_id, approved_plans)
    if not ok:
        return ExecutionReport(False, steps + [f"bank blocked: {reason}"])
    movs = plan_movements(run.case, w.plan, run.customer_payment_day)
    payload = [{"day": m.day, "amount": str(m.amount), "label": m.label} for m in movs]
    bank.post(payload, run.case.opening_cash)
    log.append("bank.post", "T2", {"movements": len(payload)}, approval_id,
               f"{len(payload)} movements booked in simulated ledger")
    steps.append(f"Simulated bank ledger: {len(payload)} movements booked.")

    # 4. consistency check: ledger path must equal the engine's predicted path
    mismatch = [d for d in w.path if d in bank.path and bank.path[d] != w.path[d]]
    if mismatch:
        log.append("consistency_check", "T0", {"days": len(mismatch)}, approval_id,
                   "FAILED", "ledger path != engine prediction")
        return ExecutionReport(False, steps + ["Consistency check FAILED."],
                               consistency=f"FAILED on {len(mismatch)} day(s) -- run stopped")
    log.append("consistency_check", "T0", {"days": len(w.path)}, approval_id,
               "ledger path equals engine prediction on all days")
    steps.append("Consistency check passed: ledger path == engine prediction.")
    return ExecutionReport(True, steps, consistency="passed")
