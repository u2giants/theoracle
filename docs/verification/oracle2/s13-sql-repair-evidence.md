# S13 SQL repair — composition, two ratified fixes, 56/75-query audit

**Date:** 2026-10-22
**Branch:** `codex/parent24-s13-sql-repair`
**Class:** `shared-db` (declared before writes via `ai-task-gates start --class shared-db`)
**Composition base:** `origin/main` bf788080
**Recovery source head:** 2633c53baadec2d2bbde586a4a13e1b2ba9e79fd

## Composition method

True-ancestor additive composition. The 2633 delta is
`git diff c187bfc3..2633c53b` (30 files, +7866/-34). The merge-base of
origin/main and 2633 is c187bfc3. Main's post-ancestor changes (7 files:
handoff + docs/plans) have zero file overlap with the 30-file delta.

Applied via `git diff --binary c187bfc3..2633c53b | git apply --index`.
All 30 files applied cleanly. Zero deletions. File count 1699→1723
(24 new + 6 modified). This is the full additive delta — no B+C subsets,
no inverse old-main diff (which would change 149 paths / delete 63 files).

## Two ratified SQL repairs (exact, not widened)

### Fix 1 — receipts census workspace join

**File:** `services/oracle-brain/sql/026_operational_recovery.sql` line 535

**Before:**
```sql
WHEN 'meeting_capture_worker_receipts_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_worker_receipts_v1 t WHERE t.workspace_id=ANY($1)';
```

**After:**
```sql
WHEN 'meeting_capture_worker_receipts_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_worker_receipts_v1 t JOIN oracle2.meeting_capture_worker_claims_v1 own ON own.claim_id=t.claim_id WHERE own.workspace_id=ANY($1)';
```

**Defect:** Canonical 020 receipts table has no `workspace_id` column
(verified: `receipt_id, claim_id, admission_id, worker_id, wire_object_key,
wire_sha256, wire_byte_count, observation, created_at`). Claims table has
`workspace_id`. Ratified fix joins SAME `claim_id` to claims owner workspace.
Scope filters unchanged.

### Fix 2 — SRF alias qualification for scope_coverage

**File:** `services/oracle-brain/sql/026_operational_recovery.sql`
sites: claim_recovery_phase_v1 (~line 705), denials union (~line 628)

**Before (claim_recovery_phase_v1):**
```sql
JOIN jsonb_array_elements(a.scope_coverage) scope ON p.appointment_id=(scope->>'appointment_id')::uuid
```

**After:**
```sql
JOIN jsonb_array_elements(a.scope_coverage) AS recovery_scope_item(value) ON p.appointment_id=(recovery_scope_item.value->>'appointment_id')::uuid
```

**Before (denials union):**
```sql
UNION ALL SELECT (scope->>'workspace_id')::uuid,own.principal_id,own.role_name,(scope->>'appointment_id')::uuid,v.revoked_at FROM oracle2.recovery_admission_revocations_v1 v JOIN oracle2.recovery_operation_admissions_v1 own USING(admission_id) CROSS JOIN LATERAL jsonb_array_elements(own.scope_coverage) scope WHERE (scope->>'workspace_id')::uuid=ANY(workspaces)
```

**After:**
```sql
UNION ALL SELECT (recovery_scope_item.value->>'workspace_id')::uuid,own.principal_id,own.role_name,(recovery_scope_item.value->>'appointment_id')::uuid,v.revoked_at FROM oracle2.recovery_admission_revocations_v1 v JOIN oracle2.recovery_operation_admissions_v1 own USING(admission_id) CROSS JOIN LATERAL jsonb_array_elements(own.scope_coverage) AS recovery_scope_item(value) WHERE (recovery_scope_item.value->>'workspace_id')::uuid=ANY(workspaces)
```

**Defect:** Naked `jsonb_array_elements(...scope_coverage) scope` collides
with `appointments.scope text` column. PostgreSQL resolves `scope->>'x'` to
`p.scope->>'x'` (text→>unknown) instead of the SRF row. Ratified fix uses
explicit `AS recovery_scope_item(value)` and qualifies `recovery_scope_item.value`
at all SAME sites. JSON keys, table columns, lineage, and horizon guards preserved.
Other working aliases (`s`, `source_scope_v1`) unchanged.

## 56/75-query audit result

Full machine-readable audit: `docs/verification/oracle2/s13-sql-repair-audit.json`

- **123 canonical tables** parsed from 17 SQL schema files (001–027)
- **75 census CASE dynamic queries** audited (all of `CURRENT_POLICY_TABLES_V1`)
- **56 operational tables** in `OPERATIONAL_TABLES_V1` (020/021/023/024/025 union)
- **18 DECLARE-collision / SRF sites** audited

**Results: 75/75 census queries PASS. 18/18 DECLARE sites PASS. 0 additional defects found.**

Each query verified for:
- referenced tables exist in canonical SQL
- column references resolve to actual table columns
- workspace_id ownership (direct `t.workspace_id`, owner-join `own.workspace_id`, or descriptor JSONB `workspace_ids`)
- no SRF alias collides with `appointments.scope`

The two known defects (receipts workspace join, scope SRF alias) were the
only ones found. No additional predicate/join design defects discovered.
No guessed broad patches applied.

## Static tests

Added 4 tests to `services/oracle-brain/tests/test_recovery_sql_source_v1.py`:

1. `test_worker_receipts_census_joins_claims_owner_workspace_not_bogus_column` — asserts receipts census joins claims, never `t.workspace_id`; verifies canonical 020 columns
2. `test_no_naked_scope_alias_on_scope_coverage_array_elements` — asserts no `jsonb_array_elements(...scope_coverage) scope` pattern remains
3. `test_claim_recovery_phase_uses_explicit_recovery_scope_item_value` — asserts `AS recovery_scope_item(value)` at both known sites with qualified `.value`
4. `test_all_census_queries_workspace_scope_or_owner_join` — asserts all 75 census queries have workspace filtering

**Test results (static, no live DB):**
- 4/4 new defect-catching tests PASS
- 6/6 pre-existing static tests (non-pglast) PASS
- 72/72 contracts+sql_source tests that can run on this machine PASS
- 2 parametrized test setup errors (pre-existing, whitespace-heavy fixtures)
- 5 pre-existing pglast-dependent tests skipped (module not installed on Windows)

The 27 actual database test bodies in `test_recovery_authority_sql_v1.py`
are unchanged. The 25 failure histories from recovery09 are preserved.

## Remaining gate

This is source freeze only. Before any fresh runner10 / actual 27-case proof:

1. Independent exact SOURCE + ONE resource assessment (new review)
2. Genuine database gate
3. Root release
4. Fresh runner10 with new identities (never replay 09 identities)
5. All 27 actual PASS with 0 E/S, current catalog, permission/revocation/direct entry negatives meaningful, complete source unchanged, exact owned resource absence

Then continue full recovery. Metadata success is not full restore.
