"""Smoke test: the Streamlit page renders end to end without exceptions (offline)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


def test_app_renders_offline():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception


def test_app_renders_with_late_delivery():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    next(s for s in at.slider if s.label == "Supplier delivery day").set_value(35).run()
    assert not at.exception, at.exception
    assert any("excluded by hard constraints" in e.label for e in at.expander)


def test_confirm_clears_provisional_banner():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert any("Provisional" in w.value for w in at.warning)
    next(b for b in at.button if b.label == "✅ Confirm").click().run()
    assert not at.exception, at.exception
    assert not any("Provisional" in w.value for w in at.warning)


def test_near_tie_choice_in_app():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    next(n for n in at.number_input if n.label == "Minimum cash reserve (USD)").set_value(5000)
    next(s for s in at.selectbox if s.label == "Owner priority (ranked first)").set_value(
        "avoid_customer_consent")
    at.run()
    assert any("Near tie" in w.value for w in at.warning)
    at.button(key="tie_minloan_OFF-3").click().run()
    assert not at.exception, at.exception
    assert any("resolved by you" in s.value for s in at.success)


def _confirmed_app():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    next(b for b in at.button if b.label == "✅ Confirm").click().run()
    return at


def test_approve_and_execute_in_app():
    at = _confirmed_app()
    next(b for b in at.button if b.label == "✅ Owner approves this plan version").click().run()
    next(b for b in at.button if b.label == "▶️ Execute approved plan in sandbox").click().run()
    assert not at.exception, at.exception
    assert any("passed" in m.value for m in at.markdown if "Consistency check" in m.value)


def test_reserve_override_flow_in_app():
    at = _confirmed_app()
    sel = next(s for s in at.selectbox if s.label.startswith("Plan to approve despite"))
    sel.select_index(next(i for i, o in enumerate(sel.options)
                          if o.startswith("Accept as-is"))).run()
    next(t for t in at.text_input if t.label.startswith("Reason")).input("owner funds gap").run()
    next(c for c in at.checkbox if c.label.startswith("I understand")).check().run()
    next(b for b in at.button if b.label == "Approve with reserve override").click().run()
    assert not at.exception, at.exception
    assert any("[RESERVE OVERRIDE]" in e.value for e in at.error)
    next(b for b in at.button if b.label == "▶️ Execute approved plan in sandbox").click().run()
    assert not at.exception, at.exception
    assert any("Execution report — [RESERVE OVERRIDE]" in m.value for m in at.markdown)


def test_stress_selector_and_matrix_render():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    next(s for s in at.select_slider if s.label.startswith("Late-payment stress")).set_value(60).run()
    assert not at.exception, at.exception
    assert any("Late-payment stress matrix" in m.value for m in at.markdown)


def test_no_plan_survives_banner():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    next(s for s in at.slider if s.label == "Supplier delivery day").set_value(35).run()
    assert any("No plan survives" in e.value for e in at.error)
