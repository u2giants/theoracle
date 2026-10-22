# S09 question-current source composition — 2026-10-22

Branch `codex/parent24-s09-compose`. Compose head (pre-evidence): `0840ef24112d12017444bee9efb5164cd4e0e445`.
Parked S09 preserved head: `11221ea80e528bd4ef817c9866d0686d3ffb7182` on `origin/codex/parent24-question-current-01a16013`.
Current main base: `bf788080afa17bb1d69ffa576a77e5740ded82f3`.
Merge base of parked and main: `c187bfc36723ca891ad7558fe202a258ee2f27f8`.

## 1. Composed inventory vs parked head

Additive merge of `11221ea8` onto `origin/main` via `git merge --no-ff`.
Diff of composed HEAD vs parked head contains exactly the seven main docs files
(`HANDOFF.d/2026-10-22T1211Z-...md`, `docs/agents/03-documentation-map.md`,
five `plan_oracle_*.md` STATUS blocks). Every question source byte matches
parked `11221ea8`. No inverse downlevel, no omitted current-main files.

Complete question source (from `2adbba09` … `11221ea8`, 6 commits):

- `services/oracle-brain/sql/024_question_effects.sql` (367 lines) — SQL024
- `services/oracle-brain/oracle_brain/operating_model/`:
  `natural_question_v1.py`, `qualified_answer_v1.py`, `qualified_synthesis_v1.py`,
  `question_cost_settlement_v1.py`, `question_effect_public_v1.py`,
  `question_effects_v1.py`, `question_native_authority_v1.py`,
  `question_signals_v1.py`
- Hosting: `question_effect_factory_v1.py`, updated
  `replacement_result_service_v1.py` / `conversation_answer_v1.py` /
  `conversation_service_v1.py`
- Native/provider: `native_factory.py`, `native_provider.py`, `provider_adapter.py`,
  `raw_endpoint_inventory_v1.py`, `sdk_projection.py`, `retrieval/planner.py`
- Workflows: `answer.py` and `natural_answer_v1.py` thinned to forwarding;
  `qualified_synthesis_v1.py` created
- Shared contracts: `protected-question-effect-contract.ts`, updates to
  `protected-client-contracts.ts`, `protected-conversation-contract.ts`
- Web: `interview-panel.tsx`, `qualified-answer-view.tsx`,
  `replacement-question-effect.test.ts`, `question-effect-view-proof.ts`,
  `question-effect-wire-proof.ts`
- Tests: `test_question_effect_native_sql_v1.py`, `test_question_effects_sql_v1.py`,
  `test_question_effect_pricing_v1.py`, `test_question_effect_public_v1.py`,
  `test_question_vector_packing_v1.py`, `test_question_core_forwarding_v1.py`,
  `test_qualified_synthesis_v1.py`, updated `test_operating_model_verifier.py`
- `scripts/oracle2/verify_workflow_integrity.py` shard packing,
  `dev/oracle2/test_canonical_schema.py` `owned_phase_database`

### Canonical path presence

All canonical migration and registration paths remain present in the composition:
`020_meeting_capture.sql`, `024_question_effects.sql`, `027_legacy_migration.sql`
under `services/oracle-brain/sql/`, plus the full `001`–`027` inventory and the
main191/193 registration entries in `verify_workflow_integrity.py`
(`SYNTHETIC_MIGRATIONS` includes `020`/`024`/`027`).
Canonical SQL024 digest target `e6f956c47842e81237f24519f27f06ea644b265b086309753e412b6c5eaf91aa`
is unchanged (source bytes not modified in this compose).

### 11221 two-fix delta (retained as-is)

1. `test_question_effect_native_sql_v1.py`: fixture uses SAME
   `owned_phase_database`, restores exactly three temporary target/receipt
   envvars (`ORACLE2_TEST_ADMIN_URL`,
   `ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT`,
   `ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256`), proves child DB absent.
   Cost holds / once claims / per-case invented universe unchanged.
2. `replacement_result_service_v1.py`: diagnostic prefix renamed to
   “exact owned result service or fixed answer/question service required”
   while keeping the foreign-loop negative nonvacuous.

## 2. Capacity / population fit notes

W10 unchanged constraints: shared **120 seconds**, **ten workers**,
per-request ≤30, full mandatory population, **0 F/E/S** / no timeout /
no launch error / clean cleanup. No case cuts, no budget raises.

Current `verify_workflow_integrity.py` documentary packing after this compose
(nine documentary workers + one event worker = ten):

| Worker | Suites | Question placement |
|---|---|---|
| documentary-01 | 55 | 5 pure question suites + `question_effects_sql_v1` |
| documentary-02 | 35 | — |
| documentary-03 | 35 | — |
| documentary-04 | 29 | `question_effect_native_sql_v1` |
| documentary-05 | 51 | — |
| documentary-06 | 18 | — |
| documentary-07 | 8 | — |
| documentary-08 | 2 | — |
| documentary-09 | 43 | `qualified_workspace_sdk_sql_v1`, `question_selection`, `qualified_workspace_v1`, `natural_business_question_v1` |
| event | (EVENT list) | — |

**Total documentary suites: 276.**

Prior measured/estimated anchors (unchanged, not acceptance):

- question SQL module ~39 s, question native module ~64 s (PR191 run 39758616744).
- documentary-01 estimate ~114 s; documentary-04 ~109 s; documentary-06 ~116 s.
- Coherent journey path ~81–84 s (extraction/assembly/assessment/compile/
  summary/embedding/projector/restart/currentness).
- Correct positive coherent path estimate `doc06 ~120.152 s`
  (failed 52.186 − 15.723 + prior 83.689) — **tightest fit risk**.
  A TLS diagnostic fix alone cannot establish fit; full CI decides.
- `doc06` carries `purpose_coherent_native_journey` plus its measured siblings.

Fit risk assessment: **doc06 remains at/over the 120 s ceiling on paper**.
No cases were cut and no budgets raised. S11 one-admin setup batching is one
unmeasured candidate for setup savings but is NOT applied here.

## 3. TLS diagnostic instrumentation (source-only)

Separate issue: coherent-native actual TLS handshake failed after
`census_committed` 3.369 s. Expected retained CA1 cryptographically signs the
retained server certificate; actual peer DER/address was not recorded. Missing
late-extraction wire is secondary settlement failure, not original cause.

Applied **source-only** instrumentation in `dev/oracle2/test_graph_tls_fixture.py`:

- `owned_graph_tls`: records actual numeric `getpeername()` **before**
  `wrap_socket`, and peer DER SHA-256 **only on successful handshake**.
  Failed wrap records `handshake_failed` with error type and no DER hash.
  Post-handshake failures record `post_handshake_failed` so they are never
  blamed on TLS. Optional `diagnostics=` list parameter for callers.
- `verify_graph_tls_peer`: same pattern on the client preflight
  (`client_handshake_succeeded` / `client_handshake_failed`).

Constraints preserved:

- No global SSL patch, no fallback, no retry.
- Exact CA/SNI/pins unchanged (`ssl.create_default_context(cafile=…)`,
  `server_hostname='localhost'`, URI pin comparison unchanged).
- Dual-family loopback listener hypothesis remains **plan-only, not executed**.
  No production, no company data, no paid provider effects.

## 4. Pure check results

Ran the five pure question suites (the current-main equivalents of the 18
retained pure checks — 62 parametrized cases across 17 test functions after
parametrization expansion):

```
tests/test_question_core_forwarding_v1.py     3
tests/test_question_effect_pricing_v1.py     26
tests/test_question_effect_public_v1.py       5
tests/test_question_vector_packing_v1.py      9
tests/test_qualified_synthesis_v1.py         13
```

**Result: 62 passed, 0 failed, 0 errors, 0 skipped, 2.64 s.**

Environment note: `hnswlib` (via `graphrag-sdk`) cannot build on this Windows
host (no MSVC 14.0+). Pure checks ran in an isolated venv with
`graphrag-sdk` installed `--no-deps` plus a stub `hnswlib` module used **only**
for import collection. No SQL / native / Next proof was executed. Full W10 was
NOT run.

## 5. Remaining gate

Not proved here; all of the following stay open:

1. **Fresh complete source review** of this composed head (exact bytes, all
   shared owners included — not thin forwarders).
2. **Reopen #192 only from fresh complete source on current main** — do not
   reuse PR192’s failed run 39760744903 or its source `32f6272`.
3. **Full CI** on the reopened PR: all ten workers, 120 s, 0 F/E/S, no timeout,
   launch, or cleanup error; every mandatory case present.
4. **Root merge** and **post-main exact proof** — including the actual
   native/SQL/Next natural `019→024→Budget→SDK` path with permission/once/cost/
   error controls, and the coherent-native TLS path with the new diagnostics
   recording actual numeric peer and DER hash.
5. Separate coherent-native TLS root-cause diagnosis (actual peer DER/address
   now recorded on next attempt; root diagnostic assignment was NOT started).
6. Separate business-acceptance hold remains. Genuine failed proof is not
   erased by an earlier green receipt. Native-v2 permission is NOT renewed.
   No API substitution for browser. No production / company data / paid
   provider effects.

## 6. Hard constraints checklist

- [x] Own worktree (`C:\tmp\s09-compose-work\s09-compose`), branch only
- [x] `ai-task-gates start --class code` before writes
- [x] Additive composition; all canonical 020/024/027/main191/193 paths present
- [x] No case cuts, no budget raises
- [x] TLS instrumentation source-only; no global SSL patch/fallback
- [x] Dual-family loopback left as unexecuted plan (this document §3)
- [x] Pure checks only; full W10 NOT run; no SQL/native/Next execution
- [x] Commit as Albert Hazan `<u2giants@users.noreply.github.com>`
- [x] Safety gates and business-acceptance hold preserved
- [x] Failed proof not overwritten with an earlier green receipt
- [x] Native-v2 permission not renewed; no API-for-browser substitution
