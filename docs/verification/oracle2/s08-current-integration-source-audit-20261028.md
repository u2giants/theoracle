# S08 current integration — composition, connector audit, registration and AST seal

Recorded: 2026-10-27 11:12 PM EDT (America/New_York), edge-dev (Windows).
Branch `parent24-s08-current-integration` from genuine `origin/main`
`489dd987f96d613be9e0546d4a772ab665b584a4` (2026-10-27 handoff tip). Worktree
`C:\tmp\oracle-s08-int-r1`. Task class `code` declared before writes
(`ai-task-gates start --class code`, base `489dd987f96d`). Commit identity
`Albert Hazan <u2giants@users.noreply.github.com>` verified via
`git var GIT_COMMITTER_IDENT`.

Scope: closeout ledger §6 step 7 (S08 complete current integration). Synthetic
and invented data only. No company originals, no production writes, no paid
providers, no real meetings. **Real Teams chat/audience producer and real
invitation/producer qualification remain UNQUALIFIED** — every participation
fact below is fixture-invented; ACK never equals a visible message or provider
idempotency. Business acceptance remains HELD. Historical 21-case runs
(including 21 SQL / 50.25s on the older limited inventory and the PR200-branch
one-shot) are **not** current acceptance; only the fresh gated run recorded in
the companion run-evidence document is.

## 1. True-ancestor additive composition (detail 1)

Preserved source: `81742134d6cb753d5bef4d0372eeea2117192e8b`
("Preserve unintegrated meeting participation source for parent24 handoff",
parent `9903fbb394ce76e812e19bafabe7c753e14177a9`) — the eight effective files:
seven missing frozen participation control/service/SQL021/tests plus the
inherited authority repaired to SAME `protected_sql_connection_v1._connection_v1`
and SAME `sql_execute_v1` for every SQL send.

Composition onto fresh current main is **additive from the true ancestor**
(81742134 content plus current-main owners). The inverse old-main diff
approach is forbidden and was not used.

Eight effective files, git-blob identity vs preserved `81742134` at this head:

| File | vs preserved | head git-blob |
|---|---|---|
| `hosting/meeting_participation_service_v1.py` | SAME | `09295a80c48a4f3ee7a79500771fb7e9e291906b` |
| `meetings/participation_authority_v1.py` | **DIFF — current-main superset** | `c84265a878a7ca7f386943f80c667d9ca9ebafd3` (preserved `0478c729…`) |
| `meetings/participation_control_contracts_v1.py` | SAME | `f43beaf9704d3c5f164e1625028b3c94efa3bd70` |
| `sql/021_meeting_participation.sql` | SAME | `4ac6cebfc6df5f804c190a8a98575803b9e9aa98` |
| `tests/test_meeting_participation_control_v1.py` | SAME | `2591c229a59522dac1a9dadedc5779e2fdb2dc8e` |
| `tests/test_meeting_participation_sql.py` | **DIFF — current-main superset** | `84eac93a1c2d5e4aea94a6126cae4ef050c47a93` (preserved `24d43571…`) |
| `tests/test_meeting_participation_v1.py` | SAME | `0a841eb5b85563a56966ec4268a06af700148e39` |
| `tests/test_meeting_participation_wire_v1.py` | SAME | `52b4169351a5b0f1afa8a3643e594a29ec4e98c3` |

The two DIFF files are **current-main supersets that retain the preserved
contract and add current-main owners only** (verified by diff direction
8174→head = additive-only):

1. `participation_authority_v1.py` — preserved repair intact (five sends on
   `sql_execute_v1`, connection on `_connection_v1`, mutation-attempted mark
   before the guarded send, after-I/O uncertainty typed
   `ParticipationOutcomeUnknown` "read-only reconciliation only, no resend").
   Current-main addition retained: `write_returned` tracking plus typed
   write-time `InsufficientPrivilege` pass-through (a complete write-statement
   privilege refusal is a deterministic safe denial; anything after the write
   returns — including the fresh status readback — stays UNKNOWN/no-resend).
   This matches the standing rule that never-written refusals are
   deterministic, not UNKNOWN.
2. `test_meeting_participation_sql.py` — 21 case bytes and L5 exactly-21 pins
   preserved; current-main W10 assertion-preserving fixture batching,
   `owned_worker_database` caching, sleep/capture-window shortening retained
   (PR214-era cuts, previously verified assertion-preserving).

The four already-merged originals are retained untouched on this head:
`hosting/meeting_participation_v1.py`, `meetings/participation.py`,
`meetings/participation_runtime_v1.py`, `meetings/participation_wire_v1.py`
(all four PRESENT at HEAD; the authority, the fifth historical owner, carries
the preserved repair above). Other main/S07/identity/Trigger/workspace source
unchanged by this composition.

## 2. Connector / common-password ownership and catalog lineage (detail 2)

Audit of the composed head — every preserved property holds:

| Property | Evidence on this head |
|---|---|
| Explicit password/port required | authority URL guard (`participation_authority_v1.py:166-167`) requires `host,port,dbname,password` before connect; common owner (`protected_sql_connection_v1.py:34`) requires `host,port,dbname,user,password,sslmode,sslrootcert` |
| Numeric pin | `_connection_v1` resolves `hostaddr` to a pinned numeric address (`ipaddress` parse, `:40-43`), rejects DNS-label-only targets, `verify-full` required (`:37`) |
| Deny PG\* fallback | `_connection_v1:30-31` refuses when any `PG*` environment key is present ("protected SQL cannot consume PG environment defaults") |
| Original deadline | all five authority sends call `sql_execute_v1(connection, deadline, …)` with the SAME original deadline (lines 231, 233, 235, 278, 418) |
| Prearmed timeouts | statement/lock timeouts armed via `pg_catalog.set_config` inside the same guarded session (`:233`); connect prearmed `connect_timeout=2`, `tcp_user_timeout` bounded (`protected_sql_connection_v1.py:53`); two-second startup floor refused when the original window cannot fit (`:47`) |
| Guarded transaction/close | no raw `psycopg.connect` / `.execute` / `.commit` / `.rollback` in the authority (grep NONE); single connection owner `_connection_v1`, single send owner `sql_execute_v1` |
| Post-close currentness | preserved `meeting_participation_v1.py` factory post-commit/close fresh-own-current-status behaviour unchanged (original owner retained) |
| Mutation-attempted BEFORE guarded send | `participation_authority_v1.py:417` sets `mutation_attempted = True` immediately before the guarded send at `:418` |
| After-I/O uncertainty typed UNKNOWN | `:449-450` raises `ParticipationOutcomeUnknown('participation outcome UNKNOWN; read-only reconciliation only, no resend')` for `mutation_attempted` or connection-level faults; never a resend |

Canonical 021 digest (git-blob semantics, `git show HEAD:…021… | sha256sum`):
`959a77553849616eee1d7b4eba4ed8a3bc146aaa432b7e0e2ca8d83ff17b2f7c` —
**exactly matches the required pin** (63753-byte LF file; a CRLF working-tree
measurement is not this pin and must not be quoted as one).

Catalog/lineage: `SYNTHETIC_MIGRATIONS` in
`scripts/oracle2/verify_workflow_integrity.py` is the sealed 23-entry
inventory `001,002,004,006–014,017–027` (omits 003/005; `021` sits after
`020_meeting_capture.sql`, before `022_consolidated_answer_delivery.sql`) —
there is no contiguous 001..027 chain and none is claimed. The journey
runner's sealed inventory digest over git-blob bytes recomputes at this head
to `64f7085ef2e2fad0ce326e17c6cbad196f4fb110b44e948a5ae9e987d7b74ddc`,
**identical to `SEALED_INVENTORY_DIGEST`** in
`scripts/oracle2/run_s08_journey_proof_v1.py` (migration bytes at current main
are unchanged since the seal). Canonical catalog conditionals for 021's six
public function signatures are present in `dev/oracle2/test_canonical_schema.py`
(`oracle2.meeting_participation_{status,control,claim,observe,prepare,
observe_audience}_v1`); `test_operating_model_verifier.py` asserts the
`[-12:]` inventory window including 021.

## 3. Registration — canonical 021 + four mandatory suites (detail 3)

- `SYNTHETIC_MIGRATIONS`: `021_meeting_participation.sql` registered (23
  entries, asserted by `test_operating_model_verifier.py:204`).
- Four mandatory suites registered in `verify_workflow_integrity.py`:
  `MEETING_PARTICIPATION_CORE_SUITES = (meeting_participation_control_v1,
  meeting_participation_v1, meeting_participation_wire_v1)` in DOCUMENTARY;
  `MEETING_PARTICIPATION_EVENT_SUITES = (meeting_participation_sql)` in EVENT
  (W10 rebalance moved the SQL suite to EVENT; that placement is current-main
  ownership and is retained).
- `scripts/oracle2/verify_phase.py` S08 gate lists all six modules
  (`test_meeting_participation.py`, `test_meeting_participation_control_v1.py`,
  `test_meeting_participation_sql.py`, `test_meeting_participation_v1.py`,
  `test_meeting_participation_wire_v1.py`, `test_outbound_replay.py`).

## 4. AST identity — 26 prior test functions (detail 3)

Per-function AST dumps (`ast.dump`, no attributes) of
`tests/test_meeting_participation_v1.py` compared between preserved
`81742134` and this head: **all 26 prior test functions AST-identical**, and
all 9 connector-successor functions (the `s08-current-case-census.json` nine)
AST-identical. Total 35 test functions = 26 prior + 9 new. Since this head's
file is byte-identical to the preserved blob, every function also matches the
post-authority-repair baseline; the authority repair's own semantic change
(the typed write-time privilege refusal) lives in
`participation_authority_v1.py`, not in these function bodies.

26 prior names (census `old_test_functions_unchanged: 26`):
`test_bad_actual_latest_binding_fails_closed`,
`test_bad_fresh_private_metadata_never_releases_provider_body`,
`test_body_policy_does_not_accept_partial_or_self_stated_map`,
`test_caller_content_substitution_denied_before_prepare_sql`,
`test_claim_body_only_after_commit_close_and_fresh_own_current_status`,
`test_closed_body_policy_fingerprint_exact_canonical_descriptor`,
`test_committed_claim_readback_failure_unknown_one_write_no_retry`,
`test_current_turn_selector_is_own_readonly_private_frame`,
`test_exact_current_address_preserves_original_words_and_claim_limits`,
`test_expanded_markup_overlimit_declines_without_truncation`,
`test_expired_claim_never_reopens_source_bytes`,
`test_expiry_refuses_before_connection`,
`test_explicit_claim_replay_has_no_executable_body`,
`test_fresh_claim_mismatch_never_releases_body`,
`test_host_contract_before_any_connection`,
`test_installation_cannot_self_appoint_or_widen_catalog`,
`test_latest_preparation_selector_is_from_actual_own_sql_only`,
`test_markup_escaped_only_for_provider_presentation`,
`test_missing_chat_host_or_source_binding_declines_no_mutation`,
`test_other_mentions_and_lookalikes_decline_without_alternate_answer`,
`test_overlimit_or_empty_reply_refuses_instead_of_slicing`,
`test_proactive_content_is_only_exact_turn_clarification_never_permission`,
`test_selector_contract_refuses_before_connection`,
`test_sender_cannot_write_observation_facts`,
`test_settings_change_at_write_close_unknown_before_next_connection`,
`test_wrong_bot_identity_in_claim_never_releases_bytes`.

The 21 SQL cases are exactly `test_meeting_participation_sql.py` (19 plain
functions + 2 single-element indirect-parametrize pins = 21 collected; the L5
comments forbid expanding those lists). SQL021 file bytes and all 21 case
bytes unchanged from the preserved source.

## 5. S08 delivery doc source references (detail 6)

These three preserved snapshots carry exact bytes/limits of the eight-source
composition and case census. Their pre-preservation "dirty/no commit" status
is superseded **only** by the `81742134` preservation commit, not by runtime
acceptance:

- [`s08-current-source-delivery.md`](https://github.com/u2giants/theoracle/blob/d02425248e9e033a79a3b80d3b2f8fd0091cd725/docs/verification/oracle2/parent24-closeout-2026-10-22/s08-current-source-delivery.md)
- [`s08-current-eight-source.patch`](https://github.com/u2giants/theoracle/blob/d02425248e9e033a79a3b80d3b2f8fd0091cd725/docs/verification/oracle2/parent24-closeout-2026-10-22/s08-current-eight-source.patch)
- [`s08-current-case-census.json`](https://github.com/u2giants/theoracle/blob/d02425248e9e033a79a3b80d3b2f8fd0091cd725/docs/verification/oracle2/parent24-closeout-2026-10-22/s08-current-case-census.json)

## 6. Gate chain (detail 4) — see companion run evidence

Planned and executed under the delegated root release for this synthetic
proof: Muse `final-check` (`--detach`, observation-week rules; `--assert-head`
the full 40-char seal head) with `AI_POOL_CALLER=mimo
AI_IMPLEMENTER_ENGINE=mimo` from inside the worktree; operator-minted
`review-receipt.json` (head + runner/plan/checker/evidence git-blob SHAs +
verdict `APPROVE`); `ai-task-gates check --before database` precise ALLOW
recorded; then **one fresh root-run execution** of
`scripts/oracle2/run_s08_journey_proof_v1.py` on edge-dev3 (Linux, Docker).
Run IDs, the 21-SQL current-acceptance receipt, pure-population result and
the journey stage record are in
`s08-current-integration-run-20261028.md` (companion). Historical 21-case
runs are not current acceptance.

Receipt-bound git-blob SHAs at the seal head (H6 semantics,
`git show HEAD:<path> | sha256sum`):

- runner `scripts/oracle2/run_s08_journey_proof_v1.py`:
  `b64739be67fe74a9253591ddbe05232feaeb6ea3565e014521e3f67996d20365`
- plan `docs/verification/oracle2/s08-journey-proof-plan.md`:
  `d9e0824a0fb2b66761468fabda6e12106f9305749ee92d2f6f5082b6f13de39e`
- checker `scripts/oracle2/check_s08_journey_skeleton_v1.py`:
  `316e45d5298c27549fd3fac1941029ce01b794c250fcbab0d18d317c37a1c7a1`
- evidence `docs/verification/oracle2/s08-compose-81742134-evidence.md`:
  `f3871572e844594a1ee001de61b12bbf7400ba5bc25f5958ba803cd9e99eb748`
