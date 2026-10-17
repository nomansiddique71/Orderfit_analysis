"""Exercise every Gemini code path with a fake model, so a deploy with Vertex AI
enabled cannot crash on code that the offline suite never reaches.

No network: gemini_client._generate is replaced by a stub that returns canned
text, the way the real model would.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent  # noqa: E402
import gemini_client  # noqa: E402
from case_data import CASE, QUOTE_TEXT, po_text  # noqa: E402


@pytest.fixture
def fake_gemini(monkeypatch):
    calls = []

    def fake_generate(contents, config=None):
        prompt = contents[0]
        calls.append(prompt)
        if "document-extraction stage" in prompt:
            return json.dumps({"fields": [
                {"name": "Order value", "value": "USD 30,000", "source": "PO-8841",
                 "span": "Total order value: USD 30,000", "confidence": 0.98, "question": ""},
                {"name": "Customer payment terms", "value": "net 30 after delivery",
                 "source": "PO-8841", "span": "net 30 -- payment due 30 days after delivery",
                 "confidence": 0.95, "question": ""},
            ], "instructions_found": []})
        if prompt.startswith("Rewrite this business message"):
            return prompt.split("\n\n", 1)[1]  # same text back: numbers unchanged
        return "Grounded answer from the memo."

    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "_generate", fake_generate)
    agent._EXTRACTION_CACHE.clear()
    yield calls
    agent._EXTRACTION_CACHE.clear()


def test_memo_json_serialises_with_new_fields():
    run = agent.run_agent(CASE, 60, "most_robust", False, stress_delay=30)
    memo = json.loads(gemini_client._memo_text(run))
    assert memo["stress_delay_days"] == 30
    assert memo["late_payment_tolerance"]
    assert "provisional_waiting_for_owner_confirmation" in memo


def test_gemini_extraction_path_runs_and_is_cached(fake_gemini):
    run = agent.run_agent(CASE, 60, "maximize_margin", False)
    assert run.extraction_mode == "gemini"
    assert {f.name for f in run.fields} == {"Order value", "Customer payment terms"}
    n = len(fake_gemini)
    agent.run_agent(CASE, 75, "most_robust", False)  # rerun: same documents
    assert len(fake_gemini) == n, "extraction must be cached across reruns"


def test_gemini_injection_still_flagged_by_regex(fake_gemini):
    run = agent.run_agent(CASE, 60, "maximize_margin", True)
    assert run.injections  # model reported none; the regex filter still catches it
    assert run.winner.plan.id == agent.run_agent(CASE, 60, "maximize_margin", False).winner.plan.id


def test_explain_ask_polish_paths(fake_gemini):
    run = agent.run_agent(CASE, 60, "maximize_margin", False)
    assert gemini_client.explain_memo(run) == ("Grounded answer from the memo.", "gemini")
    assert gemini_client.ask(run, "why?")[1] == "gemini"
    text, mode, note = gemini_client.polish_draft(run)
    assert mode == "gemini" and text == run.draft_message


def test_model_failure_falls_back(monkeypatch):
    def boom(contents, config=None):
        raise RuntimeError("503 unavailable")

    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "_generate", boom)
    agent._EXTRACTION_CACHE.clear()
    run = agent.run_agent(CASE, 60, "maximize_margin", False)
    assert run.extraction_mode == "regex"
    assert gemini_client.explain_memo(run)[1] == "template"
    assert gemini_client.polish_draft(run)[1] == "template"
    assert gemini_client.ask(run, "why?")[1] == "template"
