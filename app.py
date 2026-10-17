"""OrderFit -- order-affordability decision agent (Streamlit UI).

Run:  streamlit run app.py

Layout: a guided decision flow (verdict -> options -> timeline -> sensitivity
-> approval -> audit log) instead of a tab grid, so the demo reads as one
agent completing stages A-E.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

import agent
import engine
import gemini_client
from case_data import CASE, QUOTE_TEXT, po_text
from sandbox import (ExecutionReport, MockLenderPortal, MockOutbox, OperationLog,
                     PermissionGate, SimulatedBank, execute_plan)

D = Decimal

st.set_page_config(page_title="OrderFit", page_icon="📊", layout="wide")

# ------------------------------------------------------------------ chrome

PRIMARY = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GREEN = "#1baf7a"
RED = "#d64541"
CARD_BG = "#faf9f6"

PLAN_ORDER = ["decline", "accept-as-is", "adv50_ext0_nofin", "adv0_ext1_nofin",
              "adv0_ext0_OFF-1", "adv0_ext1_OFF-2"]
PLAN_COLORS = {"decline": MUTED, "accept-as-is": BLUE, "adv50_ext0_nofin": ORANGE,
               "adv0_ext1_nofin": GREEN, "adv0_ext0_OFF-1": "#eda100",
               "adv0_ext1_OFF-2": "#e87ba4"}
PLAN_ICON = {"decline": "🚫", "accept-as-is": "📥", "adv50_ext0_nofin": "🤝",
             "adv0_ext1_nofin": "📅", "adv0_ext0_OFF-1": "🏦", "adv0_ext1_OFF-2": "🏦"}

PRIORITY_LABELS = {
    "maximize_margin": "Maximize net margin (default)",
    "minimize_financing_cost": "Minimize financing cost",
    "avoid_customer_consent": "Do not depend on customer consent",
}

BADGE = {"LOW": ("🟢", "#e8f7f0", GREEN), "MEDIUM": ("🟠", "#fdf1e7", ORANGE),
         "HIGH": ("🔴", "#fdeaea", RED)}
TIER_COLOR = {"T0": MUTED, "T1": BLUE, "T2": GREEN, "T3": RED}


def fmt(x) -> str:
    return f"{x:,.0f}"


def tier_chip(tier: str) -> str:
    c = TIER_COLOR.get(tier, MUTED)
    return (f'<span style="background:{c};color:#fff;padding:1px 7px;'
            f'border-radius:9px;font-size:11px;font-weight:600">{tier}</span>')


def option_card(icon: str, label: str, *, winner: bool, feasible: bool,
                robust: bool, trough: str, trough_day: int, cost: str,
                margin: str, consent: str, breach: str) -> str:
    border = GREEN if winner else GRID
    head = "★ RECOMMENDED" if winner else ("Decline baseline" if label.startswith("Decline") else "")
    tick = "✅ feasible" if feasible else f"❌ breaches (day {breach})"
    rob = "robust +15d" if robust else f"fails +15d stress (day {breach})" \
        if not feasible else "fails +15d stress"
    return f"""
<div style="border:2px solid {border};border-radius:12px;padding:14px 16px;
     background:{CARD_BG};height:100%;{'box-shadow:0 2px 10px rgba(0,0,0,.08);' if winner else ''}">
  <div style="font-size:11px;color:{GREEN};font-weight:700;letter-spacing:.06em">{head}</div>
  <div style="font-size:16px;font-weight:700;margin:2px 0 8px">{icon} {label}</div>
  <div style="font-size:13px;color:{SECONDARY};line-height:1.7">
    <div>{tick}</div>
    <div>{'🛡️ ' if robust else '⚠️ '}{rob}</div>
    <div>📉 Lowest: <b>{trough}</b> (day {trough_day})</div>
    <div>💰 Cost: <b>{cost}</b> · Net margin: <b>{margin}</b></div>
    <div style="color:{MUTED}">Consent needed: {consent}</div>
  </div>
</div>"""


# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.title("OrderFit")
    st.caption("Should we accept this order — and on what terms?")
    st.divider()

    pay_day = st.slider("Customer payment day", 45, 90, 60, step=1,
                        help="Day the customer's payment for PO-8841 lands.")
    reserve = st.number_input("Minimum cash reserve (USD)", 0, 100_000,
                              int(CASE.reserve), step=500)
    priority = st.selectbox("Owner priority (ranked first)",
                            list(PRIORITY_LABELS), format_func=PRIORITY_LABELS.get)
    with st.expander("Hard constraints"):
        max_fin_cost = st.number_input(
            "Max financing cost (USD)", 0, 50_000, int(CASE.max_financing_cost), step=50,
            help="Any plan whose financing cost exceeds this cap is infeasible.")
        delivery_day = st.slider(
            "Supplier delivery day", 20, 60, CASE.delivery_day,
            help=f"PO requires delivery by day {CASE.required_delivery_day}. "
                 "A later delivery makes every accept plan infeasible.")
    injected = st.checkbox("Inject instruction into the PO (security demo)",
                           help="Adds a prompt-injection line to the purchase order. "
                                "The agent must treat it as data and flag it.")
    st.divider()
    with st.expander("Permission tiers"):
        st.markdown(
            f"{tier_chip('T0')} read — documents, logs  \n"
            f"{tier_chip('T1')} propose — simulate, rank, draft  \n"
            f"{tier_chip('T2')} act — sandbox only, owner-approved  \n"
            f"{tier_chip('T3')} never — hard-blocked in code")
    st.caption(f"🤖 AI: {gemini_client.backend_label()}")
    st.caption("Synthetic data only — no live banks, lenders or email.")

# ------------------------------------------------------------------- state

sig_src = f"{pay_day}|{reserve}|{priority}|{injected}|{max_fin_cost}|{delivery_day}"
sig = hashlib.sha256(sig_src.encode()).hexdigest()[:10]

if st.session_state.get("sig") != sig:
    st.session_state.sig = sig
    st.session_state.log = OperationLog()
    st.session_state.gate = PermissionGate(st.session_state.log)
    st.session_state.bank = SimulatedBank()
    st.session_state.outbox = MockOutbox()
    st.session_state.portal = MockLenderPortal({f.id for f in CASE.financing_offers})
    st.session_state.approvals = {}
    st.session_state.executed: ExecutionReport | None = None

from dataclasses import replace as _replace

case = _replace(CASE, reserve=D(str(reserve)), max_financing_cost=D(str(max_fin_cost)),
                delivery_day=delivery_day)

# owner-confirmed low-confidence fields (ExtractedField.key); survives slider changes
st.session_state.setdefault("confirmed", set())


def _confirm_field(key: str) -> None:
    st.session_state.confirmed.add(key)
    st.session_state.log.append("owner_confirm_field", "T1", {"field": key}, None,
                                f"owner confirmed {key}")


run = agent.run_agent(case, pay_day, priority, injected,
                      confirmed=frozenset(st.session_state.confirmed))
w = run.winner
st.session_state.log.append("run_agent", "T0", {"pay_day": pay_day, "priority": priority},
                            None, f"decision: {w.plan.label}")

# ---- "what changed" banner: compare against the previous scenario's outcome
prev = st.session_state.get("last_outcome")
feas_ids = {r.plan.label for r in run.results.values() if r.feasible}
if prev and prev.get("sig") != sig:
    changes = []
    if prev["winner"] != w.plan.label:
        changes.append(f"Recommendation flipped: **{prev['winner']}** → **{w.plan.label}**")
    lost = prev["feasible"] - feas_ids
    gained = feas_ids - prev["feasible"]
    if lost:
        changes.append(f"now **infeasible**: {', '.join(sorted(lost))}")
    if gained:
        changes.append(f"now **feasible**: {', '.join(sorted(gained))}")
    st.session_state.banner = ("🔄 Scenario changed — " + " · ".join(changes)) if changes else None
else:
    st.session_state.banner = None
st.session_state.last_outcome = {"sig": sig, "winner": w.plan.label, "feasible": feas_ids}

plan_version = hashlib.sha256(
    f"{sig}|{w.plan.id}|{w.min_balance}|{w.net_margin}".encode()).hexdigest()[:10]

# ------------------------------------------------------------------- hero

level, why = agent.uncertainty_rating(run)
icon, tint, accent = BADGE[level]
asis = run.results["accept-as-is"]

if st.session_state.get("banner"):
    st.info(st.session_state.banner, icon="🔄")

st.markdown(f"""
<div style="border-radius:16px;padding:22px 26px;background:{CARD_BG};
     border-left:6px solid {accent};margin-bottom:4px">
  <div style="font-size:12px;color:{MUTED};letter-spacing:.08em;font-weight:700">
    {"PROVISIONAL " if run.provisional else ""}DECISION MEMO — {case.name.upper()}</div>
  <div style="font-size:26px;font-weight:800;margin:6px 0 2px">
    {icon} {w.plan.label}</div>
  <div style="font-size:14px;color:{SECONDARY}">
    Uncertainty <b style="color:{accent}">{level}</b> — {why}</div>
</div>""", unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Lowest balance", f"${fmt(w.min_balance)}", f"day {w.min_day}",
          delta_color="off")
c2.metric("Reserve", f"${fmt(case.reserve)}",
          "met" if w.feasible else "breached", delta_color="off")
c3.metric("Financing cost", f"${fmt(w.financing_cost)}",
          f"net margin ${fmt(w.net_margin)}", delta_color="off")
c4.metric("Accept as-is", "breach" if asis.first_breach_day is not None else "ok",
          f"day {asis.first_breach_day}" if asis.first_breach_day is not None else "no breach",
          delta_color="inverse")
c5.metric("Robust +15d late", "yes" if w.robust else "NO",
          f"fails day {w.stress_fail_day}" if w.stress_fail_day else "stress passed",
          delta_color="inverse")

if run.provisional:
    with st.container(border=True):
        st.warning("**Provisional — waiting for owner confirmation.** The numbers above "
                   "assume the values below. A low-confidence field that changes the "
                   "simulation is never treated as fact; approval stays blocked until "
                   "you confirm it.", icon="⏳")
        for f in run.provisional_fields:
            q1, q2 = st.columns([4, 1])
            q1.markdown(f"**{f.name}:** {f.value} · confidence {f.confidence:.2f} · "
                        f"source {f.source}  \n{f.question or ''}  \n"
                        f"_If the payment date is different, move the "
                        f"**Customer payment day** slider first, then confirm._")
            q2.button("✅ Confirm", key=f"confirm_{f.key}", on_click=_confirm_field,
                      args=(f.key,), use_container_width=True)

# agent chain: stages A-E as progress chips
chips = "  ".join(
    f'<span style="background:{GRID};border-radius:10px;padding:2px 10px;'
    f'font-size:12px;color:{SECONDARY}"><b>Stage {s}</b> — {t}</span>'
    for s, t, _ in run.stage_log)
st.markdown(f"<div style='margin:10px 0 0'>{chips}</div>", unsafe_allow_html=True)
st.divider()

if run.priority_conflict:
    st.error(f"**Priority conflict — escalated.** No feasible plan satisfies "
             f"'{PRIORITY_LABELS[priority]}'. The best feasible plan "
             f"({run.ranked[0].plan.label}) conflicts with it; the agent declines "
             f"rather than recommend a plan that breaks your priority.")

# ------------------------------------------------- section: ask the agent

st.markdown("## 💬 Ask the agent about this decision")
qa1, qa2 = st.columns([4, 1])
with qa1:
    q = st.text_input("ask",
                      value=st.session_state.get("last_q", ""),
                      placeholder="e.g. Why does the 50% advance beat financing? "
                                  "What happens if the customer pays late?",
                      label_visibility="collapsed")
with qa2:
    ask_clicked = st.button("Ask 🔍", type="primary", use_container_width=True)
if ask_clicked and q:
    st.session_state.last_q = q
    st.session_state.last_answer = gemini_client.ask(run, q)
elif ask_clicked and not q:
    st.warning("Type a question first.")

if st.session_state.get("last_answer"):
    a, mode = st.session_state.last_answer
    with st.container(border=True):
        st.markdown(a)
        st.caption(f"source: {mode} · answered strictly from the engine's memo JSON — "
                   f"the model never computes numbers")
elif not st.session_state.get("last_answer"):
    if not gemini_client.gemini_available():
        st.caption("ℹ️ Gemini is not configured — set GOOGLE_GENAI_USE_VERTEXAI=true "
                   "(Vertex AI) or GOOGLE_API_KEY to enable Q&A. The deterministic "
                   "memo below is complete without it.")
    else:
        st.caption("Answers are grounded strictly in the engine's memo JSON — "
                   "if a fact is not in the data, the agent says so.")

# ------------------------------------------------------ section: the problem

st.markdown("## 1 · Is the order safe as-is?")
d1, d2 = st.columns([3, 2])
with d1:
    if asis.first_breach_day is not None:
        st.markdown(
            f"Accepting as-is first breaches the **${fmt(case.reserve)}** reserve on "
            f"**day {asis.first_breach_day}** and bottoms out at "
            f"**${fmt(asis.min_balance)} on day {asis.min_day}** — a profitable order "
            f"(${fmt(case.gross_margin)} gross margin) that cannot be funded on the "
            f"current payment terms.")
    else:
        st.markdown(
            f"Accepting as-is keeps cash at or above the **${fmt(case.reserve)}** "
            f"reserve on every day (lowest **${fmt(asis.min_balance)} on day "
            f"{asis.min_day}**).")
    if asis.violations:
        st.error("**Hard constraint violated:** " + " ".join(asis.violations))
with d2:
    alert_title = {"reserve_breach": "Reserve breach",
                   "payment_before_receipt": "Payment before receipt",
                   "offer_expiry": "Offer expiry", "fragile_plan": "Fragile plan",
                   "constraint_violation": "Hard constraint",
                   "overdue_receivable": "Overdue receivable"}
    for a in sorted(run.alerts, key=lambda a: {"critical": 0, "warning": 1}.get(a.severity, 2)):
        show = {"critical": st.error, "warning": st.warning}.get(a.severity, st.info)
        show(f"🔔 **{alert_title.get(a.rule, a.rule)}** — {a.message}")

# ------------------------------------------------------ section: the options

st.markdown("## 2 · The options it compared")
winners = [r for r in run.ranked[:4]]
cards = [
    option_card(
        PLAN_ICON.get(r.plan.id, "📋"), r.plan.label,
        winner=r.plan.id == w.plan.id, feasible=r.feasible, robust=r.robust,
        trough=f"${fmt(r.min_balance)}", trough_day=r.min_day,
        cost=f"${fmt(r.financing_cost)}", margin=f"${fmt(r.net_margin)}",
        consent=", ".join(filter(None, [
            "customer" if r.depends_on_customer_consent else "",
            "supplier" if r.depends_on_supplier_consent else ""])) or "none",
        breach=str(r.first_breach_day or r.stress_fail_day or "—"))
    for r in winners]
cols = st.columns(min(4, len(cards)))
for col, card_html in zip(cols, cards):
    col.markdown(card_html, unsafe_allow_html=True)
rest = [r for r in run.ranked[4:8]]
if rest:
    with st.expander(f"{len(rest)} more feasible plans"):
        st.dataframe(pd.DataFrame([{
            "Plan": r.plan.label, "Lowest balance": float(r.min_balance),
            "Fin. cost": float(r.financing_cost),
            "Net margin": float(r.net_margin),
            "Robust": "yes" if r.robust else "no"} for r in rest]),
            hide_index=True, width="stretch")
excluded = [r for r in run.results.values() if r.violations]
if excluded:
    with st.expander(f"⛔ {len(excluded)} plans excluded by hard constraints"):
        st.dataframe(pd.DataFrame([{
            "Plan": r.plan.label, "Violation": " ".join(r.violations),
            "Fin. cost": float(r.financing_cost),
            "Reserve met": "yes" if r.reserve_ok else f"no (day {r.first_breach_day})",
        } for r in excluded]), hide_index=True, width="stretch")
st.caption("Every number is computed by the deterministic engine; the decision "
           "layer only ranks what the engine verified.")

# ------------------------------------------------------ section: the timeline

st.markdown("## 3 · Dated cash timeline")
show_ids = [p for p in PLAN_ORDER if p in run.results]
records = []
for pid in show_ids:
    r = run.results[pid]
    seq = 0
    for d, b in r.path.items():
        # same-day rule: draw the intra-day low first, then the end-of-day balance
        low = r.low_path.get(d, b)
        for bal in ((low, b) if low != b else (b,)):
            records.append({"day": d, "balance": float(bal), "plan": r.plan.label,
                            "seq": seq})
            seq += 1
df = pd.DataFrame(records)
labels = [run.results[p].plan.label for p in show_ids]
colors = [PLAN_COLORS[p] for p in show_ids]

# red shading: the as-is path below the reserve (the affordability gap)
asis_rows = df[df["plan"] == asis.plan.label].copy()
asis_rows["capped"] = asis_rows["balance"].clip(upper=float(case.reserve))
gap = alt.Chart(asis_rows).mark_area(color=RED, opacity=0.22).encode(
    x="day:Q", y=alt.Y("capped:Q", title=None), y2=alt.datum(float(case.reserve)))

lines = alt.Chart(df).mark_line(strokeWidth=2).encode(
    x=alt.X("day:Q", title="Day"),
    y=alt.Y("balance:Q", title="Cash balance (USD)", axis=alt.Axis(format="$,.0f")),
    order="seq:Q",
    color=alt.Color("plan:N", sort=labels, title=None,
                    scale=alt.Scale(domain=labels, range=colors),
                    legend=alt.Legend(orient="top", direction="horizontal")),
    tooltip=[alt.Tooltip("plan:N", title="Option"),
             alt.Tooltip("day:Q", title="Day"),
             alt.Tooltip("balance:Q", title="Balance", format="$,.0f")],
).properties(height=380)

marks = []
if asis.first_breach_day is not None:
    marks.append(alt.Chart(pd.DataFrame([{
        "day": asis.first_breach_day, "balance": float(asis.low_path[asis.first_breach_day]),
        "label": f"first breach · day {asis.first_breach_day}"}])).mark_circle(
        size=130, color=RED).encode(x="day:Q", y="balance:Q"))
    marks.append(alt.Chart(pd.DataFrame([{
        "day": asis.first_breach_day, "balance": float(asis.low_path[asis.first_breach_day]),
        "label": f"first breach · day {asis.first_breach_day}"}])).mark_text(
        dy=-12, color=RED, fontSize=11, fontWeight="bold").encode(
        x="day:Q", y="balance:Q", text="label:N"))
marks.append(alt.Chart(pd.DataFrame([{
    "day": w.min_day, "balance": float(w.min_balance),
    "label": f"winner low · day {w.min_day}"}])).mark_circle(
    size=130, color=GREEN).encode(x="day:Q", y="balance:Q"))

reserve_df = pd.DataFrame({"reserve": [float(case.reserve)]})
rule = alt.Chart(reserve_df).mark_rule(strokeDash=[5, 4], color=SECONDARY).encode(
    y=alt.Y("reserve:Q", axis=alt.Axis(format="$,.0f")))

chart = lines + rule + gap + alt.layer(*marks) if marks else lines + rule + gap
st.altair_chart(chart.configure_axis(
    gridColor=GRID, labelColor=MUTED, titleColor=SECONDARY,
    domainColor=GRID).configure_legend(labelColor=SECONDARY, titleColor=SECONDARY),
    width="stretch")
st.caption(f"Red shading = the affordability gap: the as-is balance below the "
           f"reserve. Dashed line = minimum reserve. Vertical drops = same-day "
           f"outflows applied before inflows. 🟢 = recommended plan's "
           f"low point (day {w.min_day}).")

# -------------------------------------------------- section: sensitivity

st.markdown("## 4 · Sensitivity — when does the answer change?")
s1, s2 = st.columns([2, 3])
with s1:
    st.markdown(f"First flip as the customer payment day moves: "
                f"{'**day ' + str(run.flip_day) + '**' if run.flip_day else 'no flip between days 40–90'}.")
    if run.questions:
        st.markdown("**❓ Missing / low-confidence information**")
        for q in run.questions:
            st.markdown(f"- {q}")
    if run.min_advance and w.plan.advance_pct == 0:
        st.info(f"**Smallest workable advance:** {run.min_advance[0] * 100:.0f}% "
                f"(${fmt(case.order_value * run.min_advance[0])}) makes accept "
                f"feasible *and* robust to the 15-day delay.")
    if w.plan.financing is not None and w.stress_fail_day is not None:
        shift = engine.minimum_repay_day(case, w.plan.financing, pay_day, agent.STRESS_DELAYS)
        if shift:
            st.info(f"**Smallest financing change that works:** move repay from "
                    f"day {w.plan.financing.repay_day} to **day {shift}**.")
with s2:
    sens_days = [d for d, _ in run.sensitivity]
    sens_wide = pd.DataFrame([[lbl for _, lbl in run.sensitivity]], columns=sens_days)
    st.dataframe(sens_wide, width="stretch", height=60)
    st.caption("Winning plan for each customer payment day (40–90), current priority.")

st.markdown("#### Assumptions")
st.markdown(f"""
- Customer pays the full \\${fmt(case.order_value)} on **day {pay_day}** (stress: +15 days).
- Supplier deposit and pre-delivery payment are deferrable to day 40 **only if** the
  supplier agrees; an advance happens **only if** the customer agrees.
- Obligations after day 45 (next payroll cycle) are not modelled.
- Financing terms come only from the supplied catalogue; the agent cannot invent terms.
""")

# -------------------------------------------------- section: documents

with st.expander("📄 Documents, extraction & injection defence (stage A)"):
    if run.extraction_mode == "gemini":
        st.success(f"🤖 **Extracted by {gemini_client.backend_label()}** as typed JSON. "
                   f"{run.extraction_note}")
    else:
        st.info(f"⚙️ **Deterministic regex extraction.** {run.extraction_note}")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Purchase order PO-8841**")
        st.text(po_text(injected))
    with col2:
        st.markdown("**Supplier quotation Q-3312**")
        st.text(QUOTE_TEXT)

    if run.injections:
        for f in run.injections:
            st.error(f"⚠️ **Injection attempt flagged in {f.document}** — matched: "
                     f"\"{f.span}\". Documents are data: the instruction was ignored, "
                     f"logged, and the verdict is unchanged.")
    else:
        st.success("No injection attempts detected in the documents.")

    st.markdown("#### Extracted fields (typed, source-linked)")
    st.dataframe(pd.DataFrame([{
        "Field": f.name, "Value": f.value, "Source": f.source,
        "Confidence": f.confidence, "Source span": f.span,
        "Owner question": f.question or "",
    } for f in run.fields]), hide_index=True, width="stretch")

    st.markdown("#### Cash position & obligations (structured case data, owner-confirmed)")
    st.dataframe(pd.DataFrame([{
        "Day": m.day, "Amount": float(m.amount), "Item": m.label,
        "Counterparty": m.counterparty, "Certain": m.certain,
    } for m in sorted(case.base_movements + case.order_costs, key=lambda m: m.day)]),
        hide_index=True, width="stretch")

# -------------------------------------------------- section: draft + gemini

with st.expander("✍️ Draft counterparty message"):
    st.text_area("draft", run.draft_message, height=170, label_visibility="collapsed")
    if st.button("✨ Polish draft with Gemini (numbers verified by the engine)"):
        polished, pmode, pnote = gemini_client.polish_draft(run)
        st.text_area("polished", polished, height=190, label_visibility="collapsed")
        (st.success if pmode == "gemini" else st.warning)(f"source: {pmode} · {pnote}")
    if st.button("Generate plain-language explanation (Gemini, optional)"):
        text, mode = gemini_client.explain_memo(run)
        st.markdown(text)
        st.caption(f"source: {mode}")

# -------------------------------------------------- section: approval & execution

st.markdown("## 5 · Owner approval & sandbox execution")
st.markdown("T2 actions run in the sandbox **only** after owner approval bound to "
            "this exact plan version. Changing any slider invalidates approvals.")
st.code(f"plan_version: {plan_version}\nplan: {w.plan.label}", language=None)

a1, a2 = st.columns(2)
if a1.button("✅ Owner approves this plan version", type="primary",
             disabled=w.plan.id == "decline" or run.provisional,
             help="Decline needs no execution approval. Provisional results must be "
                  "confirmed before approval."):
    approval_id = f"APP-{hashlib.sha256(plan_version.encode()).hexdigest()[:6].upper()}"
    st.session_state.approvals[plan_version] = approval_id
    st.session_state.log.append("request_approval", "T1",
                                {"plan_version": plan_version}, None,
                                f"approved by owner as {approval_id}")
if a2.button("✍️ Approve with explicit reserve override", disabled=run.provisional):
    approval_id = f"APP-{hashlib.sha256(plan_version.encode()).hexdigest()[:6].upper()}-OVR"
    st.session_state.approvals[plan_version] = approval_id
    st.session_state.log.append("request_approval", "T1",
                                {"plan_version": plan_version, "override": True},
                                None, f"approved with override as {approval_id}")

approval_id = st.session_state.approvals.get(plan_version)
if approval_id:
    st.success(f"Approved as `{approval_id}` (bound to plan version {plan_version}).")
    st.markdown(f"**Will execute:** outbox message → "
                + (f"lender portal ({w.plan.financing.id}) → " if w.plan.financing else "")
                + "simulated bank ledger, each gated and logged.")
    if st.button("▶️ Execute approved plan in sandbox"):
        st.session_state.executed = execute_plan(
            run, st.session_state.approvals, approval_id,
            st.session_state.log, st.session_state.gate,
            st.session_state.bank, st.session_state.outbox, st.session_state.portal)
else:
    st.info("Not approved yet — execution is blocked until the owner approves "
            "this plan version.")

ex = st.session_state.get("executed")
if ex:
    st.markdown("#### Execution report")
    for s in ex.steps:
        st.markdown(f"- {s}")
    if ex.consistency:
        st.markdown(f"- Consistency check: **{ex.consistency}**")

    if st.session_state.bank.booked:
        with st.expander("Simulated bank ledger"):
            st.dataframe(pd.DataFrame(st.session_state.bank.booked),
                         hide_index=True, width="stretch")
    if st.session_state.outbox.sent:
        with st.expander("Mock outbox (nothing is delivered)"):
            for m in st.session_state.outbox.sent:
                st.markdown(f"**To:** {m['to']} — *{m['status']}*  \n```\n{m['body']}\n```")
    if st.session_state.portal.accepted:
        with st.expander("Mock lender portal"):
            st.json(st.session_state.portal.accepted)

st.markdown("#### T3 attempts — hard-blocked in code")
b1, b2, b3 = st.columns(3)
if b1.button("Attempt: send real email"):
    st.session_state.gate.block_t3("smtp.send", {"to": "real@customer.com"},
                                   "T3: no real email capability exists; blocked in code")
    st.error("BLOCKED — attempt logged.")
if b2.button("Attempt: live bank transfer"):
    st.session_state.gate.block_t3("bank.live_transfer", {"iban": "DE89..."},
                                   "T3: no live bank integration exists; blocked in code")
    st.error("BLOCKED — attempt logged.")
if b3.button("Attempt: invent loan terms"):
    st.session_state.gate.block_t3("lender.create_terms",
                                   {"principal": 999999, "fee_pct": 0},
                                   "T3: financing terms may only come from the catalogue")
    st.error("BLOCKED — attempt logged.")

# -------------------------------------------------- section: operation log

st.markdown("## 🛡️ Operation log")
st.markdown("Every tool call: time, tool, tier, hash of inputs, approval ID, result.")
entries = st.session_state.log.as_dicts()
if entries:
    lines = []
    for e in entries:
        blocked = ' <span style="color:%s;font-weight:700">⛔ %s</span>' % (
            RED, e["blocked_reason"]) if e["blocked_reason"] else ""
        lines.append(
            f'{tier_chip(e["tier"])} `{e["time"]}` **{e["tool"]}** — '
            f'{e["result"]} · in:`{e["input_hash"]}`'
            + (f' · approval:`{e["approval_id"]}`' if e["approval_id"] else "")
            + blocked)
    st.markdown("<div style='line-height:2.1;font-size:13px'>" + "<br>".join(lines)
                + "</div>", unsafe_allow_html=True)
blocked_n = sum(1 for e in entries if e["result"] == "BLOCKED")
cexp1, cexp2 = st.columns(2)
cexp1.download_button("⬇️ Export operation log (JSON — evidence item 6)",
                      json.dumps(entries, indent=1),
                      file_name="orderfit_operation_log.json", mime="application/json")
st.caption(f"{len(entries)} entries · {blocked_n} blocked attempts · "
           f"export this log as submission evidence item 6.")
