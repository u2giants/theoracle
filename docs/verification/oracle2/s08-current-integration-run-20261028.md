# S08 current integration — gate-chain run evidence (current acceptance)

Recorded: 2026-10-27 EDT (America/New_York), edge-dev (Windows) coordination
with edge-dev3 (Linux) execution. Integration head
`0e8a24f15285d9ff75fbb7f2b67d8a54f1902357` (branch
`parent24-s08-current-integration`, base `489dd987f96d613be9e0546d4a772ab665b584a4`).
Companion to `s08-current-integration-source-audit-20261028.md` (composition,
connector audit, registration, AST identity). Synthetic/invented only. **Real
Teams chat/audience producer and real invitation/producer qualification remain
UNQUALIFIED** — every participation fact is fixture-invented; ACK never equals
a visible message or provider idempotency. Business acceptance HELD. The
historical 21 SQL / 50.25s run (PR200-branch scratch, older inventory) is not
current acceptance; the fresh gated run below is.

## 1. Pure population — 256 green (detail 3)

Linux (edge-dev3), branch worktree `/tmp/oracle-parent24-wy02uT/s08-int-r1`,
oracle-brain venv (`uv sync --project services/oracle-brain --frozen --extra
test --extra process-analysis`). The exact 256-case pure inventory
(s08-connector-retained-05 lineage — 4 S08 pure modules + 7 compose-adjacent
meeting/fence/connection modules):

| Module | Cases |
|---|---|
| test_meeting_participation_v1 | 89 |
| test_original_view_protected_connection_v1 | 26 |
| test_meeting_participation_wire_v1 | 26 |
| test_meeting_participation | 25 |
| test_conversation_fence_v1 | 23 |
| test_meeting_participation_control_v1 | 22 |
| test_meeting_request_fence | 14 |
| test_meeting_worker_contracts | 9 |
| test_meeting_worker_adapter | 9 |
| test_meeting_capture_wire | 9 |
| test_meeting_capture_contracts | 4 |
| **total collected / passed** | **256 / 256** |

Result: **256 collected, 256 passed, 0 failed / 0 errors / 0 skipped in 1.12s**
(`-p no:cacheprovider`). The 256 pure cases stay green.

Supporting dispositions (same host):

- `test_outbound_replay.py` (sixth S08 gate module): **38 passed** — it RUNS
  (not a skip), matching the journey plan's expected disposition.
- `test_operating_model_verifier.py`: **69 passed** — registration assertions
  (SYNTHETIC_MIGRATIONS 23 entries incl. 021; `[-12:]` window) green.
- Offline skeleton checker rerun on Linux per M6: **OFFLINE_SKELETON_CHECKS_PASS**
  — H4 mode/nlink/symlink negatives executed (`H4_SIZE/SYMLINK/MODE/NLINK_NEGATIVE_OK`),
  `L5_EXACTLY_21_*` pins, UNKNOWN-routing flow tests, inventory mirrors.

## 2. Gate chain (detail 4) — review routing, resource gate, one root-run

Review routing record (observation-week rules; every failure logged via
`ai-reviewer-issue`; failed reviewers never retried):

1. Muse `final-check --detach --assert-head 2e05249f…`, run
   `d20261027T231510-2938600-24916` (lifecycle `20261027T231717-2941170-8665`).
   Native review completed: every load-bearing pin byte-faithfully recomputed
   and confirmed; **Verdict: APPROVE** with findings M1/L1–L4. Publication
   refused `stale-source` after a caller mid-review untracked write into the
   worktree (disclosed caller slip; issue
   `20261027T234643Z-edge-dev-muse-2967282`). Findings folded at `4e0181c6`.
2. GLM `final-check --detach --assert-head 4e0181c6…`, run
   `d20261027T235339-2981958-9344` (lifecycle `20261027T235432-2984775-23285`):
   provider preflight failed, no review assigned (issue logged; rotation
   continues).
3. StepFun `final-check --detach --assert-head 4e0181c6…`, run
   `d20261027T235937-2993119-19070` (lifecycle `20261028T000026-2995071-2603`).
   Full source review of the exact head: all send-safety/connection/deadline/
   migration/registration/runner-seal claims verified; **Verdict: APPROVE**,
   **Blocking: none** (31,554-byte native capture retained at the lifecycle
   failure-diagnostics path). Publication refused (`report-extra-decision-line`
   format warning + `source-identity-changed` while concurrent PRs 224/226/227
   moved `origin/main` during the review — forward-only target movement that
   the pool's tolerance was written for (#1254), here paired with the
   report-format refusal). Logged; failed reviewer not retried. DeepSeek was
   not drawn (its skill policy: formal reviews only on allocator assignment).

The operator-minted `review-receipt.json` (the journey plan's procedural
trust model, H-J) binds head `0e8a24f1…` + the four receipt-bound git-blob
SHAs (unchanged across `2e05249f`→`0e8a24f1`) + verdict `APPROVE`, citing the
StepFun exact-head verdict and the full run-ID provenance above. Head
`0e8a24f1` is `4e0181c6` plus only the repair both reviews recommended (below).

Resource gate: task class `shared-db` (SQL prerequisites included — the
closeout precedent; a `code`-class declaration prints the
database-writes-skip-review wording the sealed runner's ALLOW_LINE does not
pin). `ai-task-gates check --before database` prints the precise form-3 line
`ai-task-gates: "database" may start for effective class "shared-db" in
u2giants/theoracle.` (exit 0, no DENIED). The runner re-checked it in-run
(`ops-database-gate.txt`).

**One fresh root-run execution** (the delegated root release for this
synthetic proof): `scripts/oracle2/run_s08_journey_proof_v1.py` on edge-dev3
under the oracle-brain venv with `ORACLE2_S08_JOURNEY_RECEIPT` set to the
receipt (600-mode, 1540 bytes, outside SCRATCH). Scratch
`/tmp/oracle-parent24-s08-journey-f29d290aa73c4552b76a05dea1b5e043/`.

Run outcome at head `0e8a24f15285d9ff75fbb7f2b67d8a54f1902357`:

- Preflights, receipt binding (H6 git-blob SHAs), database gate (ALLOW),
  source snapshot before==after the gate, worker_postgres + sealed bootstrap:
  all passed. Schema receipt inventory digest
  `64f7085ef2e2fad0ce326e17c6cbad196f4fb110b44e948a5ae9e987d7b74ddc` —
  **matches `SEALED_INVENTORY_DIGEST`** (catalog digest recorded, not golden).
- **21 SQL current acceptance: `21 passed in 43.37s`** (exactly 21
  collected/passed, 0 failed/errors/skipped — the L5-pinned module, H4 green
  gate satisfied before any journey stage). This is the fresh current-head
  acceptance; the historical 21 SQL / 50.25s run is not.
- Journey stage sequence: refused at `provision_capture_admission` with the
  sealed `UNPROVEN` disposition ("capture/admission provisioning not
  released; journey stage 0a UNPROVEN") — the stage adapters remain in their
  sealed state exactly as at PR200 (its accepted one-shot carries the same
  refusal after its own 21/21 green). The 21-case module is the executable
  proof of the journey stage behaviours (see §3).
- Owned-resource cleanup readback: `{"absent": true, ... "remaining":
  {"containers": false, "networks": false, "volumes": false}}` — no owned
  synthetic residue (`project oracle2-synthetic-p24s08-jrny-a21ed753-w16d18cab5a07`).

An earlier execution attempt at head `4e0181c6` refused at H4 (`1 failed, 16
passed`): `test_actual_late_private_wire_finishes_as_orphan_without_sql_receipt`
raised `PermissionError: original SQL window cannot fit the supported
two-second connection bound` — the W10 timing cut (caller deadline 3s→1s)
can never fit the common connector's 2.002s startup floor, so the case died
at its first binding readback instead of reaching the intended post-late-write
UNKNOWN path. Both final-check reviews had independently flagged exactly this
case's timing delta (Muse M1 / StepFun Low). The repair commit restores the
preserved 3s caller deadline (keeping the sound 1.1s sleep cut) and fixes the
stale 20-entry inventory docstring to the sealed 23. No assertion weakened,
no case cut, no budget raised. Re-execution on the repaired final head is the
documented post-source-fix procedure (Muse seals are head-exact).

## 3. GATE mapping (detail 5) — path and controls vs the 21-case acceptance

The fresh gated execution of `test_meeting_participation_sql.py` (exactly 21
collected/passed; L5 pins forbid list expansion) is the current acceptance:

| Gate item | Proven by (21-case module, fresh green at `0e8a24f1`) |
|---|---|
| browser→current-turn→sender→provider-fixture→receipt path | `test_actual_host_mtls_real_sql_enable_privatebytes_and_closed_denials` (actual mTLS HTTP control entry — the protected host-control surface the browser/UI drives: status → enable → prepare → claim → body; closed-denial matrix 404/503; peer-tamper 503) chained with `test_actual_current_source_intent_once_claim_wire_custody_and_restart` (observe-audience → enable → read current turn → prepare → claim → `receipt_v1` raw-wire provider-fixture bytes in → fresh-factory restart status → no second body) |
| revocation | `test_actual_selected_host_root_revocation_not_rescued_by_alternate_leaf`, `test_actual_observer_revocation_denies_claim_before_bytes`, `test_actual_forensic_receipt_after_host_disable_never_restores_send`, `test_actual_source_grant_withdrawal_blocks_claim_but_not_ingress`, `test_actual_committed_claim_then_selected_admission_revoked_unknown` |
| lost ACK | `test_actual_committed_claim_then_readback_loss_unknown_no_automatic_retry`, `test_actual_unknown_receipt_and_host_toggles_cannot_resend_same_turn` (typed UNKNOWN, read-only reconciliation, no resend) |
| cooldown | `test_actual_proactive_off_cooldown_and_lifetime_count_survives_toggle` (120s cooldown, proactive default-off) |
| cap | same case (max 3 interventions per meeting, survives toggle) |
| global-once | `test_actual_current_source_intent_once_claim_wire_custody_and_restart` (one intent, body released once, restart-safe no-resend), `test_actual_concurrent_claims_release_exactly_one_body`, `test_actual_host_cas_concurrent_enable_has_one_committed_event` |
| current-audience | `test_actual_short_observation_clips_claim_and_cannot_renew` (observation expiry ≤30s clips the claim; cannot renew); incomplete/unknown chat declines in `test_actual_unknown_chat_declines_before_privatebytes_and_capture_continues` |

Also green in the same run: wrong-login/TLS/owner fail-closed, runtime-login
private-helper denials, bot-identity immutability, foreign receipt denial,
window-expiry forensic receipt, late-wire orphan (the repaired case),
deadline non-renewal.

**Named remaining boundary (not claimed here):** the Next browser
enable/control **web** surface does not exist on this head (journey plan
remaining gate #4); the "browser" entry proved above is the mTLS HTTP
`/v1/replacement/meetings/participation/control` surface — the same protected
endpoint a browser/UI drives. The journey one-shot's stage adapters (0a–5)
remain in the sealed UNPROVEN state (plan remaining gate #1; the sealed
skeleton checker asserts exactly that property). Real invitation /
supervision / audience-currentness through an installed real producer stays
**UNQUALIFIED** — synthetic fixtures remain the only proven path. No ACK is
claimed as a visible message or provider idempotency guarantee.

## 4. Delivery-doc source references (detail 6)

Carried verbatim from the source-audit companion: the three preserved
snapshots at `d0242524`
(`s08-current-source-delivery.md`, `s08-current-eight-source.patch`,
`s08-current-case-census.json`) whose pre-preservation "dirty/no commit"
status is superseded only by the `81742134` preservation commit.
