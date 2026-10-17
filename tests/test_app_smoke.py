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
    at.button(key="tie_adv0_ext0_OFF-1").click().run()
    assert not at.exception, at.exception
    assert any("resolved by you" in s.value for s in at.success)
