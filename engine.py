"""OrderFit deterministic financial engine.

Every number shown in the app is computed here with Decimal arithmetic.
The decision layer may *propose*; only this module *verifies* hard
constraints (minimum reserve on every day, delivery date, financing cap).
The model layer can never perform arithmetic or mark an infeasible plan
as feasible -- it only consumes SimulationResult objects from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import product

D = Decimal
ZERO = D("0")
CENT = D("0.01")


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT)


@dataclass(frozen=True)
class Movement:
    """A dated, signed cash movement. Positive = inflow, negative = outflow."""

    day: int
    amount: Decimal
    label: str
    kind: str  # obligation | payroll | receivable | order_cost | order_revenue | advance | financing_draw | financing_repay
    counterparty: str = ""
    certain: bool = True
    deferrable_to: int | None = None  # target day if the supplier grants an extension


@dataclass(frozen=True)
class FinancingOffer:
    id: str
    lender: str
    principal: Decimal
    fee_pct: Decimal  # flat fee, % of principal
    origination: Decimal
    draw_day: int
    repay_day: int
    expires_day: int
    conditions: str = ""

    def cost(self) -> Decimal:
        return money(self.principal * self.fee_pct / D(100) + self.origination)


@dataclass(frozen=True)
class Plan:
    id: str
    label: str
    advance_pct: Decimal  # fraction of the order value requested from the customer
    supplier_extension: bool
    financing: FinancingOffer | None

    @property
    def depends_on_customer_consent(self) -> bool:
        return self.advance_pct > 0

    @property
    def depends_on_supplier_consent(self) -> bool:
        return self.supplier_extension


@dataclass
class SimulationResult:
    plan: Plan
    path: dict[int, Decimal]  # day -> balance (only event days; piecewise-linear between)
    min_balance: Decimal
    min_day: int
    first_breach_day: int | None  # first day balance < reserve
    breach_days: list[int]
    financing_cost: Decimal
    gross_margin: Decimal  # order value - order costs (0 for decline)
    net_margin: Decimal  # gross margin - financing cost
    feasible: bool  # no breach in the base scenario
    robust: bool  # no breach in base AND every stress scenario
    stress_fail_day: int | None  # first breach day under stress, if any
    depends_on_customer_consent: bool
    depends_on_supplier_consent: bool


@dataclass(frozen=True)
class Case:
    name: str
    opening_cash: Decimal
    reserve: Decimal
    order_value: Decimal
    delivery_day: int
    required_delivery_day: int
    base_movements: tuple[Movement, ...]  # existing obligations / receivables
    order_costs: tuple[Movement, ...]  # costs caused by accepting the order
    financing_offers: tuple[FinancingOffer, ...]
    max_financing_cost: Decimal = D("2000")

    @property
    def gross_margin(self) -> Decimal:
        return self.order_value - sum((-m.amount for m in self.order_costs), ZERO)


# ---------------------------------------------------------------- simulation


def plan_movements(case: Case, plan: Plan, customer_payment_day: int) -> list[Movement]:
    """All dated movements for a plan under one customer-payment scenario."""
    if plan.id == "decline":
        return list(case.base_movements)  # declining the order: no order cash flows
    out: list[Movement] = list(case.base_movements)
    for m in case.order_costs:
        if plan.supplier_extension and m.deferrable_to is not None:
            out.append(
                Movement(m.deferrable_to, m.amount, m.label + " (extended terms)", m.kind,
                         m.counterparty, m.certain, None)
            )
        else:
            out.append(m)
    out.append(
        Movement(customer_payment_day, case.order_value, "Customer payment (PO-8841)",
                 "order_revenue", "Meridian Retail Group")
    )
    if plan.advance_pct > 0:
        out.append(
            Movement(0, money(case.order_value * plan.advance_pct),
                     f"Customer advance ({plan.advance_pct * 100:.0f}%)", "advance",
                     "Meridian Retail Group", certain=False)
        )
    if plan.financing is not None:
        f = plan.financing
        out.append(Movement(f.draw_day, f.principal, f"Financing draw {f.id}", "financing_draw", f.lender))
        out.append(Movement(f.repay_day, -(f.principal + f.cost()),
                            f"Financing repay {f.id} (principal + {money(f.cost())})",
                            "financing_repay", f.lender))
    return out


def balance_path(opening: Decimal, movements: list[Movement]) -> dict[int, Decimal]:
    """Cumulative signed sum per event day, sorted. Deterministic and exact."""
    by_day: dict[int, Decimal] = {}
    for m in movements:
        by_day[m.day] = by_day.get(m.day, ZERO) + m.amount
    path: dict[int, Decimal] = {}
    running = opening
    for day in sorted(by_day):
        running += by_day[day]
        path[day] = running
    return path


def _run_once(case: Case, plan: Plan, customer_payment_day: int) -> tuple[dict, Decimal]:
    path = balance_path(case.opening_cash, plan_movements(case, plan, customer_payment_day))
    cost = plan.financing.cost() if plan.financing else ZERO
    return path, cost


def simulate(case: Case, plan: Plan, customer_payment_day: int,
             stress_delays: list[int] | None = None) -> SimulationResult:
    """Simulate base scenario plus optional stress scenarios (customer pays late).

    Feasible  = balance >= reserve on every day, base scenario.
    Robust    = feasible in base AND in every stress scenario.
    """
    if stress_delays is None:
        stress_delays = []
    path, cost = _run_once(case, plan, customer_payment_day)

    breach_days = [d for d in sorted(path) if path[d] < case.reserve]
    min_day = min(path, key=lambda d: path[d])
    first_breach = breach_days[0] if breach_days else None

    stress_fail = None
    for delay in stress_delays:
        spath, _ = _run_once(case, plan, customer_payment_day + delay)
        sbreach = [d for d in sorted(spath) if spath[d] < case.reserve]
        if sbreach:
            stress_fail = sbreach[0]
            break

    gross = case.gross_margin if plan.id != "decline" else ZERO
    return SimulationResult(
        plan=plan,
        path=path,
        min_balance=path[min_day],
        min_day=min_day,
        first_breach_day=first_breach,
        breach_days=breach_days,
        financing_cost=cost if plan.id != "decline" else ZERO,
        gross_margin=gross,
        net_margin=gross - cost,
        feasible=first_breach is None,
        robust=stress_fail is None and first_breach is None,
        stress_fail_day=stress_fail,
        depends_on_customer_consent=plan.depends_on_customer_consent,
        depends_on_supplier_consent=plan.depends_on_supplier_consent,
    )


# ------------------------------------------------------------ plan catalogue


def enumerate_plans(case: Case) -> list[Plan]:
    """Small discrete option set, enumerated exhaustively (no solver needed).

    advance x {0%, 25%, 50%}  x  supplier extension {off, on}  x  financing {none, each offer}
    plus Decline. With more offers the enumeration stays exact as long as the
    catalogue stays small; otherwise swap in an integer-programming library --
    the contract (input typed facts, output ranked plans) does not change.
    """
    plans = [Plan("decline", "Decline the order", ZERO, False, None)]
    for pct, ext, offer in product(
        (D("0"), D("0.25"), D("0.50")),
        (False, True),
        (None, *case.financing_offers),
    ):
        if pct == 0 and not ext and offer is None:
            continue  # this is "accept as-is"
        parts = []
        if pct > 0:
            parts.append(f"{pct * 100:.0f}% advance")
        if ext:
            parts.append("supplier extension")
        if offer is not None:
            parts.append(f"financing {offer.id}")
        label = "Accept: " + " + ".join(parts) if parts else "Accept as-is"
        pid = f"adv{int(pct * 100)}_ext{int(ext)}_" + (offer.id if offer else "nofin")
        plans.append(Plan(pid, label, pct, ext, offer))
    plans.append(Plan("accept-as-is", "Accept as-is (no changes)", ZERO, False, None))
    return plans


def rank_plans(results: list[SimulationResult], case: Case,
               priority: str = "maximize_margin") -> list[SimulationResult]:
    """Constrained selection: feasible plans only, then maximise the owner's objective.

    The engine owns feasibility; this function only orders what the engine
    already verified. A priority conflict is flagged, never silently dropped.
    """
    def key(r: SimulationResult):
        penalty = 0
        if priority == "avoid_customer_consent" and r.depends_on_customer_consent:
            penalty = 1
        if priority == "minimize_financing_cost" and r.financing_cost > 0:
            penalty = 1
        if priority == "maximize_margin":
            score = r.net_margin
        elif priority == "minimize_financing_cost":
            score = -r.financing_cost * 1000 + r.net_margin
        else:  # avoid_customer_consent
            score = r.net_margin
        return (penalty, -score, r.financing_cost,
                int(r.depends_on_customer_consent) + int(r.depends_on_supplier_consent),
                r.plan.id)

    feasible = [r for r in results if r.feasible]
    return sorted(feasible, key=key)


# ------------------------------------------------------------- min-change


def minimum_advance(case: Case, customer_payment_day: int, stress_delays: list[int],
                    step_pct: int = 5) -> tuple[Decimal, SimulationResult] | None:
    """Smallest customer advance (as-is otherwise) that is feasible AND robust."""
    pct = D(step_pct) / 100
    while pct <= 1:
        plan = Plan(f"minadv{int(pct * 100)}", f"Accept with {pct * 100:.0f}% advance",
                    pct, False, None)
        r = simulate(case, plan, customer_payment_day, stress_delays)
        if r.robust:
            return pct, r
        pct += D(step_pct) / 100
    return None


def minimum_repay_day(case: Case, offer: FinancingOffer, customer_payment_day: int,
                      stress_delays: list[int]) -> int | None:
    """Eardest repay day (scan forward) at which the offer becomes robust."""
    from dataclasses import replace

    for day in range(offer.repay_day, customer_payment_day + max(stress_delays, default=0) + 30):
        shifted = replace(offer, repay_day=day)
        plan = Plan("shiftprobe", "shift probe", ZERO, False, shifted)
        r = simulate(case, plan, customer_payment_day, stress_delays)
        if r.robust:
            return day
    return None
