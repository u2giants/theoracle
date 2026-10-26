# S13 recovery metadata repair — 27/27 actual + 22/22 static proof

**Date:** 2026-10-26 (EDT)
**Branch:** `codex/parent24-s13-repair-20261026`
**Head:** `45a6a8b9d31ffc2a772142b87138a2578ed1aef0`
**Class:** code (offline synthetic DB; no production, no shared-db write)
**Host:** edge-dev3

## What was repaired (defect chain behind recovery09 FAILED 25/27)

The recovery09 run failed 25/27 with two root-cause classes. Both were already
ratified and landed on main via PR #197 and its follow-ups; this branch adds
static source locks and an independent re-proof.

| # | Defect | Evidence at 09 | Fix | Commit |
|---|---|---|---|---|
| 1 | Receipt ownership: census query `FROM meeting_capture_worker_receipts_v1 t WHERE t.workspace_id=…` but canonical 020 receipts have NO `workspace_id` column | 21/25 `UndefinedColumn` | JOIN `meeting_capture_worker_claims_v1 own ON own.claim_id=t.claim_id WHERE own.workspace_id=ANY($1)` | PR197 (on main) |
| 2 | Claim alias: `jsonb_array_elements(a.scope_coverage) scope` — alias `scope` collides with `appointments.scope text`, so `scope->>'appointment_id'` resolves to `p.scope->>'appointment_id'` (`text ->> unknown`) | 4/25 `UndefinedFunction` on `claim_recovery_phase_v1` | `AS recovery_scope_item(value)` with qualified `.value` at SAME sites | PR197 (on main) |
| 3 | `observed_at` parameter vs `meeting_participation_observations_v1.observed_at` column collision in `_recovery_operational_denials_v1` | runner10 `AmbiguousColumn` | `#variable_conflict use_variable` | `f71f0374` |
| 4 | `to_jsonb(oid)` emits JSON string; `RecoveryCurrentV1.source_database_oid` is int | runner11 pydantic `int_type` on `'16808'` | `oid::bigint` cast | `acf7d706` |

This branch adds two static source tests locking fixes 3 and 4 so neither can
regress silently:
- `test_operational_denials_observed_at_parameter_wins_over_column`
- `test_recovery_current_casts_source_database_oid_to_bigint`

## Independent re-proof (this branch)

Runner: `s13_repair_proof_20261026.py` (external harness, not committed).
Fresh synthetic worker Postgres (`oracle2-synthetic-p24rec-r26`), one canonical
owner/bootstrap on a fresh UUID DB, metadata-only.

**Actual 27-case suite** (`test_recovery_authority_sql_v1.py`):
**27 passed, 0 failed, 0 errors, 0 skipped, 37.37s**

**Static SQL-source suite** (`test_recovery_sql_source_v1.py`):
**22 passed, 0 failed, 0 errors, 0 skipped** (includes the 020 frozen-hash pin
and the two new locks; Windows CRLF false-positive does not apply on Linux).

**Owned cleanup:** `absence_proven: true`, containers/networks/volumes all
absent. Source manifest unchanged during proof.

| Artifact | SHA-256 |
|---|---|
| `recovery-authority-pytest.xml` | `731ee1addff035b82ba6470bdebe735effa6b727a1d6586f645a4a620ca0d037` |
| `static-sql-source-pytest.xml` | `a61f67066ae819786959d3d5a8e2d4c539b64dc2eb263bf29098357c0f000b60` |

Synthetic DB `oracle_operating_model_test_eb9fd0b102c34dae81b4dc35f1fa8ed9`
is a spent test identity, not a resume target.

## What this does NOT prove

- Metadata recovery success is **not** full restore. Full fresh
  backup/restore/quarantine/current denials/private/vector/license/once/cost/
  019-checkpoint/outage/RTO/RPO/scale/alerts/retention/quota remain open.
- Sealed SQL 017 unchanged. Real Teams producer UNQUALIFIED.
- Business-acceptance hold remains. No company use, production adoption, or
  parent #24 closure is claimed.
- Catalog/source pins and fail-closed paths were not weakened.
- Runner12 (`acf7d706`) previously proved 27/27 under the review-gated harness;
  this re-proof confirms the same result on the merged main lineage plus the
  two new static locks.

## UNPROVEN gates (exact)

1. Full recovery (native dump/restore, archive child, private roots, vector,
   license, once/cost, 019 checkpoint, outage/RTO/RPO/scale/alerts/retention/
   quota) — not executed here.
2. Source/runtime admission beyond the metadata SQL path — held for root.
3. Independent exact SOURCE + ONE resource assessment for any further actual
   child/filter/prlimit run — not requested here.
4. Business acceptance / company activation — owner hold, unchanged.
5. Real Teams producer qualification — UNQUALIFIED.
