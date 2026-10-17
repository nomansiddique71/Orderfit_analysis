"""Uploaded-document pipeline: read -> extract -> verify -> checks -> case -> agent.

Runs offline (deterministic parser). The 'clean' sample pack describes the
same order as the built-in Acme case, so the engine must give identical
numbers from the PDFs.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent  # noqa: E402
import case_builder  # noqa: E402
import doc_extract  # noqa: E402
from case_data import CASE  # noqa: E402
from docparse import parse_amount, parse_amounts  # noqa: E402

D = Decimal
SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _load(pack):
    meta = next(p for p in json.loads((SAMPLES / "packs.json").read_text()) if p["id"] == pack)
    docs = [doc_extract.read_upload(f"DOC-{i}", name, (SAMPLES / pack / name).read_bytes())
            for i, name in enumerate(meta["files"], 1)]
    facts, mode, note = doc_extract.extract_facts(docs)
    profile = case_builder.profile_from_json(json.loads((SAMPLES / pack / "profile.json").read_text()))
    return docs, facts, mode, profile


def _flags(pack):
    docs, facts, mode, _ = _load(pack)
    stage = doc_extract.to_document_stage(facts, docs, mode, "")
    return {f.code: f for f in stage.integrity}, stage


# ------------------------------------------------------------- parsing


def test_south_asian_and_lakh_crore_amounts():
    assert parse_amount("INR 5,00,000").value == D("500000")
    assert parse_amount("INR 2L due day 0").value == D("200000")
    assert parse_amount("INR 1.5 lakh").value == D("150000")
    assert parse_amount("0.5 crore").value == D("5000000")
    assert parse_amount("USD 12,000 due day 0").value == D("12000")
    assert "South Asian" in parse_amounts("5,00,000")[0].note


# -------------------------------------------------------- clean pack


def test_clean_pack_reproduces_acme_numbers():
    docs, facts, mode, profile = _load("clean")
    assert [d.kind for d in docs] == ["purchase_order", "supplier_quote", "invoice"]
    built = case_builder.build_case(facts, profile)
    assert built.missing == [] and built.customer_payment_day == 60
    run = agent.run_agent(built.case, 60, "maximize_margin", False,
                          documents=doc_extract.to_document_stage(facts, docs, mode, ""))
    ref = agent.run_agent(CASE, 60, "maximize_margin", False)
    assert run.winner.plan.id == ref.winner.plan.id == "adv50_ext0_nofin"
    for pid in ("accept-as-is", "adv50_ext0_nofin", "adv0_ext0_OFF-1", "adv50_ext1_OFF-2"):
        a, b = run.results[pid], ref.results[pid]
        assert (a.min_balance, a.min_day, a.first_breach_day, a.net_margin) == \
               (b.min_balance, b.min_day, b.first_breach_day, b.net_margin), pid
    assert not run.execution_blocks


def test_clean_pack_facts_are_verified():
    _, facts, _, _ = _load("clean")
    assert facts.order_value.verified and facts.delivery_day.verified
    assert all(p.amount.verified and p.day.verified for p in facts.supplier_payments)


# -------------------------------------------------------- fraud pack


def test_fraud_pack_flags_bank_change_and_blocks_execution():
    flags, stage = _flags("fraud")
    assert flags["BANK_CHANGE"].severity == "critical" and flags["BANK_CHANGE"].blocks_execution
    assert "****4821" in flags["BANK_CHANGE"].message and "****1937" in flags["BANK_CHANGE"].message
    assert "PRESSURE_LANGUAGE" in flags
    assert flags["LOOKALIKE_DOMAIN"].blocks_execution and "supp1ies" in flags["LOOKALIKE_DOMAIN"].message
    docs, facts, mode, profile = _load("fraud")
    built = case_builder.build_case(facts, profile)
    run = agent.run_agent(built.case, built.customer_payment_day, "maximize_margin", False,
                          documents=stage)
    assert run.execution_blocks == ["Supplier bank details changed", "Look-alike supplier email domain"]


def test_resolving_fraud_flag_unblocks():
    docs, facts, mode, _ = _load("fraud")
    stage = doc_extract.to_document_stage(
        facts, docs, mode, "", resolved={"BANK_CHANGE": "Called Brightwave on known number"})
    assert all(f.resolved for f in stage.integrity if f.code == "BANK_CHANGE")


def test_sandbox_refuses_while_fraud_flag_open():
    import sandbox

    docs, facts, mode, profile = _load("fraud")
    built = case_builder.build_case(facts, profile)
    stage = doc_extract.to_document_stage(facts, docs, mode, "")
    run = agent.run_agent(built.case, 60, "maximize_margin", False, documents=stage)
    log = sandbox.OperationLog()
    appr = sandbox.Approval("APP-1", "pv", run.winner.plan.id, run.winner.plan.label)
    rep = sandbox.execute_plan(run, run.winner, run.draft_message, appr, {"APP-1": appr}, log,
                               sandbox.PermissionGate(log), sandbox.SimulatedBank(),
                               sandbox.MockOutbox(), sandbox.MockLenderPortal({}),
                               blocks=run.execution_blocks)
    assert not rep.ok and "fraud" in rep.steps[-1].lower()
    assert log.entries[-1].result == "BLOCKED"


# ---------------------------------------------------- injection pack


def test_injection_pack_flagged_and_verdict_unchanged():
    flags, stage = _flags("injection")
    assert "INJECTION" in flags and stage.injections
    docs, facts, mode, profile = _load("injection")
    built = case_builder.build_case(facts, profile)
    run = agent.run_agent(built.case, 60, "maximize_margin", False, documents=stage)
    assert run.winner.plan.id == "adv50_ext0_nofin"


# ---------------------------------------------------- ambiguous pack


def test_ambiguous_pack_checks():
    flags, _ = _flags("ambiguous")
    assert {"NET_TERMS", "LINE_ITEMS", "CANCELLATION", "NUMBER_FORMAT"} <= set(flags)
    assert "day 45" in flags["NET_TERMS"].message and "day 80" in flags["NET_TERMS"].message
    assert "4,80,000" not in flags["LINE_ITEMS"].message  # engine formats in plain grouping
    assert "480,000.00" in flags["LINE_ITEMS"].message


def test_ambiguous_pack_two_payment_readings():
    _, facts, _, profile = _load("ambiguous")
    safe = case_builder.build_case(facts, profile)
    assert safe.payment_readings == {"after_order": 45, "after_delivery": 80}
    assert safe.customer_payment_day == 80  # later, safer reading by default
    early = case_builder.build_case(facts, profile, payment_reading="after_order")
    assert early.customer_payment_day == 45
    # 2L + 1.5 lakh + 25,000 read exactly
    assert [-m.amount for m in safe.case.order_costs] == [D("200000"), D("150000"), D("25000")]


def test_missing_facts_are_reported_not_guessed():
    from docmodel import Facts

    built = case_builder.build_case(Facts(), case_builder.profile_from_json(
        json.loads((SAMPLES / "clean" / "profile.json").read_text())))
    assert built.case is None
    assert "Order value" in built.missing and "At least one supplier payment" in built.missing


def test_upload_limits():
    import pytest

    with pytest.raises(ValueError):
        doc_extract.read_upload("DOC-1", "big.pdf", b"%PDF-" + b"0" * (9 * 1024 * 1024))
    with pytest.raises(ValueError):
        doc_extract.read_upload("DOC-1", "empty.txt", b"   ")
