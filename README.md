# SolvOrder: can my cash carry this order?

**Google Cloud AI Builder Cup 2026 · BFSI: Intelligent Risk, Fraud & Financial Experiences**

A small business wins a big, profitable purchase order, but it must pay its
supplier weeks before the customer pays. SolvOrder answers the owner's real
question **before** they commit:

> *Can we accept this order without our cash falling below our minimum
> reserve? If not, what is the safest way to make it work, and is anything in
> these documents fraudulent?*

It reads the purchase order, supplier quote, invoice and emails with
**Gemini on Vertex AI**, verifies every value against the source text, runs
deterministic fraud and consistency checks, rebuilds the business's cash
**day by day**, compares every response (customer advance, later supplier
payment, loans, decline) under late-payment stress, and recommends one plan.
After the owner approves, it carries the plan out in a **sandbox** (simulated
bank, mock outbox, mock lender portal) and logs every step.
Synthetic data only: no real bank, lender or email is ever touched.

## How it covers the BFSI track

| Track theme | What SolvOrder does |
|---|---|
| **Risk** | Liquidity risk of one order: reserve breaches (including same-day dips), funding gap (how much, for how many days), late-payment stress at 15/30/60/90 days, delay tolerance per plan, partial/no payment, supplier price rise or late delivery, cancellation exposure. |
| **Fraud** | Payment-diversion checks: supplier bank details changed between quote, invoice and email; payee is not the supplier; invoice amount matches no quoted payment; pressure or "new account" wording. Blocking flags stop **every** sandbox payment until the owner records an out-of-band check. Prompt injections in documents are flagged and ignored. |
| **Automating complex processes** | Documents → verified facts → cash rebuild → every plan simulated and ranked → drafted message → approved, logged sandbox execution. |
| **Better customer interactions** | Plain-language verdict, "Ask SolvOrder" Q&A, and a counterparty message whose numbers Gemini cannot change. |
| **Personalised, informed experiences** | The owner's cash, reserve, financing cap, priority and stress level drive the answer; near ties are handed back to the owner. |

## How Google AI is used

| Where | What Gemini does | How the engine keeps it honest |
|---|---|---|
| Reading documents | Gemini (structured JSON output) reads uploaded PDFs/text: order value, delivery, payment terms and their start, supplier payments, line items, bank details, cancellation clause, conflicts, instructions addressed to an AI. Scanned PDFs are sent as PDF parts. | Every value carries a verbatim quote; the verifier checks the quote exists in the document text and the value matches it (`doc_extract.py`). Failures lower confidence and become owner questions. Numbers are parsed by code (`docparse.py`, incl. 5,00,000 / 5L / 0.5 crore), never by the model. |
| Fraud & consistency | Reports conflicts and instructions it notices. | The decisions are deterministic rules (`doc_checks.py`); a regex filter also catches injections. |
| Explain & Q&A | Explains the decision; answers the owner's questions. | Prompt contains only the engine's memo JSON; told never to compute numbers. |
| Draft polish | Rewrites the negotiation message. | Rejected if it adds or drops any number (`gemini_client.verify_draft`). |

Design rule: **the model may propose; only the engine verifies.** All money
maths uses Python `Decimal` in `engine.py`. Gemini is called only on an
explicit action (upload, Ask, Explain, Polish) and every call is cached. If
Gemini is unavailable, SolvOrder still works end to end: a deterministic
parser reads the sample-document layout, or the owner enters the facts.

## Architecture

```
Browser (React + Tailwind, web/)
   │  /api
Cloud Run container ── FastAPI (server.py)
   ├─ doc_extract.py   read PDF/text · Gemini extraction · span verifier · parser fallback
   ├─ doc_checks.py    fraud & integrity rules
   ├─ case_builder.py  owner-confirmed facts + business profile -> Case
   ├─ agent.py         stages A-E: alerts, ranking, uncertainty, near tie, smallest change
   ├─ engine.py        Decimal cash simulation, constraints, stress, tolerance, scenarios
   ├─ sandbox.py       permission gate T0-T3, simulated bank, mock outbox/lender, op log
   └─ gemini_client.py Gemini via Vertex AI (or API key), cached calls with fallbacks
        └──► Gemini on Vertex AI (service account with roles/aiplatform.user)
```

Permission tiers are enforced in code: T0 read · T1 propose · T2 act in the
sandbox only after the owner approves that exact plan version (and never
while a fraud flag is open) · T3 never (real money, real email, invented loan
terms, editing documents: no code path, attempts logged).

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cd web && npm ci && npm run build && cd ..
uvicorn server:app --port 8000          # open http://localhost:8000
```

UI development with hot reload: run `uvicorn server:app --port 8000` and, in
`web/`, `npm run dev` (Vite proxies `/api`).

Gemini locally (optional):

```bash
gcloud auth application-default login
export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=<project-id> GOOGLE_CLOUD_LOCATION=global
```

Never commit keys. `ORDERFIT_OFFLINE=1` forces the no-AI path (used by tests).

## Sample documents

`samples/` holds four synthetic packs (regenerate with
`python scripts/make_samples.py`):

| Pack | Shows |
|---|---|
| Clean order (USD) | Reserve breach on day 20; 50% advance is the cheapest safe plan. Same numbers as the built-in Acme case. |
| Changed bank details | Invoice and an "urgent" email ask for a new account → critical fraud flag; payments blocked until resolved. |
| Hidden AI instruction | A PO line tells the AI to ignore the reserve → flagged, decision unchanged. |
| Ambiguous terms (INR) | "Net 45" with no start date (two readings), line items that don't add up, lakh amounts, cancel-anytime clause. |

## Tests

```bash
python -m pytest tests -q
```

88 tests, all offline: locked worked-example numbers, same-day rule,
constraints, delay tolerance cross-checked against a day-by-day scan,
scenarios, funding gap, sandbox approval binding and fraud block, the
document pipeline on every sample pack, Gemini paths with a stubbed model
(honest output verified; invented or misread values downgraded; failures
fall back), and the API end to end.

## Deploy to Cloud Run

One container (the Dockerfile builds the React UI, then serves it from
FastAPI):

```bash
gcloud run deploy orderfit --source . --region asia-southeast1 \
  --service-account orderfit-run@<PROJECT_ID>.iam.gserviceaccount.com \
  --update-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=<PROJECT_ID>,GOOGLE_CLOUD_LOCATION=global \
  --session-affinity --memory 1Gi --timeout 3600 --max-instances 2
```

Requires `aiplatform.googleapis.com` enabled and `roles/aiplatform.user` on
the service account. `UI=streamlit` (env var) serves the earlier Streamlit
interface instead.

## 5-minute demo path

1. **Changed bank details** sample → *Check the facts*: the critical fraud flag and pressure wording.
2. *See the cash risk*: plain-English verdict, funding gap, day-by-day chart.
3. *Compare options*: switch to "Safest if paid late" and 30 days; watch the ranking change; ask SolvOrder a question.
4. *Approve & act*: approve → execute → **blocked** by the fraud flag (logged as T2 BLOCKED).
5. Back on *Check the facts*, record the call-back check → execute again → ledger matches the engine; export the operation log.
6. **Hidden AI instruction** and **Ambiguous terms (INR)** samples for the security and integrity checks.

## Limits (honest)

- Synthetic data; one business profile per case; one currency per case; days are counted from order confirmation (no calendar dates).
- Sessions live in server memory (no database); a new Cloud Run instance starts a fresh session.
- Without Gemini, the parser only understands the sample "Label: value" layout; other documents need Gemini or manual entry. Scanned PDFs need Gemini and owner confirmation.
- Financing terms come from a fixed catalogue; real products have conditions (collateral, covenants) not modelled. Interest is simple, pro-rated per 30 days.
- The option set is a fixed enumeration (advance 0/25/50%, supplier extension, catalogue loans, sized loan, decline); split deliveries and postponing discretionary spend are not modelled.
- Not yet built: an independent reference implementation and baseline scoreboard, persistence, calendar-date parsing (e.g. 03/04/2026 ambiguity).
- Decision support, not financial advice.
