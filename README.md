# Smart Home Conversational Agent

I built a bilingual smart-home shopping assistant on the Google Agent Development Kit and Gemini. It recommends products with a real compatibility check, compares them, upsells, and refuses anything unsafe or off-topic. I ran it against a real catalogue: roughly 940 products exported from Bauhaus, one JSON per product.

The core idea is a clean split of responsibility. The LLM works out what the user wants, and deterministic Python decides the facts. Compatibility, comparison and upsell selection are all computed in code, never by the model. That is what makes compatibility something I can audit and trust, instead of a hallucination waiting to happen.

Most of the interesting work sits in the data layer, not the prompt. The export buries supported voice assistants inside a free-text German attributes blob, so I wrote an ingestion parser that mines them out and normalises them to a validated set of Alexa, Google Assistant and Siri. I checked it against the whole catalogue, 561 products with a valid assistant, reconciled against a raw scan. Retrieval is a structured filter first, then BM25: compatibility, category and price are hard constraints applied before ranking, so a requirement never gets ranked away. BM25 rather than vectors because the catalogue is small and the queries are keyword-ish, with a dense reranker as the documented path if it ever needs to scale.

Two things I treated as product decisions rather than features : I read that as product thinking, not architectural complexity. Two things I treated as product decisions rather than features. Upsell is the primary business metric, so I instrument it as an attach rate in the eval harness instead of leaving it as an untested line in a prompt. And safety spends zero tokens: a deterministic pre-model check hard-blocks wiring and installation questions in both English and German before the model is ever called, which is cheaper and impossible to prompt-inject around.

I come from a LangGraph background, and ADK's shared-state, tool-calling model mapped straight onto the same way of thinking, here as a single coordinator agent with typed tools and a lifecycle callback.
Deployed on GKE Autopilot with Terraform and Vertex AI via Workload Identity. Demo video in Deployment.
## Deployment (GKE Autopilot)



https://github.com/user-attachments/assets/0cd8c939-5869-43d3-8937-6712735063fa



The agent runs as a container on GKE Autopilot. All infrastructure is Terraform.

- **Infra as code:** Terraform provisions Artifact Registry, the Autopilot cluster, a runtime service account and IAM.
- **No API keys in the cluster:** Gemini is called through Vertex AI using Workload Identity. The Kubernetes service account impersonates a GCP service account with `roles/aiplatform.user`.
- **Build:** Cloud Build produces the image, so no local Docker is needed. The container runs as a non-root user.
- **Deploy:** `deploy.sh` builds, pushes, applies the manifests and waits for rollout.

### What the demo shows
- Tool calls in order: `search_products`, then `get_upsell_suggestions`, then the grounded answer
- The wiring question blocked by the deterministic guardrail (`guardrail_triggered` in session state)
- Traces: about 9 s end to end, with tools at 1 s and 2 ms. Most of the latency is the model calls, so streaming is the next step.

### Things that broke on the way (and fixes)
- **ADK origin check returned 403 on session creation:** made `--allow_origins` configurable via an `ALLOW_ORIGINS` env var.
- **Non-root container couldn't write ADK's runtime UI config:** gave the app user ownership of that one directory instead of running as root.
- **`gemini-flash-latest` returned 404 in europe-west3 on Vertex:** switched to the `global` endpoint. Pinning an explicit model version is the next step.
- **Catalogue path was relative to the working directory:** copied `data/` into the image to match the loader.

The cluster is torn down when not in use to avoid cost. Redeploy with `terraform apply && ./deploy.sh`.

## Architecture

```
   user turn ──►  before_model_callback  ──►  root LlmAgent (Gemini)  ──►  typed tools  ──►  in-memory catalog
   (EN or DE)     deterministic safety         detects language,            search /            (943 products,
                  guardrail: blocks            grounds every answer         check_compatibility  loaded once,
                  wiring/installation          in tool output,              compare / upsell     compatibility
                  before a token is spent      enforces upsell + domain                          parsed at load)
```

**Core principle:** the LLM decides *what the user wants*; deterministic Python tools decide
*the facts*. Compatibility, comparison and upsell selection are computed in code, never by the
model this is what makes compatibility correct and auditable instead of a hallucination risk.

### Key design decisions

- **Compatibility is parsed, not guessed.** The raw export stores supported voice assistants
  inside a free-text German `attributes` blob. An ingestion parser extracts and normalises them
  to a validated set {Amazon Alexa, Google Assistant, Apple Siri}. Verified against the full
  catalogue (561 products with a valid voice assistant; counts reconciled against a raw scan).
- **Retrieval = structured filter first, then BM25.** Compatibility, category and price are hard
  filters applied before ranking, so a constraint is never ranked away. Only the fuzzy free-text
  part of a query is ranked. BM25 (not vectors) because the catalogue is small and queries are
  keyword-ish; a dense reranker is the documented scale-up path.
- **Category is derived** from title keywords (the source has no category field). ~25% fall into
  an honest `other` bucket (hubs, actuators, sirens, miscellaneous) rather than being force-fit.
- **Upsell is derived and measured.** No upsell field exists in the data, so upgrades are pricier
  same-category compatible products and add-ons are cheaper same-category items. Upsell is the
  primary KPI and is reported as an attach rate by the eval harness.
- **Two-layer guardrails.** A deterministic `before_model_callback` hard-blocks electrical wiring
  questions (EN + DE) before spending a token, matching on word-stems and token boundaries so
  German separable verbs and conjugated forms are caught; the agent instruction handles softer
  semantic domain-deflection. Code-level filters can't be prompt-injected around; instruction handles the
  long tail.
- **Single coordinator agent + tools**, not a multi-agent tree three intents over one bounded
  catalogue don't justify orchestration overhead, and a single agent is far easier to evaluate.

## Setup & run

Requires Python >= 3.10.

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# product data: unzip the export into data/products/ (one JSON per product)
#   the loader reads data/products/info/*.json and skips macOS junk files

# auth: create smart_home_agent/.env with a Google AI Studio key
#   GOOGLE_GENAI_USE_VERTEXAI=FALSE
#   GOOGLE_API_KEY=your-key           (from https://aistudio.google.com/apikey)
```

Run the assistant:

```
adk web                                   # pick "smart_home_agent";
streamlit run app/streamlit_app.py        # or the Streamlit chat UI
```

Tests and evaluation:

```
pytest -q                                 # 20 deterministic unit tests (no API key needed)
python -m eval.run_eval                   # behavioural KPI eval (live with a key; deterministic checks without)
adk eval smart_home_agent eval/smart_home.evalset.json   # ADK-native trajectory eval
```

## Evaluation

Two complementary layers:

1. **`eval/run_eval.py` - business-KPI harness.** Scores compatibility correctness, guardrail
   block rate, language match, and **upsell attach rate** (the primary KPI). In a live run the
   upsell attach rate was **100%** on recommendation turns. (Note: the Google AI free tier caps
   daily requests, so a full live run may be quota-limited; the deterministic unit tests cover the
   same invariants without an API key.)
2. **`eval/smart_home.evalset.json` - ADK-native trajectory eval** for `adk eval`, checking the
   agent calls the right tools. Cleanly regenerated via the "Save as eval case" button in `adk web`.

## Project layout

```
smart_home_agent/
  agent.py              root_agent (ADK entrypoint) + guardrail wiring
  catalog/attributes.py parse + normalise compatibility from the German attribute blob
  catalog/loader.py     load/normalise 943 products (price, category, compatibility)
  catalog/retrieval.py  structured filter + BM25 ranking
  tools/recommend.py    search_products, check_compatibility, get_upsell_suggestions
  tools/compare.py      compare_products
  guardrails/callbacks.py  before_model_callback safety guardrail (EN/DE)
data/products/          product JSONs
eval/                   run_eval.py (KPI harness) + smart_home.evalset.json (ADK eval)
tests/test_tools.py     20 unit tests for the deterministic layer
app/streamlit_app.py    minimal Streamlit chat UI
```

## What I'd do with more time

- A Gemini/embedding reranker as an optional second retrieval stage, measured against BM25.
- Guardrails as an ADK Plugin (reusable across agents) rather than a single callback.
- Persisted sessions (DatabaseSessionService) and tracing to Cloud Logging / OpenTelemetry.
- Cross-category upsell affinity (e.g. bulb -> hub/bridge) and an LLM-as-judge check on upsell relevance.
- Embedding-based product categorisation to shrink the `other` bucket.
- A short "why this is compatible / why recommended" line on each suggestion, since transparency is a conversion lever.
- Guided discovery for undecided shoppers ("I want to start a smart home"), not just keyword lookup.

## Notes on the stack

Built on ADK 2.x / Gemini, Python 3.10+.
