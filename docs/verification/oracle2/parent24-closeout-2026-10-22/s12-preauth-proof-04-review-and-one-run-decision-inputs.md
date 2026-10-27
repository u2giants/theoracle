# S12 preauth proof 04 — independent review and one-run decision inputs

Prepared inputs only. No review receipt, no database gate, no one-run release is claimed here.
Every gate below is named UNPROVEN until the responsible actor records a real receipt.

Companion brief: `s12-current-public-review-brief-04.md` (same directory).
Runner: `run-s12-current-preauth-proof-04.py` (same directory), SHA256 `5b05cb4a41a8bc50b6284b4c1d09fa99b7003deb0680e8e9fd5063fd48731911`.

## 1. What the independent reviewer is asked to assess

Two separate assessments. Both must pass before root may decide one-run.

### A. Exact SOURCE assessment

Review ALL of the following at consumer HEAD `7defd1eeeaccad46ba04b96952c439305065c796`
(genuine main parent `c187bfc36723ca891ad7558fe202a258ee2f27f8`):

**Shared / authguard (the full binding set — not only the 11-file 7def diff):**
1. `packages/shared/src/protected-server-binding.ts`
2. `packages/shared/src/protected-control-window.ts`
3. `packages/shared/src/_protected-file.ts`
4. `packages/shared/src/protected-service-channel.ts`
5. `apps/web/proxy.ts`
6. `apps/web/lib/auth-guard.ts`
7. `apps/web/lib/supabase/server.ts`
8. `apps/web/lib/replacement-protected-client.ts`
9. `apps/web/lib/replacement-server-binding.ts`

**S12 nine-case and fixture sources (7def additions):**
10. `services/oracle-brain/tests/test_workspace_next_recipients_sql_v1.py`
11. `services/oracle-brain/tests/test_workspace_workflow_fixture_v1.py`
12. `services/oracle-brain/tests/invented_next_employee_fixture_v1.py`
13. `apps/web/tests/oracle2/workspace-next-recipients-proof.ts`
14. `apps/web/tests/oracle2/invented-auth-service.ts`
15. `apps/web/tests/oracle2/invented-auth-service.ts` companion `apps/web/lib/replacement-recipient-origin.test.ts`
16. `apps/web/lib/replacement-protected-control-route.test.ts`

**Runner and custody:**
17. `run-s12-current-preauth-proof-04.py` (exact bytes, SHA above)
18. Complete 1703-file manifest (`s12-current-preauth-reviewed-source.json`, 215406 bytes, SHA `06e8b1ce008d8d23d305f75c58d7417a9e3d401e22b35a9158f3049a8e220e5f`)

**SOURCE assessment questions:**
- Does the preauth path refuse malformed/expired/missing/changed facts with zero Auth/SQL before any SDK construction?
- Does `validUntil` equal the minimum of index expiry and ALL origin-matched profile horizons (shortest matched profile)?
- Are all eight closed validators unchanged and applied to every pinned profile?
- Do the eight malformed employee-pair cases raise before `owned_worker_database`?
- Does the one end-to-end case cover two independent recipients, named workflow, EN/ZH, mobile, revocation, and original-window deadlines?
- Does runner 04 refuse to start without an exact review receipt and matching runner digest?
- Does runner 04 invent no startup receipt and treat missing ownership as UNKNOWN/absence_proven:false?
- Is the complete 1703 census bound before the database gate and rechecked after?

### B. ONE resource-plan assessment

Runner 04 requests exactly one fresh synthetic resource footprint:

| Resource | Exact plan |
|---|---|
| Compose project | `oracle2-synthetic-s12c04` + helper suffix `w<12hex>` |
| PostgreSQL | one fresh worker Postgres via `worker_postgres` (owned TLS) |
| Graph | one Falkor candidate, port bound to `127.0.0.1`, label-checked |
| Canonical schema | installed ONCE under `dev.oracle2.test_canonical_schema` |
| Phase database | one fresh UUID database under `owned_phase_database` |
| Worker label | `documentary-99` |
| Next | one `next dev --turbopack --experimental-https` instance |
| Browser | one Playwright chromium, two contexts (desktop 1280, mobile 393) |
| Limits | context 120s, admission 115s, request 30s, test deadline 120s |
| Cleanup | retained ownership receipt 0600 single-link; remaining containers/networks/volumes by project label must be empty |

**Resource-plan questions:**
- Is this truly ONE resource, not a fleet or a full W10 run?
- Does cleanup prove absence (absence_proven:true) or honestly report UNKNOWN/false?
- Are original 120/115/30 limits preserved without widening?
- Does the runner stop at the database gate if the review receipt is missing or mutated?

## 2. Named UNPROVEN gates (decision inputs for root)

Root must not treat any of these as satisfied until a real receipt is recorded.

| Gate ID | Owner | Required evidence | Current status |
|---|---|---|---|
| `S12-04-REVIEW` | Independent reviewer (different engine) | Written SOURCE + RESOURCE-PLAN assessment with APPROVE or BLOCK on this exact HEAD + runner digest | **UNPROVEN** |
| `S12-04-DB-GATE` | `ai-task-gates check --before database --reviewer-approval <receipt>` | Gate output ALLOW, receipt SHA bound, runner SHA bound | **UNPROVEN** |
| `S12-04-ROOT-RELEASE` | Root coordinator | Explicit one-fresh-release decision naming runner 04 SHA and HEAD | **UNPROVEN** |
| `S12-04-LIVE-9CASE` | Whoever executes runner 04 after the three gates above | JUnit `{tests:9,failures:0,errors:0,skipped:0}`, result.json, complete-source-before/after equality, cleanup.json absence_proven:true | **UNPROVEN** |
| `S12-04-NEXT-E2E` | Same run | receipt.json with `actual_next:true`, `all_requests_original_window:true`, employee_sql_observations TLS-true, zero page errors | **UNPROVEN** |
| `S12-04-PROCESS-ABSENCE` | Same run | process-cleanup.json remaining_active empty; owned containers/networks/volumes empty | **UNPROVEN** |
| `S12-04-TEAMS` | Separate qualification | Real Teams producer proof | **UNQUALIFIED** |
| `S12-04-BIZ` | Business acceptance | Company comparison / adoption / non-use / retirement authority | **UNPROVEN** (hold remains) |

## 3. What is already proven without a live database run

These facts do NOT substitute for any gate above.

1. Runner 04 exists with SHA256 `5b05cb4a41a8bc50b6284b4c1d09fa99b7003deb0680e8e9fd5063fd48731911` (verified against exact blob bytes).
2. Nine-case suite at 7def is exactly one end-to-end + eight malformed-input negatives.
3. **Cases 2–9 PROVEN offline by live execution (2026-10-26).** All eight malformed employee-pair inputs raised `ValueError` before `owned_worker_database`; a stub that raises if reached was never touched. Exact refusals: `empty`/`one`/`three` → `exact two invented employee entries required`; `auth-duplicate`/`employee-duplicate`/`string-uuid`/`boolean-admin`/`unknown-tuple` → `distinct exact invented authuser/employee/bool tuples required`. This proves zero-database refusal for cases 2–9.
4. **Workflow structure PROVEN offline (2026-10-26).** `workspace-artwork-rework-v1` constructs under `formal_eligible=True` with steps=5, transitions=6, conditions=2, roles=3, handoffs=1, rework=1 (art-t6 Revise ART → Review ART), exclusive-split edges=2 from art-decision. All five step labels and both condition wordings appear in the QUOTE string.
5. Runner 04 requires argv review receipt + argv runner SHA; rechecks review SHA after the gate; writes source-after even on startup failure; treats missing ownership as UNKNOWN/absence_proven:false and raises.
6. Runner 04 has NEVER executed as a real database gate. Scratch dir `s12-current-preauth-owned-proof-04` does not exist.
7. Earlier nine-case suite (source `31262e0063c1`) passed in a prior tree but had ZERO workflows; it is not this current proof.
8. Consumer source HEAD `7defd1eeeaccad46ba04b96952c439305065c796` is NOT an ancestor of current `main`; the nine-case sources live only on the frozen S12 path and must be reviewed at that exact HEAD.

## 4. Explicit non-claims

- No invented review receipt. No invented database-gate ALLOW. No invented JUnit. No invented cleanup receipt.
- No Supabase production session, real employee, company source, or provider call is proved.
- No documentation-check pass (capability remains UNKNOWN/INVALID).
- No full S12 product acceptance (grouped inbox, editable correction, source-failure/retry health, full a11y/task rubric remain open).
- No business acceptance. Real Teams producer UNQUALIFIED.
- This packet is not authority to execute runner 04. Execution requires `S12-04-REVIEW` + `S12-04-DB-GATE` + `S12-04-ROOT-RELEASE` first.

## 5. Suggested decision order for root

1. Dispatch independent reviewer for `S12-04-REVIEW` against this exact packet.
2. On APPROVE, record the review receipt at a stable path and note its SHA256.
3. Run `ai-task-gates check --before database --reviewer-approval <receipt>` in the frozen workspace. If ALLOW, proceed; if not, stop.
4. Root records `S12-04-ROOT-RELEASE` naming HEAD `7defd1eeeaccad46ba04b96952c439305065c796` and runner SHA `5b05cb4a…`.
5. Execute `run-s12-current-preauth-proof-04.py <receipt> 5b05cb4a41a8bc50b6284b4c1d09fa99b7003deb0680e8e9fd5063fd48731911` once, in the frozen workspace.
6. Verify JUnit `{9,0,0,0}`, source-before/after equality, absence_proven:true, process-cleanup remaining empty.
7. Only then mark `S12-04-LIVE-9CASE` / `S12-04-NEXT-E2E` / `S12-04-PROCESS-ABSENCE` proven and continue remaining full S12 product tasks.

Posted by MiMo chat on edge-dev3. All gates above remain UNPROVEN as of this packet.
