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

### Second diagnosis — CI run 39842552937 (first repack 4fe1227a)

Result: `tests: 4677, skipped: 0, success: false`. Full main baseline is 5370.
Gap = 693 tests. Artifact `workflow-integrity.json` worker_results shows
`documentary-09: junit_present: false` — the only worker that did not write
JUnit. All nine other workers completed and wrote JUnit (687+659+448+560+1602+
386+76+53+206 = 4677). `documentary-09.stdout` shows progress to ~90 % then a
hard cut (pytest killed at the shared 120 s deadline); one `F` at 45 % is
unattributed because JUnit was never written.

Root cause: the first repack placed `conversation_native_sql` on documentary-09
(`_place_suites(..., 'paid_sdk_embeddings_v3', after=True)`). Main's packing
deliberately keeps `conversation_native_sql` on documentary-03 — the PR191
comment on main records that documentary-09 previously exhausted at 794/795
cases and the 14-case native module was moved to documentary-03 to fix it.
Moving it back to documentary-09 re-created that timeout.

### Second fix (this commit)

Registration/placement only. Removed the `conversation_native_sql →
paid_sdk_embeddings_v3` override so the suite stays on documentary-03 (the
PR191 / main home). `qualified_workspace_sdk_sql_v1` remains on documentary-03.
No test bodies, budgets, or case counts changed.

Packing after this fix (nine documentary + one event = ten workers):

| Worker | Suites | Notable placement | Est. wall (s) |
|---|---|---|---|
| documentary-01 | 55 | 5 pure question suites | ~110 |
| documentary-02 | 35 | — | ~107 |
| documentary-03 | 36 | `conversation_native_sql`, `qualified_workspace_sdk_sql_v1` | ~118 |
| documentary-04 | 29 | `question_effect_native_sql_v1` (~61 s) | ~113 |
| documentary-05 | 51 | — | ~113 |
| documentary-06 | 18 | `purpose_coherent_native_journey` (~81 s), factory v1 | ~117 |
| documentary-07 | 8 | `consolidation_next_auth_browser_v1` | ~110 |
| documentary-08 | 2 | `question_effects_sql_v1` (~38 s) | ~117 |
| documentary-09 | 42 | main's doc09 (no `conversation_native_sql`) | ≤120 |
| event | 22 | — | ~97 |

**Total documentary suites: 276.** Population 298 suites across 10 workers.

Counts before → after: CI 4677 (doc09 missing) → expected 5370 (full main
baseline). Local collection after first fix was 5450 (5314 mapped + 136
Windows-only); mapped Linux population is the 5370 baseline.

Fit risk: documentary-03 (~118 s with both `conversation_native_sql` ~16 s and
workspace ~15 s) is the tightest. documentary-09 restores main's proven 42-suite
set. Whole CI decides fit; prior timing estimates are not acceptance.

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
   reuse PR192's failed run 39760744903 or its source `32f6272`.
3. **Full CI** on the reopened PR: all ten workers, 120 s, 0 F/E/S, no timeout,
   launch, or cleanup error; every mandatory case present. The second packing
   fix (this commit) must produce the full 5370 population with documentary-09
   writing JUnit. The `F` observed at 45 % in doc09's killed stdout is
   unattributed until JUnit is written; it is a genuine open question, not
   erased.
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

## 5a. Run 39846165685 diagnosis — zero test failures, timeout accounting defect

CI run 39846165685 (branch `codex/parent24-s09-compose`, commit `b1edb626`)
executed the complete 5472-test population. JUnit evidence shows **zero
failed, errored, or skipped tests** across all ten workers. Every worker's
stdout ends with `N passed`. The `success: false` verdict comes entirely from
`evidence_errors: ["worker did not complete successfully" ×10]`.

Root cause: `run_test_groups` used a single shared `timed_out` boolean. When
documentary-03's wall clock (119.44 s pytest + process overhead) exceeded the
shared 120-second deadline, the `break` path set `timed_out=True` and that
one flag was stamped onto every worker — including event (97.24 s) and
documentary-09 (105.88 s) which finished well within budget. A post-loop
`if time.monotonic()>deadline` check further marked all workers timed out
even when each individual `wait()` had returned successfully.

Two source fixes in this commit:

1. **Per-worker timeout tracking** in `run_test_groups`: each worker's
   `timed_out` is now computed from its own `wait()` outcome against the
   shared deadline. Workers that completed before the deadline are no longer
   marked timed out because a sibling was slow. The blanket post-loop clock
   check is removed; the per-worker `wait(timeout=remaining)` already
   enforces the deadline.
2. **Rebalance** `source_processing_qualification` (5.48 s measured) from
   documentary-03 (118.1 s) to documentary-02 (105.0 s → 110.5 s). This
   brings documentary-03 to ≈112.6 s pytest, under the 120 s wall-clock
   ceiling with process overhead. Population, ten workers, and the 120 s
   deadline are unchanged. No case cuts, no budget raises.

The known S07 Create-child failure (protected channel 503 during exchange)
did **not** reproduce in this run — `test_actual_independent_V2_processes_Create_to_unattended_STOP_terminal_receipt`
passed (40.88 s). It remains the known inherited main failure and is not
treated as fixed.

Slowest tests retained as-is (real-clock semantics, not defects):
- `test_purpose_coherent_native_journey::test_coherent_native_census_uses_real_prior_input_parent` — 80.71 s (full multi-phase journey)
- `test_meeting_unattended_sql::test_actual_independent_V2_processes_Create_to_unattended_STOP_terminal_receipt` — 40.88 s (capture-window expiry)
- `test_purpose_worker_startup` — 78.98 s (intentional 5 s deadline/horizon sleeps)

## 6. Hard constraints checklist

- [x] Own worktree (`C:\tmp\s09-compose-work\s09-compose`), branch only
- [x] `ai-task-gates start --class code` before writes
- [x] Additive composition; all canonical 020/024/027/main191/193 paths present
- [x] No case cuts, no budget raises
- [x] TLS instrumentation source-only; no global SSL patch/fallback
- [x] Dual-family loopback left as unexecuted plan (this document §3)
- [x] Pure checks only; full W10 NOT run; no SQL/native/Next execution
- [x] Second packing fix is registration/placement only (conversation_native_sql
      restored to documentary-03; no test body / budget / case changes)
- [x] Third fix: per-worker timeout tracking + source_processing_qualification
      rebalance (no case cuts, no budget raises, no guard weakening)
- [x] All 5472 tests confirmed passing in run 39846165685 (0 F/E/S)
- [x] Commit as Albert Hazan `<u2giants@users.noreply.github.com>`
- [x] Safety gates and business-acceptance hold preserved
- [x] Failed proof not overwritten with an earlier green receipt
- [x] Native-v2 permission not renewed; no API-for-browser substitution
