# Trend2Line — rules for every coding session

## Hackathon constraints (non-negotiable)
- Runtime AI is **Gemini only** (google-genai SDK). Never add another model provider's SDK.
  `scripts/check_no_anthropic.sh` runs before every deploy and fails the build if one appears.
- Deploy target: **Cloud Run**, region asia-south1. Nothing hosted elsewhere.
- All code written fresh inside the hackathon window. No code copied from employer projects.
- Only synthetic or public data. No client data, ever.

## Architecture rule
The LLM interprets; code computes. Gemini may: pick the Wikipedia article, turn a trend/photo into a
ProductSpec, and write the narrative. Everything numeric, every date, line capability, allergen and rule
comes from deterministic code over the tables in data/. The verdict is decided in code; the writer
explains it and cannot change it.

## Google APIs move fast
Vertex AI was renamed Gemini Enterprise Agent Platform in April 2026. Model IDs and env var names change.
When unsure about a Google API, ask for the current docs page instead of guessing. Pin versions.

## Working agreements
- Keep `pytest -q` green. Add a test for every new deterministic rule.
- Every new tool output goes through EvidenceRegistry.record(); every new claim kind needs a verifier check.
- MOCK_LLM=1 must keep working (offline demo + CI).
