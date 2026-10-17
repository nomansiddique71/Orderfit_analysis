"""OrderFit deterministic financial engine.

Every number shown in the app is computed here with Decimal arithmetic.
The decision layer may *propose*; only this module *verifies* hard
constraints (minimum reserve on every day, delivery date, financing cap).
The model layer can never perform arithmetic or mark an infeasible plan
as feasible -- it only consumes SimulationResult objects from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    due_day: int | None = None  # contractual due day (receivables); < 0 = already overdue today
    tied_to_delivery: bool = False  # moves with the delivery date (e.g. paid on delivery)


@dataclass(frozen=True)
class FinancingOffer:
    """A lender's term sheet. Terms only ever come from a catalogue -- never invented.

    Cost = flat fee (% of principal) + origination + simple monthly interest,
    pro-rated by days drawn / 30 (e.g. 1.5% per month over 60 days = 3%).
    min/max_principal bound what the lender will lend; an offer whose
    principal falls outside them is ineligible (L-02) and never shown as an option.
    """

    id: str
    lender: str
    principal: Decimal
    fee_pct: Decimal  # flat fee, % of principal
    origination: Decimal
    draw_day: int
    repay_day: int
    expires_day: int
    conditions: str = ""
    monthly_rate_pct: Decimal = D("0")  # simple interest per 30 days drawn
    min_principal: Decimal | None = None
    max_principal: Decimal | None = None
    principal_step: Decimal = D("500")  # granularity when sizing a loan

    def cost(self) -> Decimal:
        months = D(self.repay_day - self.draw_day) / D(30)
        interest = self.principal * self.monthly_rate_pct / D(100) * months
        return money(self.principal * self.fee_pct / D(100) + self.origination + interest)

    @property
    def sizeable(self) -> bool:
        """True if the lender quotes a principal range we can size a loan within."""
        return self.min_principal is not None and self.max_principal is not None

    def ineligibility(self) -> str | None:
        """Reason this offer cannot be used as quoted, or None if it is eligible."""
        if self.min_principal is not None and self.principal < self.min_principal:
            return (f"principal {self.principal:,.0f} is below {self.lender}'s minimum "
                    f"{self.min_principal:,.0f}")
        if self.max_principal is not None and self.principal > self.max_principal:
            return (f"principal {self.principal:,.0f} is above {self.lender}'s maximum "
                    f"{self.max_principal:,.0f}")
        return None

    def with_principal(self, principal: Decimal) -> "FinancingOffer":
        from dataclasses import replace

        return replace(self, principal=principal)

    def terms_text(self) -> str:
        parts = []
        if self.fee_pct:
            parts.append(f"{self.fee_pct}% flat fee")
        if self.monthly_rate_pct:
            parts.append(f"{self.monthly_rate_pct}% per month")
        if self.origination:
            parts.append(f"{self.origination:,.0f} fee")
        return " + ".join(parts) or "no cost"


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
    path: dict[int, Decimal]  # day -> end-of-day balance (only event days)
    min_balance: Decimal
    min_day: int
    first_breach_day: int | None  # first day balance < reserve
    breach_days: list[int]
    financing_cost: Decimal
    gross_margin: Decimal  # order value - order costs (0 for decline)
    net_margin: Decimal  # gross margin - financing cost
    feasible: bool  # no reserve breach in the base scenario AND no hard-constraint violation
    robust: bool  # no breach in base AND every stress scenario
    stress_fail_day: int | None  # first breach day under stress, if any
    depends_on_customer_consent: bool
    depends_on_supplier_consent: bool
    # day -> lowest balance within the day (outflows applied before inflows).
    # Breaches and min_balance are measured on this, not on end-of-day.
    low_path: dict[int, Decimal] = field(default_factory=dict)
    # hard constraints other than the reserve (delivery date, financing-cost cap)
    violations: list[str] = field(default_factory=list)
    tolerance: "Tolerance | None" = None  # filled in by the agent (delay_tolerance)

    @property
    def reserve_ok(self) -> bool:
        return self.first_breach_day is None


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
    supplier: str = ""  # counterparty whose prices a price-increase scenario changes
    late_penalty_pct_per_week: Decimal = D("0")  # from the PO: % of order value per week late

    @property
    def gross_margin(self) -> Decimal:
        return self.order_value - sum((-m.amount for m in self.order_costs), ZERO)


@dataclass(frozen=True)
class Scenario:
    """A what-if applied on top of a plan. Default = everything as expected."""

    key: str = "base"
    label: str = "As expected"
    customer_pays: bool = True
    payment_fraction: Decimal = D("1")  # share of the balance the customer actually pays
    supplier_price_increase_pct: Decimal = D("0")  # applies to case.supplier's costs
    supplier_delay_days: int = 0  # delivery (and delivery-tied costs + payment) slips


BASE = Scenario()


def scenario_case(case: Case, sc: Scenario) -> Case:
    """Cost-side effects of a scenario: supplier prices and the delivery date."""
    from dataclasses import replace

    if sc.supplier_price_increase_pct == 0 and sc.supplier_delay_days == 0:
        return case
    costs = []
    for m in case.order_costs:
        amount, day = m.amount, m.day
        if sc.supplier_price_increase_pct and m.counterparty == case.supplier:
            amount = money(amount * (1 + sc.supplier_price_increase_pct / D(100)))
        if m.tied_to_delivery:
            day += sc.supplier_delay_days
        costs.append(replace(m, amount=amount, day=day))
    return replace(case, order_costs=tuple(costs),
                   delivery_day=case.delivery_day + sc.supplier_delay_days)


def late_delivery_penalty(case: Case, delay_days: int) -> Decimal:
    """PO penalty for late delivery; a started week counts as a full week."""
    if delay_days <= 0:
        return ZERO
    weeks = -(-delay_days // 7)  # ceiling division
    return money(case.order_value * case.late_penalty_pct_per_week / D(100) * weeks)


# ---------------------------------------------------------------- simulation


def overdue_receivables(case: Case) -> list[Movement]:
    """Receivables whose due day has passed (day 0 is today) but are still expected."""
    return [m for m in case.base_movements
            if m.amount > 0 and m.due_day is not None and m.due_day < 0]


def without_movement(case: Case, movement: Movement) -> Case:
    """The same case with one existing movement removed (e.g. a receivable never paid)."""
    from dataclasses import replace

    return replace(case, base_movements=tuple(m for m in case.base_movements
                                              if m is not movement))


def constraint_violations(case: Case, plan: Plan) -> list[str]:
    """Hard constraints besides the reserve. Decline commits to nothing."""
    if plan.id == "decline":
        return []
    out: list[str] = []
    if case.delivery_day > case.required_delivery_day:
        out.append(f"Delivery on day {case.delivery_day} misses the required day "
                   f"{case.required_delivery_day}.")
    if plan.financing is not None and plan.financing.cost() > case.max_financing_cost:
        out.append(f"Financing cost {plan.financing.cost():,.0f} exceeds the cap of "
                   f"{case.max_financing_cost:,.0f}.")
    return out


def plan_movements(case: Case, plan: Plan, customer_payment_day: int | None,
                   scenario: Scenario = BASE) -> list[Movement]:
    """All dated movements for a plan under one customer-payment scenario.

    customer_payment_day=None models a customer who never pays the balance.
    scenario adds payment-side what-ifs (partial payment, late-delivery
    penalty, payment slipping with delivery); cost-side effects come from
    scenario_case().
    """
    case = scenario_case(case, scenario)
    if not scenario.customer_pays:
        customer_payment_day = None
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
    # The advance is part of the order value, not extra money: the customer's
    # final payment is the order value minus whatever was paid up front.
    advance = money(case.order_value * plan.advance_pct)
    if customer_payment_day is not None:
        due = case.order_value - advance
        if scenario.payment_fraction != 1:
            due = money(due * scenario.payment_fraction)
        due -= late_delivery_penalty(case, scenario.supplier_delay_days)
        out.append(Movement(customer_payment_day + scenario.supplier_delay_days, max(due, ZERO),
                 "Customer payment (PO-8841)" + (" -- balance after advance" if advance else ""),
                 "order_revenue", "Meridian Retail Group"))
    if advance > 0:
        out.append(
            Movement(0, advance,
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
    return daily_balances(opening, movements)[1]


def daily_balances(opening: Decimal, movements: list[Movement]
                   ) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
    """Return (low_path, end_path) per event day.

    Same-day rule (M-10): on a day with both inflows and outflows, outflows are
    applied first, so the intra-day low is end-of-previous-day + that day's
    outflows. This is the conservative reading -- a payment due in the morning
    cannot be funded by a receipt that might clear in the afternoon -- and it
    keeps the path deterministic (no dependency on input order).
    """
    outs: dict[int, Decimal] = {}
    ins: dict[int, Decimal] = {}
    for m in movements:
        bucket = outs if m.amount < 0 else ins
        bucket[m.day] = bucket.get(m.day, ZERO) + m.amount
    low: dict[int, Decimal] = {}
    end: dict[int, Decimal] = {}
    running = opening
    for day in sorted(set(outs) | set(ins)):
        running += outs.get(day, ZERO)
        low[day] = running
        running += ins.get(day, ZERO)
        end[day] = running
    return low, end


def _run_once(case: Case, plan: Plan, customer_payment_day: int
              ) -> tuple[dict, dict, Decimal]:
    low, end = daily_balances(case.opening_cash,
                              plan_movements(case, plan, customer_payment_day))
    cost = plan.financing.cost() if plan.financing else ZERO
    return low, end, cost


def simulate(case: Case, plan: Plan, customer_payment_day: int,
             stress_delays: list[int] | None = None) -> SimulationResult:
    """Simulate base scenario plus optional stress scenarios (customer pays late).

    Feasible  = intra-day balance >= reserve on every day, base scenario.
    Robust    = feasible in base AND in every stress scenario.
    """
    if stress_delays is None:
        stress_delays = []
    low, path, cost = _run_once(case, plan, customer_payment_day)

    breach_days = [d for d in sorted(low) if low[d] < case.reserve]
    min_day = min(low, key=lambda d: low[d])  # earliest day on ties
    first_breach = breach_days[0] if breach_days else None

    stress_fail = None
    for delay in stress_delays:
        slow, _, _ = _run_once(case, plan, customer_payment_day + delay)
        sbreach = [d for d in sorted(slow) if slow[d] < case.reserve]
        if sbreach:
            stress_fail = sbreach[0]
            break

    violations = constraint_violations(case, plan)
    feasible = first_breach is None and not violations
    gross = case.gross_margin if plan.id != "decline" else ZERO
    return SimulationResult(
        plan=plan,
        path=path,
        min_balance=low[min_day],
        min_day=min_day,
        first_breach_day=first_breach,
        breach_days=breach_days,
        financing_cost=cost if plan.id != "decline" else ZERO,
        gross_margin=gross,
        net_margin=gross - cost,
        feasible=feasible,
        robust=stress_fail is None and feasible,
        stress_fail_day=stress_fail,
        depends_on_customer_consent=plan.depends_on_customer_consent,
        depends_on_supplier_consent=plan.depends_on_supplier_consent,
        low_path=low,
        violations=violations,
    )


# ------------------------------------------------------------- scenarios

ORDER_KINDS = {"order_cost", "order_revenue", "advance", "financing_draw", "financing_repay"}


@dataclass
class ScenarioOutcome:
    scenario: Scenario
    min_balance: Decimal
    min_day: int
    first_breach_day: int | None
    order_net: Decimal  # all order-related cash in - out (incl. financing), whole horizon
    violations: list[str]
    penalty: Decimal

    @property
    def reserve_ok(self) -> bool:
        return self.first_breach_day is None


def evaluate_scenario(case: Case, plan: Plan, customer_payment_day: int,
                      sc: Scenario) -> ScenarioOutcome:
    movs = plan_movements(case, plan, customer_payment_day, sc)
    low, _ = daily_balances(case.opening_cash, movs)
    breach = [d for d in sorted(low) if low[d] < case.reserve]
    min_day = min(low, key=lambda d: low[d])
    return ScenarioOutcome(
        scenario=sc, min_balance=low[min_day], min_day=min_day,
        first_breach_day=breach[0] if breach else None,
        order_net=sum((m.amount for m in movs if m.kind in ORDER_KINDS), ZERO),
        violations=constraint_violations(scenario_case(case, sc), plan),
        penalty=(late_delivery_penalty(case, sc.supplier_delay_days)
                 if plan.id != "decline" and sc.customer_pays else ZERO),
    )


def money_at_risk(case: Case, plan: Plan) -> list[tuple[int, Decimal]]:
    """If the customer cancels right after day d: order money already spent and
    not covered by the advance (assumes supplier payments made are not refunded
    and the advance is kept). One row per day an order cost is paid."""
    if plan.id == "decline":
        return []
    movs = plan_movements(case, plan, None)
    advance = sum((m.amount for m in movs if m.kind == "advance"), ZERO)
    out, spent = [], ZERO
    for day in sorted({m.day for m in movs if m.kind == "order_cost"}):
        spent += sum((-m.amount for m in movs if m.kind == "order_cost" and m.day == day), ZERO)
        out.append((day, max(spent - advance, ZERO)))
    return out


# --------------------------------------------------------- delay tolerance


@dataclass(frozen=True)
class Tolerance:
    """How many days late the customer can pay before the plan breaks.

    kind: "never_pays_safe" (X-01) -- holds even if the balance never arrives;
          "fails_on_time"  (X-02) -- breaks even if the customer pays on time;
          "days"                  -- holds for up to `days` days late.
    """

    kind: str
    days: int | None = None
    last_safe_pay_day: int | None = None

    @property
    def rank_value(self) -> int:
        """Bigger = more robust. Used for sorting only."""
        if self.kind == "never_pays_safe":
            return 10**6
        if self.kind == "fails_on_time":
            return -1
        return self.days

    def survives(self, delay: int) -> bool:
        return self.rank_value >= delay

    @property
    def label(self) -> str:
        if self.kind == "never_pays_safe":
            return "safe even if the customer never pays"
        if self.kind == "fails_on_time":
            return "fails even if paid on time"
        return f"{self.days} day(s) late (pay by day {self.last_safe_pay_day})"


def feasible_at(case: Case, plan: Plan, customer_payment_day: int | None) -> bool:
    """Reserve met on every day (intra-day) and no hard-constraint violation."""
    if constraint_violations(case, plan):
        return False
    low, _ = daily_balances(case.opening_cash,
                            plan_movements(case, plan, customer_payment_day))
    return all(b >= case.reserve for b in low.values())


def delay_tolerance(case: Case, plan: Plan, customer_payment_day: int) -> Tolerance:
    """Largest payment delay (days) that still keeps the reserve.

    Paying later can only lower (never raise) the balance on any day, so
    feasibility is monotone in the delay and a binary search is exact.
    """
    if not feasible_at(case, plan, customer_payment_day):
        return Tolerance("fails_on_time")
    if plan.id == "decline" or feasible_at(case, plan, None):
        return Tolerance("never_pays_safe")
    # Paying on or after the last event day is the same as never paying
    # (outflows come first that day), which we know fails.
    last = max(m.day for m in plan_movements(case, plan, None))
    lo, hi = 0, last - customer_payment_day  # feasible(lo) is True, feasible(hi) is False
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if feasible_at(case, plan, customer_payment_day + mid):
            lo = mid
        else:
            hi = mid
    return Tolerance("days", lo, customer_payment_day + lo)


# ------------------------------------------------------------ plan catalogue


def eligible_offers(case: Case) -> list[FinancingOffer]:
    return [o for o in case.financing_offers if o.ineligibility() is None]


def ineligible_offers(case: Case) -> list[tuple[FinancingOffer, str]]:
    return [(o, o.ineligibility()) for o in case.financing_offers
            if o.ineligibility() is not None]


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
        (None, *eligible_offers(case)),
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

    priority "most_robust": order by late-payment tolerance, then financing
    cost. Decline trivially tolerates anything, so it is ranked last whenever
    at least one accept plan survives the chosen stress (r.robust), and first
    only when none does. Requires r.tolerance to be filled in.
    """
    consents = lambda r: (int(r.depends_on_customer_consent)  # noqa: E731
                          + int(r.depends_on_supplier_consent))
    feasible = [r for r in results if r.feasible]

    if priority == "most_robust":
        def rkey(r: SimulationResult):
            tol = r.tolerance.rank_value if r.tolerance else -1
            return (-tol, r.financing_cost, consents(r), r.plan.advance_pct,
                    -r.net_margin, r.plan.id)
        accept = sorted((r for r in feasible if r.plan.id != "decline"), key=rkey)
        decline = [r for r in feasible if r.plan.id == "decline"]
        return accept + decline if any(r.robust for r in accept) else decline + accept

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
        return (penalty, -score, r.financing_cost, consents(r), r.plan.id)

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


def minimum_safe_loan(case: Case, offer: FinancingOffer, customer_payment_day: int,
                      stress_delay: int, advance_pct: Decimal = ZERO,
                      supplier_extension: bool = False
                      ) -> tuple[Decimal, SimulationResult] | None:
    """Smallest principal, within the lender's own limits and step, that keeps the
    reserve on time AND when the customer pays `stress_delay` days late (R-08).

    Only the principal changes; rate, fees and dates stay exactly as quoted.
    Returns None if no allowed principal works (or the offer is not sizeable).
    """
    if not offer.sizeable:
        return None
    principal = offer.min_principal
    while principal <= offer.max_principal:
        sized = offer.with_principal(principal)
        plan = Plan(f"minloan_{offer.id}" + (f"_adv{int(advance_pct * 100)}" if advance_pct else ""),
                    f"Accept: {offer.lender} loan of {principal:,.0f} (minimum safe)"
                    + (f" + {advance_pct * 100:.0f}% advance" if advance_pct else ""),
                    advance_pct, supplier_extension, sized)
        r = simulate(case, plan, customer_payment_day, [stress_delay])
        if r.robust:
            return principal, r
        principal += offer.principal_step
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
