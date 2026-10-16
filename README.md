# OrderFit — Streamlit prototype

A decision agent that evaluates a specific purchase order **before** the owner
commits: it reads the documents, rebuilds the dated cash position, and answers
*"can we accept this order without breaching our minimum cash reserve — and if
not, which response is best?"*

Built for the FinTechathon 2026 concept proposal (Topic E). Everything here is
**synthetic data** — no live banks, lenders, or email.

## Run it

```bash
cd orderfit
pip install -r requirements.txt
streamlit run app.py
```

Optional: put a `GOOGLE_API_KEY` in the parent `.env` (see `../.env.example`)
to enable the Gemini explanation and Q&A. Without a key, every deterministic
part still works — the narrative falls back to templates.

## What to try (5-minute demo path)

1. **Decision memo** (default tab) — the agent's answer for the shipped case:
   accept as-is breaches the reserve on day 20; the 50% customer advance is
   the cheapest feasible plan.
2. **Cash timeline** — balance paths for the six canonical options vs the
   dashed reserve line.
3. Move the **customer payment day** slider to 75 — the financing plans now
   fail their day-61 repayment; the memo flips to "robust to delay" reasoning
   and shows the sensitivity scan.
4. Change the **owner priority** to "do not depend on customer consent" — the
   ranking changes and the change is explained.
5. Tick **"Inject instruction into the PO"** — a prompt-injection line is
   flagged, treated as data, and the verdict does not change.
6. **Approve & execute** — approve the plan version, then watch it post to the
   simulated bank ledger, mock outbox and mock lender portal, with a
   consistency check (ledger path == engine prediction) and a full operation
   log. The T3 buttons are hard-blocked in code.

## Architecture

```
case_data.py   synthetic case + documents (facts behind the extraction demo)
engine.py      deterministic Decimal engine: simulation, feasibility,
               plan enumeration, constrained ranking, min-change probes
agent.py       stages A-E: extraction w/ source spans + injection filter,
               alerts, sensitivity scan, uncertainty rating, decision memo
sandbox.py     permission gate (T0-T3), simulated bank, mock outbox,
               mock lender portal, operation log
gemini_client.py  optional Gemini narrative / Q&A (data-grounded, swappable)
app.py         Streamlit UI
tests/         regression tests locking the worked-example numbers
```

Design rule enforced in code: **the model may propose, only the engine
verifies.** Every feasibility claim, balance, fee and margin on screen is
computed by `engine.py` with `Decimal` arithmetic; Gemini never does
arithmetic and never creates or alters financing terms.

## Tests

```bash
cd orderfit
python -m pytest tests/ -q
```
