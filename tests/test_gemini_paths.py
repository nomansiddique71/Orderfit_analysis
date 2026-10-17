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


# --------------------------------------------- uploaded documents via Gemini

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _fraud_docs():
    import doc_extract

    names = ["purchase_order.pdf", "supplier_quote.pdf", "supplier_invoice.pdf", "supplier_email.pdf"]
    return [doc_extract.read_upload(f"DOC-{i}", n, (SAMPLES / "fraud" / n).read_bytes())
            for i, n in enumerate(names, 1)]


def _s(value, source, span, conf=0.95):
    return {"value": value, "source": source, "span": span, "confidence": conf}


def _model_output(order_span="Total order value: USD 30,000", order_value="USD 30,000"):
    return {
        "documents": [{"source": "DOC-1", "kind": "purchase_order"}, {"source": "DOC-2", "kind": "supplier_quote"},
                      {"source": "DOC-3", "kind": "invoice"}, {"source": "DOC-4", "kind": "email"}],
        "customer_name": _s("Meridian Retail Group", "DOC-1", "Buyer: Meridian Retail Group"),
        "order_ref": _s("PO-8841", "DOC-1", "PO number: PO-8841"),
        "order_value": _s(order_value, "DOC-1", order_span),
        "delivery_day": _s("day 30", "DOC-1", "Delivery required by: day 30"),
        "payment_terms_days": _s("30", "DOC-1", "Payment terms: Net 30 days after delivery"),
        "payment_terms_basis": _s("after_delivery", "DOC-1", "Net 30 days after delivery"),
        "late_penalty_pct_per_week": _s("1%", "DOC-1", "Late delivery penalty: 1% of order value per week"),
        "cancellation_clause": _s("none", "DOC-1", "Cancellation: none"),
        "supplier_name": _s("Brightwave Supplies", "DOC-2", "Supplier: Brightwave Supplies"),
        "invoice_amount": _s("USD 12,000", "DOC-3", "Amount due: USD 12,000"),
        "supplier_payments": [
            {"label": "Supplier deposit", "amount": _s("USD 12,000", "DOC-2", "Supplier deposit: USD 12,000 due day 0"),
             "due_day": _s("day 0", "DOC-2", "Supplier deposit: USD 12,000 due day 0")},
            {"label": "Pre-delivery payment", "amount": _s("USD 5,000", "DOC-2", "Pre-delivery payment: USD 5,000 due day 20"),
             "due_day": _s("day 20", "DOC-2", "Pre-delivery payment: USD 5,000 due day 20")},
            {"label": "Shipping and handling", "amount": _s("USD 1,500", "DOC-2", "Shipping and handling: USD 1,500 due day 30"),
             "due_day": _s("day 30", "DOC-2", "Shipping and handling: USD 1,500 due day 30")},
        ],
        "line_items": [],
        "bank_details": [
            {"source": "DOC-2", "payee": "Brightwave Supplies Ltd", "bank_name": "First Harbour Bank",
             "account_number": "4410 2283 1937", "span": "Account number: 4410 2283 1937", "confidence": 0.95},
            {"source": "DOC-3", "payee": "Brightwave Supplies Ltd", "bank_name": "Pacific Crest Bank",
             "account_number": "7702 9918 4821", "span": "Account number: 7702 9918 4821", "confidence": 0.95},
        ],
        "conflicts": ["The invoice gives a different bank account from the quote."],
        "instructions_found": [],
    }


def test_gemini_document_path_verified_and_fraud_flagged(monkeypatch):
    import case_builder
    import doc_extract

    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "extract_order_documents", lambda docs: _model_output())
    doc_extract._CACHE.clear()
    docs = _fraud_docs()
    facts, mode, _ = doc_extract.extract_facts(docs)
    assert mode == "gemini" and facts.order_value.verified
    stage = doc_extract.to_document_stage(facts, docs, mode, "")
    codes = {f.code for f in stage.integrity}
    assert {"BANK_CHANGE", "PRESSURE_LANGUAGE", "MODEL_CONFLICT"} <= codes
    profile = case_builder.profile_from_json(__import__("json").loads((SAMPLES / "fraud" / "profile.json").read_text()))
    built = case_builder.build_case(facts, profile)
    run = agent.run_agent(built.case, built.customer_payment_day, "maximize_margin", False, documents=stage)
    assert run.winner.plan.id == "adv50_ext0_nofin" and run.execution_blocks


def test_gemini_invented_span_or_misread_amount_is_downgraded(monkeypatch):
    import doc_extract

    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    doc_extract._CACHE.clear()
    # invented quote: not in the document
    monkeypatch.setattr(gemini_client, "extract_order_documents",
                        lambda docs: _model_output(order_span="Order total is thirty thousand"))
    facts, _, _ = doc_extract.extract_facts(_fraud_docs())
    assert not facts.order_value.verified and facts.order_value.confidence <= 0.3
    doc_extract._CACHE.clear()
    # real quote, wrong number
    monkeypatch.setattr(gemini_client, "extract_order_documents",
                        lambda docs: _model_output(order_value="USD 3,000"))
    facts, _, _ = doc_extract.extract_facts(_fraud_docs())
    assert not facts.order_value.verified and "does not match" in facts.order_value.note
    stage = doc_extract.to_document_stage(facts, _fraud_docs(), "gemini", "")
    assert any(f.name == "Order value" and f.low_confidence for f in stage.fields)
    doc_extract._CACHE.clear()


def test_gemini_document_failure_falls_back_to_parser(monkeypatch):
    import doc_extract

    def boom(docs):
        raise RuntimeError("503")

    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "extract_order_documents", boom)
    doc_extract._CACHE.clear()
    facts, mode, note = doc_extract.extract_facts(_fraud_docs())
    assert mode == "parser" and "Gemini could not read" in note and facts.order_value.present


def test_concurrent_reads_share_one_gemini_call_and_get_private_copies(monkeypatch):
    """Startup warm-up and a visitor asking for the same sample make one model call;
    each caller gets its own Facts object, so one session can't edit another's."""
    import threading
    import time

    import doc_extract

    calls = []

    def slow(docs):
        calls.append(1)
        time.sleep(0.2)
        return _model_output()

    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "extract_order_documents", slow)
    doc_extract._CACHE.clear()
    out = []
    threads = [threading.Thread(target=lambda: out.append(doc_extract.extract_facts(_fraud_docs())))
               for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1 and len(out) == 3
    assert out[0][0] is not out[1][0] and out[0][0].order_value.value == out[1][0].order_value.value
    docs = _fraud_docs()
    doc_extract.extract_facts(docs)  # cache hit still applies Gemini's document kinds
    assert {d.kind for d in docs} >= {"purchase_order"}
    doc_extract._CACHE.clear()


def test_failed_gemini_read_is_not_cached(monkeypatch):
    import doc_extract

    state = {"fail": True}

    def flaky(docs):
        if state["fail"]:
            raise RuntimeError("503")
        return _model_output()

    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setattr(gemini_client, "extract_order_documents", flaky)
    doc_extract._CACHE.clear()
    assert doc_extract.extract_facts(_fraud_docs())[1] == "parser"
    state["fail"] = False
    assert doc_extract.extract_facts(_fraud_docs())[1] == "gemini"
    doc_extract._CACHE.clear()


def test_thinking_level_is_set_and_dropped_for_models_that_reject_it(monkeypatch):
    from google.genai import types

    cfg = gemini_client._with_thinking(types.GenerateContentConfig(temperature=0), "m1")
    assert cfg.thinking_config.thinking_level == types.ThinkingLevel.LOW and cfg.temperature == 0
    monkeypatch.setenv("GEMINI_THINKING", "default")
    assert gemini_client._with_thinking(None, "m1") is None
    monkeypatch.delenv("GEMINI_THINKING")
    gemini_client._NO_THINKING.add("old-model")
    try:
        assert gemini_client._with_thinking(None, "old-model") is None
    finally:
        gemini_client._NO_THINKING.discard("old-model")
