# Workflow-read model bake-off

## R2 responsibility-path decision — 2026-08-06

Purpose: execute the owner-approved bounded model bake-off after the deeper responsibility reader
scored 12/30. The fixture, `licensed-team-responsibilities-v1` answer key, `field-aware-v3`
matcher, 27/30 threshold, strict evidence policy, reader budgets, post-pass limits, and disabled
merge/apply controls remained frozen.

### Production snapshot and eligibility

- Original primary: `openai/gpt-4.1`.
- Original pool: `openai/gpt-4.1`, `anthropic/claude-sonnet-5`,
  `google/gemini-2.5-pro`.
- `business_model_merge_enabled=false`; `business_model_apply_enabled=false`.
- `business_objects=0`; `business_object_versions=0`; `business_model_changes=0`.
- GPT-4.1 was eligible: structured output, strict JSON Schema, deep schema accepted, and adapter
  parameters safe were all true.
- Claude Sonnet 5 and Gemini 2.5 Pro were skipped as ineligible because production capability data
  has `deep_schema_accepted=false` for both. No fallback or forced bypass was used.

The existing pinned disposable document `c4ba034f-fb6c-40ee-a98e-fd20166a438b` was reused. Each
run forced a new immutable source map over the unchanged five persisted chunks; runs were serialized
and the source content hash remained `2b0adcd617790033b4f8759a7c7998b911336917951e38a29f6d097ef16661f5`.

### Candidate results

| Candidate | Run | Trigger run | Map | Score | Responsibilities | Kept / dropped | Calls / input / estimated cost |
|---|---:|---|---|---:|---:|---:|---|
| `openai/gpt-4.1` | 1 | `run_06ftfd4h0b8erk4pr99u2hlg01` | `5f1491c7-e38b-4c07-a063-121244215dda` | 11/30 | 79 | 395 / 164 | 23 / 58,923 / $0.294615 |
| `openai/gpt-4.1` | 2 | `run_06ftffk1dpavmptpve978aot01` | `14724714-edc1-4012-a932-44cfd6c8ed23` | 12/30 | 81 | 350 / 148 | 22 / 55,620 / $0.278100 |
| `anthropic/claude-sonnet-5` | — | — | — | ineligible | — | — | `deep_schema_accepted=false` |
| `google/gemini-2.5-pro` | — | — | — | ineligible | — | — | `deep_schema_accepted=false` |

Both scored runs used only `openai/gpt-4.1`; their final model attempts were successful and used
prompt `responsibility-read-v2.4-span-bound`. Mean score: **11.5/30**. Spread: 1 point.

## DECISION 2026-08-06 workflow_read / R2 responsibility path

- Result: bake-off failed (`11.5 <= 23`).
- Frozen rule applied: require deeper architecture; no second bake-off.
- Production settings restored to the original primary and three-model pool with correct JSON
  encoding.
- Merge/apply remained false and all three durable business-model tables remained empty after the
  runs.

### Deviations and operational notes

- The first settings write was immediately detected as double-JSON-encoded on read-back and
  corrected before scoring. Run 1 counts because its durable attempts prove every call used
  GPT-4.1 successfully after the corrected single-model state; no fallback occurred.
- The R2-specific frozen responsibility document was re-read with `force=true` rather than deleting
  its chunks and downstream claims. This preserved the identical source while producing fresh,
  immutable superseding maps and avoided unrelated claim-pipeline mutations.

