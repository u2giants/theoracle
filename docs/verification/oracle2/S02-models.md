# S02 model evaluation — synthetic corpus only

Run 2026-09-28, about 10:00 AM EDT (retry of two primary cases shortly after). Posted by Claude chat unknown on edge-dev3.

**This is a synthetic-only diagnostic, not a business-quality claim.** Only the 30 invented `question` records from `evals/oracle2/synthetic-cases.jsonl` (20 `A`, 10 `D`) were sent. No company data, nothing from Supabase. The 12 `F` parser fixtures are not business questions and were not sent. Scores are automated proxies; the S01 blinded human review (acceptance-spec.md) has not been performed, so the §10.3 thresholds (19/20 etc.) are **not** claimed as met by either model.

## Model resolution

Listing APIs called 2026-09-28 (EDT) with keys from 1Password `vibe_coding`:
- Anthropic `GET https://api.anthropic.com/v1/models` — returned current IDs including `claude-opus-5-5`, `claude-sonnet-5`, `claude-haiku-4-5-20251001`.
- OpenAI `GET https://api.openai.com/v1/models` — returned dated snapshots including `gpt-5.5-2026-04-23`, `gpt-5.4-2026-03-05`.

Choice: the research doc names no generation model; candidates come from `packages/ai/src/routes/catalog.ts` (Anthropic primary routes, OpenAI secondary).
- **Primary: `claude-sonnet-5`** (Anthropic; a fixed model ID in Anthropic's listing — Anthropic no longer issues a separate dated alias for this generation).
- **Fallback: `gpt-5.5-2026-04-23`** (OpenAI dated snapshot; called with `reasoning_effort=low`).

Caps: `max_tokens` 1200 (Anthropic), `max_completion_tokens` 2400 (OpenAI). Total tokens: primary 17,560, fallback 8,483.

## ProcessingApproval scope

Default-deny `oracle_brain.provider_policy.dispatch` admitted every call. Two approvals, created in-process for the run only:
provider `anthropic` (fallback=false) and `openai` (fallback=true); account `oracle-eval`; endpoint the exact messages/chat-completions URL; `data_classes = {"synthetic"}`; purpose `s02-model-evaluation`; `terms_hash` = SHA-256 of the provider commercial-terms URL; expiry two hours after start (`2026-09-28T16:03:35.853487Z`); register_ref this file. Unit tests prove a non-synthetic data class or unapproved provider is refused.

## Scoring (proxy for the S01 rubric)

A case passes when: JSON parsed; every citation resolves to a supplied span (source resolution); abstain/answer mode matches `expectation`; and at least 50% of the required-fact key terms appear in the answer. Forbidden-inference, usefulness and improvement-contract checks require the human review and are not scored here.

| | Pass | A split | D split | Citations resolve | Mode match |
|---|---|---|---|---|---|
| Primary `claude-sonnet-5` | 21/30 | 15/20 | 6/10 | 30/30 | 25/30 |
| Fallback `gpt-5.5-2026-04-23` | 20/30 | 16/20 | 4/10 | 30/30 | 29/30 |

Both models cited only supplied spans (100% resolution) on every case. Primary more often answered where an answer was expected but chose abstention (A07, A19, D04, D06, D09); fallback was terser, so term coverage failed more often. Two primary calls (A18, A19) returned transient HTTP errors in the first run and were rerun once with the same inputs; results are in `S02-models-results.json`.

| Case | Category | Expect | Primary | Fallback |
|---|---|---|---|---|
| A01 | procedure_ownership | answer | PASS (cite y, mode y, cov 0.86) | PASS (cite y, mode y, cov 0.57) |
| A02 | procedure_ownership | answer | PASS (cite y, mode y, cov 0.67) | PASS (cite y, mode y, cov 0.5) |
| A03 | procedure_ownership | answer | PASS (cite y, mode y, cov 0.67) | PASS (cite y, mode y, cov 0.67) |
| A04 | procedure_ownership | abstain | PASS (cite y, mode y, cov 0.86) | PASS (cite y, mode y, cov 0.71) |
| A05 | conditional_exception | answer | PASS (cite y, mode y, cov 0.64) | PASS (cite y, mode y, cov 0.55) |
| A06 | conditional_exception | answer | PASS (cite y, mode y, cov 0.57) | PASS (cite y, mode y, cov 0.57) |
| A07 | conditional_exception | answer | fail (cite y, mode n, cov 0.83) | PASS (cite y, mode y, cov 0.67) |
| A08 | conditional_exception | answer | PASS (cite y, mode y, cov 0.8) | PASS (cite y, mode y, cov 0.8) |
| A09 | cross_department | answer | PASS (cite y, mode y, cov 0.71) | PASS (cite y, mode y, cov 0.71) |
| A10 | cross_department | answer | fail (cite y, mode y, cov 0.44) | fail (cite y, mode y, cov 0.44) |
| A11 | cross_department | answer | PASS (cite y, mode y, cov 0.8) | PASS (cite y, mode y, cov 0.8) |
| A12 | cross_department | answer | PASS (cite y, mode y, cov 0.7) | PASS (cite y, mode y, cov 0.7) |
| A13 | historical_change | answer | PASS (cite y, mode y, cov 1.0) | PASS (cite y, mode y, cov 1.0) |
| A14 | historical_change | answer | PASS (cite y, mode y, cov 0.78) | PASS (cite y, mode y, cov 0.56) |
| A15 | historical_change | abstain | PASS (cite y, mode y, cov 0.5) | PASS (cite y, mode y, cov 0.5) |
| A16 | improvement_decision | answer | PASS (cite y, mode y, cov 0.55) | PASS (cite y, mode y, cov 0.55) |
| A17 | improvement_decision | abstain | fail (cite y, mode y, cov 0.44) | fail (cite y, mode y, cov 0.33) |
| A18 | improvement_decision | answer | PASS (cite y, mode y, cov 0.75) | PASS (cite y, mode y, cov 0.75) |
| A19 | improvement_decision | answer | fail (cite y, mode n, cov 0.33) | fail (cite y, mode y, cov 0.22) |
| A20 | improvement_decision | abstain | fail (cite y, mode y, cov 0.33) | fail (cite y, mode y, cov 0.17) |
| D01 | procedure_ownership | answer | fail (cite y, mode y, cov 0.4) | fail (cite y, mode y, cov 0.4) |
| D02 | procedure_ownership | answer | PASS (cite y, mode y, cov 0.83) | PASS (cite y, mode y, cov 0.83) |
| D03 | conditional_exception | answer | PASS (cite y, mode y, cov 0.5) | fail (cite y, mode y, cov 0.25) |
| D04 | conditional_exception | answer | fail (cite y, mode n, cov 0.5) | fail (cite y, mode y, cov 0.25) |
| D05 | cross_department | answer | PASS (cite y, mode y, cov 0.67) | PASS (cite y, mode y, cov 0.83) |
| D06 | cross_department | answer | fail (cite y, mode n, cov 0.67) | fail (cite y, mode n, cov 0.67) |
| D07 | historical_change | answer | PASS (cite y, mode y, cov 0.5) | PASS (cite y, mode y, cov 0.5) |
| D08 | historical_change | abstain | PASS (cite y, mode y, cov 1.0) | fail (cite y, mode y, cov 0.0) |
| D09 | improvement_decision | answer | fail (cite y, mode n, cov 0.5) | fail (cite y, mode y, cov 0.25) |
| D10 | improvement_decision | abstain | PASS (cite y, mode y, cov 0.6) | PASS (cite y, mode y, cov 0.6) |

## Reproduce

```
op run --env-file <env with ANTHROPIC_API_KEY/OPENAI_API_KEY op:// refs> -- \
  python scripts/oracle2/evaluate_models.py --primary anthropic:claude-sonnet-5 \
  --fallback openai:gpt-5.5-2026-04-23 --out results.json
```
Offline tests: `python -m unittest scripts/oracle2/test_evaluate_models.py` (with `services/oracle-brain` on PYTHONPATH).
