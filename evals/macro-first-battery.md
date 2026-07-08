# Macro-First Battery / Gate Log

Append-only record for `MACRO_FIRST_REDESIGN.md` stage gates and acceptance-battery
runs.

## 2026-07-07 — Stage 2 Workflow Reader Gate — canonical swimlane fixture

Fixture: document `9d09fa89-3a46-465e-a98b-837287c9e22a`, `Pop Creations Flow 12112025 (1).png`.

Scope note: the destructive clean re-ingest path was blocked by the repo's provenance
guard before deletion: the document's old claims had 1 Brain citation and 2 gap
references. To preserve provenance, this gate ran `source-workflow-read` directly
against the existing persisted chunks and did not wipe the document.

Runs:

- `run_cmra2epx05qke0kmvp80vlrmd`: first workflow read, `validated`, map
  `5e120c73-2890-4627-acaf-b35857ae42d7`, `keptCount=151`, `droppedCount=0`.
- `run_cmra2g75q5z1m0wmvs9b47pz9`: same-content redispatch, `skipped_existing`
  against map `5e120c73-2890-4627-acaf-b35857ae42d7`.
- `run_cmra2gfri5u5l0mmzn7adxwj0`: forced rerun, `validated`, map
  `2615f242-897b-4724-9091-6e08108aec63`, old map superseded.
- `run_cmra2iihl5v400mmzp0rich66`: controlled failure with a deliberately invalid
  workflow-read route, failed loudly, wrote a failed map, and set
  `documents.macro_health='failed'`.
- `run_cmra2j6p95vxv0imzxsmqvsly`: restored settings and repaired the fixture,
  `validated`, map `86f33611-9bce-4f65-be2a-702c288ea478`.
- `run_cmra2ork561l00jonzlrqxfcv`: final run after making OpenAI primary,
  `validated`, active map `72ed0ef9-8ea7-4e60-84a3-a7e9236eb7c8`,
  `nodes=63`, `edges=71`, `lanes=14`, `paths=1`, `keptCount=149`,
  `droppedCount=0`.

Final DB state:

- `documents.status='complete'`, `documents.macro_health='complete'`,
  `processing_error IS NULL`.
- Exactly 1 non-superseded source workflow map remains for the document:
  `72ed0ef9-8ea7-4e60-84a3-a7e9236eb7c8`.
- Final active map attempt used `openai/gpt-4.1` as primary and succeeded.
- Prod settings now read:
  `default_workflow_read_route='openai/gpt-4.1'`;
  `model_pool_workflow_read=['openai/gpt-4.1','anthropic/claude-sonnet-5','google/gemini-2.5-pro']`.

Answer-key coverage, scored against `fix_enhancement.md` section 2.1:

- Stage-group recall: 9/9. The active map includes buyer engagement, creative
  direction, design execution, costing/factory sourcing, new-vs-existing branching,
  tech-pack revision loop, licensor concept approval, sampling/PPS audit, and
  order/production/shipment.
- Branch/loop recall: pass. The active map includes buyer price approval,
  new-vs-existing product branches, licensor legal-line/packaging vs creative-design
  branches, PPS audit pass/fail, re-sampling, and ship-to-US terminal flow.
- Systems recall: pass. The map includes DFlow, RFQ, ClickUp, ColdLion, MasterData,
  SKU creation, and PPT/library references.
- Lane/owner recall: pass. The map captured 14 lanes, including the expected
  Buyer/Sales/Creative/Technical/Junior/Sourcing/Production/Carlos/Gina/Licensing/
  Licensor/Factories roles. This exceeds the original rough 9-lane answer-key
  grouping because the diagram has additional named swimlanes/roles.
- Validation survival: pass. Final run kept 149/149 emitted elements after
  deterministic validation (`droppedRatio=0`), above the Stage 2 >=90% gate.

Gate result: PASS with one limitation. The full destructive re-ingest portion of the
gate was not run because provenance guards correctly blocked deleting live cited
claims. The workflow-reader, validation, same-hash idempotency, supersede semantics,
failure visibility, final health restoration, and route setting hardening were all
verified live.

## 2026-07-07 — Stage 2 Reader-Failure Fallback Gate (deviation #1)

Proves the `require_workflow_map_for_ingestion` fallback branch inside
`processDocument()` — NOT reachable via the standalone `source-workflow-read` task,
so this gate runs FULL `document-ingestion`. The canonical fixture `9d09fa89…` is
blocked by the provenance guard, so a disposable duplicate was used.

Fixture: disposable duplicate doc `6491a849-95a2-49cb-b919-b3d95b9d33bc`
(`Licensed Team Responsibilities 2 - tagged.txt`, 5 chunks, 0 provenance blockers).
A second duplicate `5fc17b22-…` was left untouched (had Brain/contradiction/gap
blockers). Failure forced by setting `default_workflow_read_route` +
`model_pool_workflow_read` to `openai/forced-failure-nonexistent`.

Runs (deployed worker `20260707.3`):

- `run_cmrayd1er9lyh0ilq800q321f` (`require=false`): **PASS**. Trigger `completed`;
  doc `status='complete'`, `macro_health='map_failed'`, `processing_error` starts
  `DEGRADED — source workflow map failed: extraction continued without map guidance
  because require_workflow_map_for_ingestion=false`, `claim_count=6`,
  `source_workflow_maps` has 1 `failed` row.
- `run_cmraym76g9kl60plwtflae0bp` (`require=true`): doc correctly `status='failed'`,
  `claim_count=0`, extraction blocked. Contract MISS: `processing_error` was the raw
  `ModelCapabilityError`, not the `Source workflow read failed:` prefix — the outer
  task `run` catch overwrites `documents.processing_error` with the raw thrown error
  (pre-existing bug, first exposed here).
- `run_cmrayo7v69dwe0pn91x5mme9d` (restored route, cleanup): `completed`, real
  `degraded` map, `claim_count=26` — confirms route settings were restored to a
  functional model (a nonexistent route cannot produce a map).

Fix: commit `e6a5e07` re-throws `new Error(processingError)` in the strict branch so
the outer catch preserves the prefix; `verify:document-ingestion-fallback` now
asserts both branches. Deployed `20260707.4` (`mq239ok5`, 27 tasks). Settings
restored to `default_workflow_read_route='openai/gpt-4.1'` +
`model_pool_workflow_read=['openai/gpt-4.1','anthropic/claude-sonnet-5','google/gemini-2.5-pro']`,
`require_workflow_map_for_ingestion=false`.

Gate result: PASS. `require=false` (the actual point of deviation #1 — degrade
instead of halting all ingestion) is proven correct and live. The strict-path error
message was fixed and redeployed; that fix's contract is covered by the automated
gate but has not been re-run live against prod (low risk — cosmetic error text on
the non-default path; the document still correctly fails).

## 2026-07-07 — Stage 3 Map-Directed Extraction Gate Attempt

Scope: Stage 3 shipped code + prod migration + Trigger deploy, then attempted the
canonical fixture gate.

Implementation/deploy state:

- Prod migration `89_map_directed_extraction_cleanup.sql` applied via the current-prod
  Supabase session pooler.
- Verification query: six dead lens/outline settings count = `0`;
  `map_directed_extraction_enabled=true`; `jsonb_typeof(value)='boolean'`.
- Trigger prod worker deployed as version `20260707.5`, deployment `s2if9yzf`, with
  23 detected tasks. Current worker no longer registers `source-outline`,
  `document-lens-extraction`, `macro-relationship-extraction`, or
  `source-coverage-audit`.

Local gates:

- PASS: `corepack pnpm -r typecheck`
- PASS: `corepack pnpm --filter @oracle/engines run verify:macro-first`
- PASS: `corepack pnpm --filter @oracle/engines run verify:r5` (includes Stage 3 map
  dedup smoke)
- PASS: `corepack pnpm --filter @oracle/workers run verify:source-workflow-read`
- PASS: `corepack pnpm --filter @oracle/workers run verify:document-ingestion-fallback`
- PASS: `corepack pnpm --filter @oracle/ai run verify:workflow-read`
- PASS: `git diff --check`

Canonical fixture gate:

- Fixture: document `9d09fa89-3a46-465e-a98b-837287c9e22a`; active map
  `72ed0ef9-8ea7-4e60-84a3-a7e9236eb7c8`.
- Clean re-ingest remains blocked by provenance guard. Dry-run
  `scripts/reevaluate-document.mjs` reported 3 blockers: 1 Brain citation and 2 gap
  references. No force-delete was attempted.
- Deployed worker run `run_cmrb30q0wbnva0mof8d1jguk5` completed but no-oped:
  `chunksInserted=0`, `candidatesStaged=0`, `claimsPromoted=0`,
  `duplicatesAppended=0`, `rejections=0`.
- Current-state measurement after the no-op run: active map has 63 nodes + 71 edges
  = 134 map elements; current document has 652 promoted claims, 0 mapped claims,
  0/134 map elements evidenced by `mapElementRef`, max same-element claim count 0.

Gate result: BLOCKED for the numeric claim-quality target, because the canonical
fixture cannot be clean-reset without resolving live Brain/gap provenance references.
The implementation, cleanup migration, worker task deletion, and deployment gates
passed. The actual numeric target still needs a clean re-ingest after provenance is
resolved through normal admin review.

### 2026-07-07 — Stage 3 clean re-ingest gate + vision A/B (UNBLOCKED; coverage FAIL, root-caused)

Owner confirmed the app is NOT launched: the fixture's Brain citation + gap refs were
disposable test artifacts, so a clean reset was authorized. Blockers cleared (scoped to
this doc's claims: 1 `section_claims`, 2 `gaps.related_claim_ids`, plus newer FK rows
the reset helper's guard MISSES — `macro_relationship_claims`, `source_outline_source_refs`,
`source_group_items`), then `APPLY=1 scripts/reevaluate-document.mjs` reset the doc and
re-ingest ran on worker `20260707.5`. All runs verified against Trigger run records.

**First clean re-ingest (gemini-2.5-flash vision, run `run_cmrb4ukrochnc0one92rsj3zc`):**
63 promoted claims (gate A ≤100 PASS); dedup max 1 claim/ref, 0 elements with 3+,
`duplicatesAppended=1` (gate C PASS); coverage 55/120 = 45.8% of the fresh map's
elements (gate B ≥95% FAIL). Overall FAIL on coverage.

**Vision A/B (identical fixture, only `default_vision_route` differs; both verified via
Trigger tags/output):**

| Metric | qwen3-vl (`run_cmrb5qi4…`) | gemini-2.5-flash (`run_cmrb5knp…`) |
|---|---:|---:|
| Transcription | 3 chunks, 9,340 chars; names Carlos, Gina | 3 chunks, 9,254 chars; mostly generic `[White Box]` |
| Fresh map | 58 nodes + 59 edges = 117; validated; kept 131/dropped 7 | 41 + 43 = 84; validated; kept 99/dropped 0 |
| Promoted claims | 43 (candidates 48, rej 5) | 48 (candidates 55, rej 7) |
| Coverage | 42/117 = 35.9% (gate B FAIL) | 34/84 = 40.5% (gate B FAIL) |
| Dedup (gate C) | max 1/ref, 0 with 3+, dup 0 — PASS | max 1/ref, 0 with 3+, dup 0 — PASS |
| Claims anchored to map | 42/43 (1 null ref, 0 orphan) | 34/48 (**14 null refs**) |
| Vision latency | 94.7s | 30.6s |

Decision: **keep `qwen/qwen3-vl-235b-a22b-thinking`** (richer map, better lane/owner
attribution, nearly all claims anchored vs 14 floating for flash). Prod
`default_vision_route` restored to qwen3-vl; pool already contained it.

**Gate A (≤100) PASS, C (dedup) PASS on both models. Gate B (coverage ≥95%) FAIL on
both — and it is EXTRACTION-limited, not vision-limited:** qwen produced a 117-element
map but extraction only PROPOSED ~48 candidates. Root cause (confirmed by reading
`document-ingestion.ts`): in map-directed mode the extraction prompt is
self-contradictory — the diagram note (`document-ingestion.ts` ~L819) still says the
PRE-map "Aim for FEWER, higher-altitude, CONNECTED claims" / "Do NOT emit a separate
claim for every box", while the request (~L865) says "at most one canonical claim" per
element (a ceiling, no floor). Since Stage 2 validates a verbatim quote for EVERY map
element, the evidence provably exists; the model is simply told to under-produce. Also
noted: high run-to-run variance (same fixture+model gave maps of 84–120 elements across
runs). Next: de-conflict the prompt (map-directed mode must instruct one claim per
listed node/edge, no sparse guidance) and re-run; escalate to deterministic map-element
seeding from the map's stored validated quotes if the prompt fix alone misses ≥95%.
