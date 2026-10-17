"""Company names and email domains: rule checks and the optional Google check."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import company_check as cc  # noqa: E402
import gemini_client  # noqa: E402
from test_api import _sample, _session, client  # noqa: E402


def test_lookalike_and_name_rules():
    assert cc.lookalike("brightwavesupplies.example", "brightwave-supp1ies.example")
    assert not cc.lookalike("brightwavesupplies.example", "acmetrading.example")
    assert not cc.lookalike("brightwavesupplies.example", "brightwavesupplies.example")
    assert cc.name_matches_domain("Meridian Retail Group", "meridianretail.example")
    assert cc.name_matches_domain("Kaveri Textile Mills", "random-shop.example") is False


def test_free_mail_is_flagged():
    p = cc.Party("supplier", "Brightwave Supplies", "brightwave.pay@gmail.com", "DOC-2")
    assert any("free webmail" in r["text"] for r in cc.rule_checks(p))


def test_companies_endpoint_rules_and_google_off_by_default():
    sid = _session()
    _sample(sid, "fraud")
    r = client.post("/api/companies", json={"session_id": sid}).json()
    roles = {p["role"]: p for p in r["parties"]}
    assert roles["supplier"]["email"] == "accounts@brightwavesupplies.example"
    assert any(x["kind"] == "bad" and "supp1ies" in x["text"] for x in roles["supplier"]["rules"])
    assert r["mode"] == "off" and "SOLVORDER_GOOGLE_SEARCH" in r["note"]


def test_google_check_uses_gemini_results(monkeypatch):
    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setenv("SOLVORDER_GOOGLE_SEARCH", "1")
    cc._CACHE.clear()
    calls = []

    def fake(parties):
        calls.append(parties)
        return ([{"role": "supplier", "company": "Brightwave Supplies", "found": "no",
                  "official_domain": "", "email_domain_matches": "unclear",
                  "summary": "No public record found."},
                 {"role": "customer", "company": "Meridian Retail Group", "found": "YES",
                  "official_domain": "meridianretail.example", "email_domain_matches": "yes",
                  "summary": "Listed retailer."}],
                [{"title": "example", "uri": "https://example.com"}])

    monkeypatch.setattr(gemini_client, "verify_companies_web", fake)
    sid = _session()
    _sample(sid, "clean")
    r = client.post("/api/companies", json={"session_id": sid}).json()
    roles = {p["role"]: p["google"] for p in r["parties"]}
    assert r["mode"] == "on" and roles["supplier"]["found"] == "no" and roles["customer"]["found"] == "yes"
    assert r["sources"][0]["uri"] == "https://example.com"
    client.post("/api/companies", json={"session_id": sid})
    assert len(calls) == 1  # cached
    log = client.get(f"/api/log?session_id={sid}").json()["entries"]
    assert any(e["tool"] == "gemini.google_search" and e["where"] == "gemini" for e in log)
    cc._CACHE.clear()


def test_google_check_failure_degrades(monkeypatch):
    monkeypatch.setattr(gemini_client, "gemini_available", lambda: True)
    monkeypatch.setenv("SOLVORDER_GOOGLE_SEARCH", "1")
    cc._CACHE.clear()

    def boom(parties):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(gemini_client, "verify_companies_web", boom)
    sid = _session()
    _sample(sid, "clean")
    r = client.post("/api/companies", json={"session_id": sid}).json()
    assert r["mode"] == "error" and r["parties"][0]["rules"]
