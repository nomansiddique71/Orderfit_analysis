"""Who are we dealing with? Company names and email addresses in the documents.

Two layers, same rule as everywhere in SolvOrder (the model proposes, rules decide):

  Rules (always on, no network)
    FREE_EMAIL        a company writes from a free webmail address (gmail.com ...)
    LOOKALIKE_DOMAIN  a supplier document uses an email domain one or two
                      characters away from the supplier's known domain
                      (brightwave-supp1ies vs brightwavesupplies): a classic
                      payment-diversion trick. Blocks payments until handled.
    domain vs name    the email domain does not resemble the company name (info)

  Google check (optional: SOLVORDER_GOOGLE_SEARCH=1, off by default because
  grounded search is billed per request)
    Gemini with Google Search grounding looks each company up and reports
    whether it has a public web presence, its official domain, and whether the
    email domain belongs to it -- with the web sources it used. The result is
    shown to the owner as evidence; it never changes a number.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")
FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com",
             "live.com", "aol.com", "icloud.com", "proton.me", "protonmail.com", "gmx.com",
             "mail.com", "yandex.com", "zoho.com", "rediffmail.com"}
COMPANY_WORDS = {"ltd", "limited", "co", "company", "inc", "llc", "pvt", "private", "group",
                 "plc", "corp", "corporation", "the", "and", "trading", "gmbh", "sa"}


@dataclass
class Party:
    role: str  # customer | supplier
    company: str
    email: str
    source: str  # doc id

    @property
    def domain(self) -> str:
        m = EMAIL_RE.search(self.email or "")
        return m.group(1).lower() if m else ""

    def to_json(self) -> dict:
        return {"role": self.role, "company": self.company, "email": self.email,
                "domain": self.domain, "source": self.source}


def parties(facts) -> list[Party]:
    out = []
    for role, name, email in (("customer", facts.customer_name, facts.customer_email),
                              ("supplier", facts.supplier_name, facts.supplier_email)):
        if name.present or email.present:
            out.append(Party(role, name.value.strip(), email.value.strip(),
                             email.source or name.source))
    return out


def _core(domain: str) -> str:
    """Registrable name without TLD and punctuation: 'brightwave-supp1ies.example' -> 'brightwavesupp1ies'."""
    labels = domain.lower().split(".")
    name = labels[-2] if len(labels) >= 2 else labels[0]
    return re.sub(r"[^a-z0-9]", "", name)


def _distance(a: str, b: str) -> int:
    """Levenshtein distance (small strings only)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def lookalike(known: str, other: str) -> bool:
    """Different domains whose names differ by 1-2 edits (or only by punctuation)."""
    if not known or not other or known == other:
        return False
    a, b = _core(known), _core(other)
    return a == b or 0 < _distance(a, b) <= 2


def name_matches_domain(company: str, domain: str) -> bool | None:
    """True if a distinctive word of the company name appears in the domain."""
    words = [w for w in re.findall(r"[a-z0-9]+", company.lower()) if w not in COMPANY_WORDS and len(w) > 2]
    if not words or not domain:
        return None
    core = _core(domain)
    return any(w in core for w in words)


def rule_checks(p: Party) -> list[dict]:
    """Per-party results shown in the company card: kind ok | warn | bad."""
    out = []
    if not p.email:
        return [{"kind": "warn", "text": "No email address found in the documents."}]
    if p.domain in FREE_MAIL:
        out.append({"kind": "warn", "text": f"Uses free webmail ({p.domain}), not a company domain."})
    else:
        match = name_matches_domain(p.company, p.domain)
        if match is True:
            out.append({"kind": "ok", "text": f"Email domain {p.domain} matches the company name."})
        elif match is False:
            out.append({"kind": "warn", "text": f"Email domain {p.domain} does not resemble '{p.company}'."})
    return out


def domain_flags(facts, docs) -> list[tuple[str, str, str, str, list[str], bool]]:
    """(code, severity, title, message, documents, blocks) for doc_checks."""
    out = []
    by_role = {p.role: p for p in parties(facts)}
    sup = by_role.get("supplier")
    if sup and sup.domain and sup.domain not in FREE_MAIL:
        for d in docs:
            if d.kind not in ("supplier_quote", "invoice", "email") or not d.text:
                continue
            for m in EMAIL_RE.finditer(d.text):
                dom = m.group(1).lower()
                if lookalike(sup.domain, dom):
                    out.append(("LOOKALIKE_DOMAIN", "critical", "Look-alike supplier email domain",
                                f"{d.doc_id} uses {m.group(0)}, which imitates the supplier's domain "
                                f"{sup.domain} ({_core(dom)} vs {_core(sup.domain)}). Fraudsters register "
                                f"near-identical domains to redirect payments. Payments are blocked until "
                                f"you verify the sender on a number you already had.",
                                [d.doc_id], True))
                    break
    for p in by_role.values():
        if p.domain in FREE_MAIL:
            out.append(("FREE_EMAIL", "warning", f"{p.role.title()} uses a free email address",
                        f"{p.company or p.role} writes from {p.email}. Real companies usually use their "
                        f"own domain; confirm the contact before you pay or ship.", [p.source], False))
    # one flag per code is enough: the first look-alike found is the evidence
    seen, unique = set(), []
    for f in out:
        if f[0] not in seen or f[0] == "FREE_EMAIL":
            seen.add(f[0])
            unique.append(f)
    return unique


# ------------------------------------------------------------ Google check


def google_enabled() -> bool:
    import gemini_client

    return (gemini_client.gemini_available()
            and os.environ.get("SOLVORDER_GOOGLE_SEARCH", "0").strip().lower() in ("1", "true", "yes", "on"))


_CACHE: dict[str, dict] = {}


def google_check(ps: list[Party]) -> dict:
    """{"mode": "on"|"off"|"error", "note", "results": {role: {...}}}. Cached per party set."""
    if not ps:
        return {"mode": "off", "note": "No company names found.", "results": {}}
    if not google_enabled():
        return {"mode": "off", "results": {},
                "note": "Google check is off on this server (set SOLVORDER_GOOGLE_SEARCH=1). "
                        "The rule checks above still run."}
    key = json.dumps([p.to_json() for p in ps], sort_keys=True)
    if key not in _CACHE:
        import gemini_client

        try:
            rows, sources = gemini_client.verify_companies_web([p.to_json() for p in ps])
            results = {}
            for p in ps:
                r = next((x for x in rows if str(x.get("company", "")).lower() == p.company.lower()), None)
                r = r or next((x for x in rows if str(x.get("role", "")).lower() == p.role), None) or {}
                results[p.role] = {
                    "found": _yn(r.get("found")), "official_domain": str(r.get("official_domain", ""))[:120],
                    "email_domain_matches": _yn(r.get("email_domain_matches")),
                    "summary": str(r.get("summary", ""))[:400]}
            _CACHE[key] = {"mode": "on", "results": results, "sources": sources[:8],
                           "note": f"Searched Google with {gemini_client.backend_label()}."}
        except Exception as exc:  # never block the flow on the web check
            return {"mode": "error", "results": {},
                    "note": f"Google check failed ({exc}); the rule checks above still apply."}
    return _CACHE[key]


def _yn(v) -> str:
    v = str(v or "").strip().lower()
    return v if v in ("yes", "no") else "unclear"
