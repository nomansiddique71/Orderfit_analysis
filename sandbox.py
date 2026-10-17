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


OVERRIDE_TAG = "[RESERVE OVERRIDE]"


@dataclass(frozen=True)
class Approval:
    """An owner approval bound to one exact plan version.

    override=True means the owner knowingly approved a plan that breaches the
    minimum cash reserve. That flag travels with the approval into every log
    entry and the execution report; it is never dropped or inferred.
    """

    approval_id: str
    plan_version: str
    plan_id: str
    plan_label: str
    override: bool = False
    reason: str = ""

    @property
    def display_label(self) -> str:
        return f"{OVERRIDE_TAG} {self.plan_label}" if self.override else self.plan_label


class PermissionGate:
    """Checks tier + approval binding before any T2 action reaches the sandbox."""

    def __init__(self, log: OperationLog) -> None:
        self.log = log

    def check_t2(self, tool: str, payload: dict, approval_id: str | None,
                 approvals: dict[str, Approval], plan_version: str
                 ) -> tuple[bool, str | None]:
        """approvals maps approval_id -> Approval; plan_version is what is about to run."""
        if approval_id is None:
            self.log.append(tool, "T2", payload, None, "BLOCKED",
                            "no approval ID -- T2 actions require an owner-approved plan version")
            return False, "no approval ID"
        approval = approvals.get(approval_id)
        if approval is None:
            self.log.append(tool, "T2", payload, approval_id, "BLOCKED",
                            "unknown approval ID")
            return False, "unknown approval ID"
        if approval.plan_version != plan_version:
            self.log.append(tool, "T2", payload, approval_id, "BLOCKED",
                            "approval is bound to a different plan version")
            return False, "approval is bound to a different plan version"
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
            # amounts arrive as strings (JSON-safe payload); parse exactly
            by_day[m["day"]] = by_day.get(m["day"], Decimal(0)) + Decimal(str(m["amount"]))
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
    """Accepts only terms that match the supplied catalogue.

    Rate, fees and dates must equal the catalogue offer exactly; the principal
    must equal the quoted one or lie within the lender's own min/max range.
    """

    def __init__(self, catalogue: dict) -> None:
        self.catalogue = catalogue  # offer id -> engine.FinancingOffer
        self.accepted: list[dict] = []

    def accept(self, offer_id: str, terms: dict) -> tuple[bool, str]:
        offer = self.catalogue.get(offer_id)
        if offer is None:
            return False, f"terms for {offer_id} not in catalogue -- rejected"
        fixed = {"fee_pct": str(offer.fee_pct), "origination": str(offer.origination),
                 "monthly_rate_pct": str(offer.monthly_rate_pct),
                 "draw_day": offer.draw_day, "repay_day": offer.repay_day}
        changed = [k for k, v in fixed.items() if terms.get(k) != v]
        if changed:
            return False, f"terms for {offer_id} differ from catalogue ({', '.join(changed)}) -- rejected"
        principal = Decimal(str(terms.get("principal")))
        in_range = (offer.sizeable and offer.min_principal <= principal <= offer.max_principal)
        if principal != offer.principal and not in_range:
            return False, f"principal {principal:,.0f} not allowed for {offer_id} -- rejected"
        self.accepted.append({"offer": offer_id, "terms": terms,
                              "status": "accepted (mock)"})
        return True, "accepted"


@dataclass
class ExecutionReport:
    ok: bool
    steps: list[str]
    consistency: str | None = None
    override: bool = False


def execute_plan(run, result: SimulationResult, draft: str, approval: Approval,
                 approvals: dict[str, Approval], log: OperationLog, gate: PermissionGate,
                 bank: SimulatedBank, outbox: MockOutbox,
                 portal: MockLenderPortal, blocks: list[str] | None = None) -> ExecutionReport:
    """T2: carry the approved plan version into the sandbox with tier checks.

    result is the engine's simulation of the approved plan (the recommended
    plan, or the one the owner chose under a reserve override).
    blocks: unresolved fraud/integrity flags (doc_checks). While any remain,
    nothing reaches the sandbox, whatever the approval says.
    """
    if blocks:
        log.append("execute_plan", "T2", {"blocks": blocks}, approval.approval_id, "BLOCKED",
                   "unresolved fraud/integrity flag(s): " + "; ".join(blocks))
        return ExecutionReport(False, ["Execution blocked by unresolved fraud/integrity "
                                       "flag(s): " + "; ".join(blocks)],
                               override=approval.override)
    from engine import plan_movements

    w = result
    aid, pv, ovr = approval.approval_id, approval.plan_version, approval.override
    tag = f" {OVERRIDE_TAG}" if ovr else ""
    steps: list[str] = []
    if ovr:
        steps.append(f"{OVERRIDE_TAG} Executing '{w.plan.label}', which breaches the "
                     f"reserve (lowest {w.min_balance:,.0f} on day {w.min_day}). Owner "
                     f"reason: {approval.reason or '(none given)'}")

    def report(ok: bool, extra: list[str], consistency: str | None = None) -> ExecutionReport:
        return ExecutionReport(ok, steps + extra, consistency, override=ovr)

    # 1. draft message -> mock outbox (T2, gated)
    ok, reason = gate.check_t2("outbox.send", {"subject": "draft", "override": ovr},
                               aid, approvals, pv)
    if not ok:
        return report(False, [f"outbox blocked: {reason}"])
    outbox.send("counterparty@example.com", "OrderFit approved message", draft)
    log.append("outbox.send", "T2", {"to": "counterparty", "len": len(draft), "override": ovr},
               aid, "sent (mock)" + tag)
    steps.append("Draft message posted to mock outbox.")

    # 2. financing acceptance, if any (T2, gated; terms must match the catalogue)
    if w.plan.financing is not None:
        f = w.plan.financing
        ok, reason = gate.check_t2("lender.accept", {"offer": f.id, "override": ovr},
                                   aid, approvals, pv)
        if not ok:
            return report(False, [f"lender portal blocked: {reason}"])
        accepted, msg = portal.accept(f.id, {"principal": str(f.principal),
                                             "fee_pct": str(f.fee_pct),
                                             "origination": str(f.origination),
                                             "monthly_rate_pct": str(f.monthly_rate_pct),
                                             "draw_day": f.draw_day, "repay_day": f.repay_day})
        log.append("lender.accept", "T2", {"offer": f.id, "override": ovr}, aid,
                   (msg if accepted else f"BLOCKED: {msg}") + tag, None if accepted else msg)
        steps.append(f"Lender portal ({f.id}): {msg}.")
        if not accepted:
            return report(False, [])

    # 3. bank scheduling (T2, gated)
    ok, reason = gate.check_t2("bank.post", {"plan": w.plan.id, "override": ovr},
                               aid, approvals, pv)
    if not ok:
        return report(False, [f"bank blocked: {reason}"])
    movs = plan_movements(run.case, w.plan, run.customer_payment_day)
    payload = [{"day": m.day, "amount": str(m.amount), "label": m.label} for m in movs]
    bank.post(payload, run.case.opening_cash)
    log.append("bank.post", "T2", {"movements": len(payload), "override": ovr}, aid,
               f"{len(payload)} movements booked in simulated ledger" + tag)
    steps.append(f"Simulated bank ledger: {len(payload)} movements booked.")

    # 4. consistency check: ledger path must equal the engine's predicted path
    mismatch = [d for d in w.path if d in bank.path and bank.path[d] != w.path[d]]
    if mismatch:
        log.append("consistency_check", "T0", {"days": len(mismatch)}, aid,
                   "FAILED" + tag, "ledger path != engine prediction")
        return report(False, ["Consistency check FAILED."],
                      consistency=f"FAILED on {len(mismatch)} day(s) -- run stopped")
    log.append("consistency_check", "T0", {"days": len(w.path)}, aid,
               "ledger path equals engine prediction on all days" + tag)
    steps.append("Consistency check passed: ledger path == engine prediction.")
    return report(True, [], consistency="passed")
