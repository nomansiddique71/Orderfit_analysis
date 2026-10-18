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
Every plan has a **money breakdown**: each payment in and out by day, the
running balance, totals, profit, and plain reasons to accept or not, all from
the engine's numbers. The owner's **company profile** says which side of a deal
they are usually on (**seller**: a customer's order, or **buyer**: a supplier's
offer) and the currency the business runs in (BDT, INR, USD, GBP, EUR). Amounts
written in another currency are converted to it: **Gemini with Google Search
finds the exchange rate for the document's date** (today's rate, labelled, when
the document has no date), the conversion itself is exact Decimal arithmetic,
and every converted value shows what the document wrote and the rate used. The
owner can correct a rate; implausible rates are flagged; without Gemini the
owner is asked for the rate. Sample cases keep their own currency. For each case SolvOrder checks the role against the documents and
asks when they disagree. After the owner approves a plan, **Notify my customer**
(seller) or **Notify my supplier** (buyer) emails the other side from the
approved plan through a demo outbox, books the plan in a **sandbox** (simulated
bank, mock lender portal), and files plan and emails under **Approved / declined
plans**. When **no way of accepting keeps the reserve**, the only recommendation
is to decline: SolvOrder shows why each option fails (and any engine-verified
change that would make the deal work) and sends a polite, justified decline to
the customer or supplier, filed with the same record.
Synthetic data only: no real bank, lender or email is ever touched.

## How it covers the BFSI track

| Track theme | What SolvOrder does |
|---|---|
| **Risk** | Liquidity risk of one order: reserve breaches (including same-day dips), funding gap (how much, for how many days), late-payment stress at 15/30/60/90 days, delay tolerance per plan, partial/no payment, supplier price rise or late delivery, cancellation exposure. |
| **Fraud** | Payment-diversion checks: supplier bank details changed between quote, invoice and email; look-alike supplier email domain (`brightwave-supp1ies`); free-webmail senders; payee is not the supplier; invoice amount matches no quoted payment; pressure or "new account" wording. Optional Google check: Gemini with Search grounding looks each company up (public presence, official domain, does the email domain belong to it). Blocking flags stop **every** sandbox payment; the owner picks how to handle each check (verify by phone, pay only the known account, hold, report); only a safe choice unblocks. Prompt injections in documents are flagged and ignored. |
| **Automating complex processes** | Documents → verified facts → Gemini asks for what is missing → cash rebuild → every plan simulated and ranked → one message per party, sent on approval → logged sandbox execution (viewable outbox, ledger, lender portal). |
| **Better customer interactions** | Plain-language verdict and a step-by-step cash walk (cash today − payroll − bills − order costs + receipts = lowest point vs reserve), "Ask SolvOrder" Q&A, and counterparty messages whose numbers Gemini cannot change. |
| **Personalised, informed experiences** | After an upload, Gemini works out which facts about *this* business it still needs (cash, reserve, payroll, bills, receivables, loan offers, advance already received) and asks in a pop-up form. The owner's numbers, priority and stress level drive the answer; the owner can choose any safe plan, not only the recommended one. Demo accounts with email-code sign-up and a profile. |

## How Google AI is used

| Where | What Gemini does | How the engine keeps it honest |
|---|---|---|
| Reading documents | Gemini (structured JSON output) reads uploaded PDFs/text: order value, delivery, payment terms and their start, supplier payments, line items, bank details, cancellation clause, conflicts, instructions addressed to an AI. Scanned PDFs are sent as PDF parts. | Every value carries a verbatim quote; the verifier checks the quote exists in the document text and the value matches it (`doc_extract.py`). Failures lower confidence and become owner questions. Numbers are parsed by code (`docparse.py`, incl. 5,00,000 / 5L / 0.5 crore), never by the model. |
| Fraud & consistency | Reports conflicts and instructions it notices. | The decisions are deterministic rules (`doc_checks.py`); a regex filter also catches injections. |
| Intake questions | Picks and words the questions to ask the owner for this order (e.g. "What payroll is due before day 60?"). | Only from a fixed list of fields the engine understands; unknown keys dropped; the rule checklist is always the floor. |
| Company check (optional) | Gemini + **Google Search grounding** looks up each company and email domain, with web sources. | Shown as evidence only; rules (look-alike domain, free mail) decide flags. Off unless `SOLVORDER_GOOGLE_SEARCH=1`. |
| Explain & Q&A | Explains the decision; answers the owner's questions. | Prompt contains only the engine's memo JSON; told never to compute numbers. |
| Draft polish | Rewrites the negotiation message. | Rejected if it adds or drops any number (`gemini_client.verify_draft`). |

Design rule: **the model may propose; only the engine verifies.** All money
maths uses Python `Decimal` in `engine.py`. Gemini is called only on an
explicit action (upload, intake, Ask, Explain, Polish, company check) and every
call is cached; calls use a low thinking level (`GEMINI_THINKING`) for speed, and
the four sample packs are read once at startup so the demo answers instantly. If
Gemini is unavailable, SolvOrder still works end to end: a deterministic
parser reads the sample-document layout, or the owner enters the facts.

## Architecture

```
Browser (React + Tailwind, web/)
   │  /api
Cloud Run container ── FastAPI (server.py)
   ├─ doc_extract.py   read PDF/text · Gemini extraction · span verifier · parser fallback
   ├─ doc_checks.py    fraud & integrity rules
   ├─ company_check.py email-domain rules · optional Google check (Gemini + Search grounding)
   ├─ needs.py         intake questions (Gemini picks from a fixed list; rule checklist fallback)
   ├─ case_builder.py  owner-confirmed facts + business profile -> Case
   ├─ auth.py          demo accounts: email-code sign-up, PBKDF2 hashes, reset (in memory)
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

`samples/` holds six synthetic packs (regenerate with
`python scripts/make_samples.py`):

| Pack | Shows |
|---|---|
| Clean order (USD) | Reserve breach on day 20; 50% advance is the cheapest safe plan. Same numbers as the built-in Acme case. |
| Changed bank details | Invoice from a look-alike domain and an "urgent" email ask for a new account → critical fraud flags; payments blocked until handled. |
| Hidden AI instruction | A PO line tells the AI to ignore the reserve → flagged, decision unchanged. |
| Ambiguous terms (INR) | "Net 45" with no start date (two readings), line items that don't add up, lakh amounts, cancel-anytime clause. |
| You are the seller (BDT) | Padma Garments sells 3,000 shirts to Rupsha Fashion House. Role read from the PO (Seller: Padma); 50% advance recommended; Notify addresses the customer. |
| You are the buyer (BDT) | Padma Garments buys fabric from Meghna Fabrics. Role read from the PO (Buyer: Padma); no customer-advance plans; the smallest safe bank loan is recommended; Notify addresses the supplier (and the lender). |

## Tests

```bash
python -m pytest tests -q
```

122 tests, all offline: locked worked-example numbers, same-day rule,
constraints, delay tolerance cross-checked against a day-by-day scan,
scenarios, funding gap, sandbox approval binding and fraud block, the
document pipeline on every sample pack, Gemini paths with a stubbed model
(honest output verified; invented or misread values downgraded; failures
fall back), the cash walk against the engine, intake questions, plan choice and
per-party messages, the sandbox view and log labels, company checks, the demo
login, and the API end to end.

## Deploy to Cloud Run

One container (the Dockerfile builds the React UI, then serves it from
FastAPI):

```bash
gcloud run deploy orderfit --source . --region asia-southeast1 \
  --service-account orderfit-run@<PROJECT_ID>.iam.gserviceaccount.com \
  --update-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=<PROJECT_ID>,GOOGLE_CLOUD_LOCATION=global,SOLVORDER_GOOGLE_SEARCH=1 \
  --session-affinity --memory 1Gi --timeout 3600 --min-instances 1 --max-instances 1
```

Requires `aiplatform.googleapis.com` enabled and `roles/aiplatform.user` on
the service account. One always-on instance keeps the in-memory sessions,
accounts and Gemini cache warm (`--min-instances 1` is billed while idle; drop
it after judging). `SOLVORDER_GOOGLE_SEARCH=1` turns on the grounded Google
company check (billed per search); leave it out to run the rules only. `UI=streamlit` (env var) serves the earlier Streamlit
interface instead.

## 5-minute demo path

1. **Try the demo account** (or sign up: the code appears in the on-screen demo inbox).
2. **Changed bank details** sample → *Check the facts*: bank-change and look-alike-domain flags, pressure wording, "Who are you dealing with?" (Google check).
3. *See the cash risk*: the cash walk (today → payroll, bills, order costs → lowest point vs reserve) and the day-by-day chart.
4. *Compare options*: switch to "Safest if paid late"; **choose a different plan** than the recommended one.
5. *Approve & notify*: approve → **Notify my customer** → confirm the email → payments **blocked** by the fraud flags (Blocked in the log); the email still goes to the demo outbox.
6. Back on *Check the facts*, choose "pay only the original account" / "verified by phone", approve again and notify → ledger matches the engine; open **Inside the sandbox**, the labelled log and **Approved / declined plans**.
7. **Profile → Your company**: set the company name, *Buyer*, and *BDT*; load **You are the buyer (BDT)**; open **See the money breakdown** on any plan; approve → **Notify my supplier**.
8. **Currency**: profile currency *BDT*, then the manual form with "USD 30,000" and "USD 12,000" → the rate card (Gemini + Google Search, or enter it) and "৳36,42,000 in your currency · In the document: USD 30,000" under each amount.
9. **Decline**: on *Check the facts* raise the reserve until nothing works → *Compare options* shows only "Decline the order" with each option's failure → *Decline and notify my customer* → the polite mail is filed under **Approved / declined plans**.
10. **Option 2/3**: upload `samples/clean/*.pdf` or type a deal in the manual form → the intake pop-up asks only what is missing (your cash, reserve and payroll; as a buyer, the income you expect from the goods; your role if the documents disagree with your profile).

## Limits (honest)

- Synthetic data; one business profile per case; days are counted from order confirmation (calendar dates are read only for the exchange-rate date; 12/03/2026 is read day-first).
- Exchange rates come from Gemini with Google Search (one rate per currency per case, for the document date); the sanity band only catches gross errors such as an inverted rate. Emails to the counterparty quote amounts in the owner's currency.
- Buyer deals: the income from the goods is the owner's estimate (asked, not read from documents); a buyer's plans are supplier extension and loans (no customer to ask for an advance).
- Notify sends to a demo outbox only; no real email is delivered. Approved plans live in server memory with the demo account.
- Sessions and demo accounts live in server memory (no database): a restart clears them. The browser replays the current case after a restart, but accounts must sign up again. The demo login gates the UI; the analysis API itself is session-based, not account-based.
- The sample companies are invented, so the Google check reports "no public record" for them (as it should); its value shows on real names.
- Without Gemini, the parser only understands the sample "Label: value" layout; other documents need Gemini or manual entry. Scanned PDFs need Gemini and owner confirmation.
- Financing terms come from a fixed catalogue; real products have conditions (collateral, covenants) not modelled. Interest is simple, pro-rated per 30 days.
- The option set is a fixed enumeration (advance 0/25/50%, supplier extension, catalogue loans, sized loan, decline); split deliveries and postponing discretionary spend are not modelled.
- Not yet built: an independent reference implementation and baseline scoreboard, persistence, calendar-date parsing (e.g. 03/04/2026 ambiguity).
- Decision support, not financial advice.
