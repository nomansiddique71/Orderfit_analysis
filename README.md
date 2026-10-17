# OrderFit: AI decision agent for SME purchase orders

**Google Cloud AI Builder Cup 2026 · BFSI track** (risk assessment, document intelligence, financial assistance)

A small business gets a large, profitable purchase order, but it has to pay
the supplier weeks before the customer pays. OrderFit answers the owner's
real question **before** they commit:

> *Can we accept this order without our cash falling below the minimum
> reserve? If not, what is the best way to make it work?*

It reads the purchase order and supplier quote with **Gemini on Vertex AI**,
rebuilds the dated cash position, simulates every option (customer advance,
supplier extension, financing offers, decline), stress-tests late payment,
and recommends one plan with its risks. Synthetic data only: no live banks,
lenders or email.

## How Google AI is used

| Stage | What Gemini does | How the engine keeps it safe |
|---|---|---|
| A. Document extraction | Reads PO-8841 and Q-3312 and returns typed JSON fields (value, verbatim source span, confidence, owner question) using structured output | Every span must exist in the source text; key amounts must match the owner-confirmed case. Failures lower confidence and become owner questions. The model's numbers never enter the simulation. |
| Injection defence | Reports any text that tries to instruct the AI | A deterministic regex filter runs too. The verdict cannot change either way (tested). |
| Explain & Q&A | Explains the memo and answers the owner's questions | Prompt contains only the engine's memo JSON; the model is told not to compute numbers. |
| Draft polish | Rewrites the negotiation email in clear English | Rejected if it adds or drops any number compared with the engine's draft. |

Design rule: **the model may propose, only the engine verifies.** All
balances, fees, margins and feasibility checks come from `engine.py`
(Python `Decimal`). If Gemini is unavailable the app still runs fully, using
regex extraction and templates.

## Architecture on Google Cloud

```
Browser ──► Cloud Run (Streamlit container, asia-southeast1)
              │  service account: orderfit-run (least privilege)
              ├──► Gemini on Vertex AI (global endpoint, roles/aiplatform.user)
              └──► Secret Manager (optional API-key fallback)
Build: gcloud run deploy --source . → Cloud Build → Artifact Registry
```

## Code map

```
case_data.py      synthetic case + source documents
engine.py         deterministic Decimal engine: simulation, feasibility,
                  plan enumeration, constrained ranking, min-change probes
agent.py          stages A-E: Gemini extraction + verifier (regex fallback),
                  alerts, sensitivity scan, uncertainty rating, memo
gemini_client.py  Gemini client (Vertex AI or API key), structured
                  extraction, explanation, Q&A, verified draft polish
sandbox.py        permission gate (T0-T3), simulated bank, mock outbox,
                  mock lender portal, operation log
app.py            Streamlit UI
tests/            regression tests for the numbers + tests for the AI guards
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Gemini (optional locally). Either use Vertex AI with your own Google login:

```bash
gcloud auth application-default login
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=<your-project-id>
export GOOGLE_CLOUD_LOCATION=global
```

or set `GOOGLE_API_KEY` (AI Studio key). Never commit keys.

## Deploy to Cloud Run

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:orderfit-run@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
gcloud run deploy orderfit --source . --region asia-southeast1 \
  --service-account orderfit-run@<PROJECT_ID>.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=<PROJECT_ID>,GOOGLE_CLOUD_LOCATION=global \
  --allow-unauthenticated --session-affinity --memory 1Gi --max-instances 2
```

## 5-minute demo path

1. **Decision memo**: accepting as-is breaches the reserve on day 20; the
   50% customer advance is the cheapest feasible plan.
2. **Documents** expander: fields extracted by Gemini, each with its source
   span and the verifier result.
3. Move **customer payment day** to 75: the financing plans fail their
   day-61 repayment; the sensitivity scan shows where the answer flips.
4. Change **owner priority** to "do not depend on customer consent": the
   ranking changes and the agent explains why.
5. Tick **Inject instruction into the PO**: Gemini and the regex filter both
   flag it; the verdict does not change.
6. **Polish draft with Gemini**, then **Approve → Execute** in the sandbox
   and export the operation log.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## Limits and roadmap

- One synthetic business and one order at a time; documents are built in.
- Roadmap: PDF upload with **Document AI** for scanned orders, operation log
  and portfolio risk analytics in **BigQuery**, case store in **Cloud SQL**,
  more stress scenarios (partial payment, cancellation, FX shocks).
