# Trend2Line

Turns a viral food trend into a verified factory decision: can our lines make it, which existing
products would lose their allergen-free claims, how long to shelf, and how much consumer interest is
left when we get there. Every number in the recommendation is checked against recorded evidence.

Built for the Google Cloud AI Builder Cup 2026. Theme: **Manufacturing: Intelligent Operations & Industrial Efficiency**.

## What is real and what is not (read before the demo)

| Item | Status |
|---|---|
| Wikipedia pageviews (live mode) | Real, fetched live from the Wikimedia REST API |
| Pageviews with `MOCK_LLM=1` | **Synthetic** curves, labelled as such in the UI |
| `data/fad_reference.json` | **Placeholder** until you run `python -m scripts.build_fad_reference`. Verdicts are capped at CONDITIONAL until then |
| `data/plant.yaml`, `timeline.yaml`, `equipment_catalog.csv` | **Synthetic** demo factory. Your domain person should make the values realistic |
| `data/rules.csv` | Requirements written generically; every `source_url` is a TODO and `verified=false` until a person checks the regulation |
| `data/allergen_map.csv` | Common-knowledge mapping; review it |

## Run locally (no keys needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
MOCK_LLM=1 uvicorn app.main:app --reload --port 8080   # open http://localhost:8080
```

## Live mode locally

```bash
cp .env.example .env    # fill GEMINI_MODEL (current Flash ID from AI Studio) and GOOGLE_API_KEY
set -a && source .env && set +a
uvicorn app.main:app --reload --port 8080
```

## Deploy to Cloud Run

One-time setup, on a personal Google account and personal GCP project with billing enabled:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

First deploy, no key needed:

```bash
PROJECT_ID=YOUR_PROJECT_ID MOCK_LLM=1 ./deploy.sh
```

Go live. Store the AI Studio key in Secret Manager and let Cloud Run's runtime service account read it:

```bash
printf '%s' "YOUR_AI_STUDIO_KEY" | gcloud secrets create gemini-api-key --data-file=-
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
PROJECT_ID=YOUR_PROJECT_ID GEMINI_MODEL=YOUR_FLASH_MODEL_ID ./deploy.sh
```

If the deploy complains about service-account or Cloud Build permissions, paste the exact error into
your coding session; the fix is usually a single IAM binding.

## Layout

```
app/main.py            FastAPI: /, /healthz, /api/config, /api/run
app/pipeline.py        Stage orchestration, decision rules, writer/verifier loop
app/stages/            trend, bom, feasibility (allergen blast radius), compliance, timeline, verifier
app/llm.py             Gemini structured output, disk cache, mock mode
app/mock.py            Offline handlers (writer errs on draft 1 so the verifier is visible)
data/                  Knowledge tables (authoritative; the LLM never invents these)
static/index.html      UI
adk_app/               ADK wrapper for `adk web` traces (day-2 task, untested)
scripts/               Fad reference builder, Gemini-only guard
tests/                 pytest: deterministic core and end-to-end mock API
```

## Known limitations

- Wikipedia pageviews are a public proxy for demand, not social or sales data. The signal sits behind
  one function so a company could plug in its own data.
- Capture uses an exponential-decay model, `0.5 ** (T / half_life)`, relative to interest on the run date.
- Co-manufacturer capability and allergen handling are assumed, not modelled.
- There is no LLM judge for free-text claims yet; such claims are labelled assumptions.
