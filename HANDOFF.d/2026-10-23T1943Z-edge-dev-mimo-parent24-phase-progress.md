---
issue: 24
status: OPEN
owner: mimo/parent24-1943-2026-10-23
---

# Parent24 phase progress: S08/S11 SQL green, PR197 pins+runner10 ready, independent review blocked

Record owner: MiMo chat on edge-dev (session `ses_ffe5e95ecfe39ffett6HImqCYW`). Observations rechecked October 23, 2026, approximately 2:10–3:45 PM EDT, America/New_York. Dated observations, not transferable authority. Program is NOT complete. No company use, production adoption, or parent closure is claimed.

## 0. Business decisions only the owner can make

**No new business question is outstanding now.** Continue every permitted structural and invented-data obligation before requesting company use. The business-acceptance hold stays until the whole readiness list is proved. Then present the entire genuine business-question list together, once.

**Already settled — do NOT re-ask:**
- October 22, 2026: Albert answered "Remain in force until withdrawn" to whether rules already approved should survive loss of approval authority. Applies only to the exact immutable assertion/version/scope previously approved. Already landed through PR182 and recorded on #29/the plans.
- The closeout, the resume handoff, and the original completion request are not separate permission for company use.

No technical review, platform access, schema decision, source or resource admission belongs in this section. The coordinator and assigned AI reviewers own those steps.

## 1. What this application is

The Oracle repository is POP Creations' evidence-backed company consultant. It ingests permitted originals and explicitly invited conversations/meetings, retains quote-level evidence, models connected workflows/history/conflicts/unknowns, and produces cited answers under current permissions. The outcome is explainable business knowledge, not a test count.

Retained application: Next/TypeScript on Vercel, Trigger.dev workers, Supabase. Replacement: isolated Python/PostgreSQL/FalkorDB/stock GraphRAG operating model with protected mTLS boundaries. Coolify owns app namespaces; Ansible owns host changes.

Authoritative sources, STATUS first:
- [plan_oracle_consultant_overhaul.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_consultant_overhaul.md) and [parent #24](https://github.com/u2giants/theoracle/issues/24)
- [plan_oracle_workflow_integrity.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_workflow_integrity.md), [plan_oracle_source_processing_qualification.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_source_processing_qualification.md), [plan_oracle_replacement_documentary_journey.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_replacement_documentary_journey.md), [plan_oracle_native_fresh_v2.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_native_fresh_v2.md)
- Closeout of record: [2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md) — NOT retired; still holds full S/W/U criteria.
- Prior baton: [2026-10-23T1425Z-edge-dev-mimo-parent24-resume.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-23T1425Z-edge-dev-mimo-parent24-resume.md) — NOT retired this session (predecessor work not fully finished).
- S07 plan: [s07-create-child-fresh-proof-plan.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/oracle2/s07-create-child-fresh-proof-plan.md)

## 2. What we set out to do this session, and why

Albert asked: resume parent #24 from current main after reading both handoffs in full. Goal: continue every remaining phase under existing safety gates and the separate business-acceptance hold. Named next actions: (1) S07 fresh invented proof after independent SOURCE+ONE resource review; (2) on PR197 run Linux pglast + 021/024/025 pin checks then runner10; (3) land PR200 and PR201 after their Linux proofs. Do not delete open PR branches. Do not ask Albert for technical approval.

## 3. Current state — what is true right now

### 3.1 Main and merged work

Main tip at session start: `81f9f6d9` ([handoff PR #204](https://github.com/u2giants/theoracle/pull/204)). W10 **5472 success:true** remains the last full-population green (run 39855010833). Business acceptance false.

### 3.2 PR197 S13 SQL repair — pins and static proof green; runner10 prepared

Branch `codex/parent24-s13-sql-repair`, head [`3072140f`](https://github.com/u2giants/theoracle/commit/3072140f90e0340bc89f7a4eb4221c8c8aa5cc51).

This session:
- **Pin check PASSED.** 020/021/023/024/025/027 git-blob sha256 all match `OPERATIONAL_OWNER_SOURCE_PINS_V1`. Disk hashes on Windows differ only by CRLF; always hash git blobs.
- **`test_recovery_sql_source_v1.py` 20/20 PASS** after refreshing the outside-context frozen hash (the two ratified repairs change bytes outside `_recovery_context_v1`). Scope-inverse `count==9` and normalized-context hash unchanged. Commit `3072140f` pushed.
- **27 SQL cases collect** on `test_recovery_authority_sql_v1.py` (the runner10 population).
- **Runner10 prepared** on edge-dev3: `run-recovery-metadata-sql-proof-10.py`, bound to head `3072140f`, manifest sha `32cacf5215161fb0ea91ef413db953079b590c00b0afbd1bc894ba666ace8cb9` (1725 files / 218398 bytes), scratch `recovery-metadata-owned-sql-10`, project base `oracle2-synthetic-p24rec10-mimo`. **NOT executed** — requires independent resource assessment + root release.
- GLM final-check APPROVE on `939cc280` remains valid for the SQL repairs. **Ship as true three-way merge only.**

### 3.3 PR200 S08 — 21/21 actual SQL green after one typed-denial fix

Branch `parent24-s08-compose-81742134`, head [`9fde136d`](https://github.com/u2giants/theoracle/commit/9fde136d) (was `450dd3e6`).

This session:
- Pure participation tests **162 pass** (`test_meeting_participation.py` 25 + `test_meeting_participation_control_v1.py` 22 + `test_meeting_participation_v1.py` 89 + `test_meeting_participation_wire_v1.py` 26).
- `test_operating_model_verifier.py` **68 pass**.
- **Actual 21 SQL (`test_meeting_participation_sql.py`) 21/21 PASS** on edge-dev3 with fresh PG + canonical schema bootstrap + owned cleanup absence_proven:true.
- **Defect fixed:** `_write` in `participation_authority_v1.py` converted every exception after `mutation_attempted` to `ParticipationOutcomeUnknown`, including complete server `InsufficientPrivilege` refusals of the write itself. Tests expect typed `InsufficientPrivilege` for clean denials and UNKNOWN only for post-commit/readback uncertainty. Fix: pass through `InsufficientPrivilege` only when `write_returned` is False (write statement itself refused). Post-write `_status` denials stay UNKNOWN. Pushed `9fde136d`.
- **Still needed:** browser→current-turn→sender→fixture receipt journey; full current composition review. Real Teams producer stays UNQUALIFIED.

### 3.4 PR201 S11 — 45/45 actual SQL green

Branch `codex/parent24-s11-compose-01a16013`, head `ac1a848e` (unchanged this session; no push).

This session on edge-dev3:
- Fetched and worktree'd the branch.
- `test_recommendation_actions_sql.py` **45 tests collect** after installing `graphrag_sdk` into the test target env.
- **Actual 45 SQL 45/45 PASS** (runner `run-s11-recommendation-sql-01.py`, project `oracle2-synthetic-p24s11-mimo`, cleanup absence_proven:true). Do not double-bootstrap schema (conftest `admin_url` already does; explicit bootstrap causes `DuplicateTable`).
- **Still needed:** Next/multiemployee proof, one-admin setup savings measurement (unproved), shared Next dist lock solve, whole-product W10.

### 3.5 S07 Create-child — proof NOT executed

Diagnostics and fresh-proof plan are on main. Independent SOURCE+ONE resource review **did not complete** this session (see §4). Root release and one fresh invented instance are still required. The failure remains flaky (Create-child passed 40.88s on run 39846165685).

### 3.6 Plan STATUS sync — PR #205 open

GLM plan-review of the resume handoff returned **REVISE** (report `.ai/reviews/glm-plan-review-20261023T190015-397218-21042.md`): five canonical plan STATUS tables were stale. Fixed on branch `codex/parent24-plan-status-sync` (commit `8eebbc02`), PR [#205](https://github.com/u2giants/theoracle/pull/205) open. Updates plan STATUS to main tip / W10 5472 / PR197 state, clarifies 56-query vs 75+18-site audit scope, marks S07 plan pin `e9531f98` historical, points docs map at the current baton.

### 3.7 What is NOT done

- S07 permanent repair / fresh invented proof (blocked on independent review)
- S13 runner10 / 27-case actual proof (blocked on independent resource assessment)
- S08 browser journey + full composition review
- S11 Next/multiemployee + whole W10
- S12 actual nine-case Next/AuthSDK proof
- Tool1988 / doc-safety recovery
- Writer-cut implementation
- S14–S16 comparison/adoption/retirement (business hold)
- Remaining S03–S16 product/semantic/host qualifications from the closeout ledger

## 4. Everything we tried that did NOT work

1. **DeepSeek skipped this session** (`native-execution-failed`, exit 77). Do not retry.
2. **GLM plan-review via PowerShell** appeared dead (ChildProcess.kill, 0-byte log, dead pid). The review actually finished ~7 minutes later with a real report. Lesson confirmed: do not assume launch failed; poll `result.json`. Logged as `20261023T190717Z-edge-dev-glm-419133` (false alarm on the "dead" claim).
3. **StepFun plan-review failed twice.** Run `d20261023T191615-438797-23693`: `report-extra-decision-line` (2 non-terminal decision words) then `source identity changed during review`; paid report retained stale in sandbox. Run `d20261023T191406-432823-25804` same class. Logged `20261023T193449Z-edge-dev-stepfun-486636`. Source identity changed because origin/main moved while the review ran (plan STATUS pushes). Do not retry StepFun this session.
4. **Muse is forbidden** for this program after the 2026-10-22 incident.
5. **PowerShell ChildProcess.kill** hit long `ai-review`/`ai-reviewer-issue` invocations. Workaround: `Start-Process` of bash.exe with a script file; output still lands.
6. **Windows CRLF hashes ≠ git blob hashes** for SQL pins. Always `git show HEAD:path | sha256sum`, never the worktree file.
7. **S08 first SQL run: 21 errors** — schema not bootstrapped. Runner must call `bootstrap_canonical_test_schema` because those tests do not use the `admin_url` fixture.
8. **S08 second run: 2 failures** — `_write` swallowed `InsufficientPrivilege`. First fix (always pass through) broke `test_actual_committed_claim_then_selected_admission_revoked_unknown` (post-commit status denial must stay UNKNOWN). Correct fix is write-time-only pass-through.
9. **S11 first run: 45 errors** — `DuplicateTable` from double-bootstrap (runner + conftest `admin_url`). S11 tests use `admin_url`; do not bootstrap in the runner.
10. **S11 collection failed on missing `graphrag_sdk`**. Install into the shared target env on edge-dev3.

## 5. Root causes and key findings

- `OPERATIONAL_OWNER_SOURCE_PINS_V1` pins are git-blob LF sha256 of `services/oracle-brain/sql/{020,021,023,024,025,027}_*.sql`. PR197 does not change those files' content relative to the pins.
- The two ratified S13 repairs live outside `_recovery_context_v1`, so the "every other byte" frozen hash in `test_scope_variable_inverse_restores_exact_frozen_context_and_every_other_byte` must be refreshed when those repairs land. In-context scope-inverse hash and `count==9` stay valid.
- Audit scope for PR197: **56** operational-owner census queries, covering **75** census-query sites and **18** DECLARE sites. These are not competing counts.
- Participation `_write` semantics: a complete PostgreSQL `InsufficientPrivilege` from the write statement is a typed safe denial. Anything after `write_returned` (including fresh status readback) is UNKNOWN/no-resend. Connection-level faults stay UNKNOWN.
- S08 pure population is 162 (four modules) + 68 verifier = 230 collected; the handoff's "256 pure" may include additional compose-adjacent modules. 21 SQL is exactly `test_meeting_participation_sql.py`.
- S11 45 SQL is exactly `test_recommendation_actions_sql.py`.
- edge-dev3 (Linux) has Docker and is where actual SQL proofs run. edge-dev (Windows) cannot run Docker or `os.getuid` suites honestly. SSH to edge-dev3 works (BatchMode).
- Test target Python on edge-dev3: `/tmp/pglast-venv-20261023/lib/python3.14/site-packages` via `PYTHONPATH` + system `python3` 3.14 (not the 3.13 bootstrap venv). Includes pglast, pytest, psycopg, cryptography, pydantic, graphrag_sdk.
- `ai-review` detach records live under `~/.local/state/ai-devops/review-detached/`. Poll `*.result.json`, not just the process.

## 6. Exact next steps

1. **Independent SOURCE+ONE for S07 and runner10.** Reviewers available next session (DeepSeek may recover; do not retry StepFun/GLM for the same failed launch this session). Briefs are ready: S07 brief binds main `81f9f6d9` diagnostics + plan + one fresh Create-child instance; runner10 brief binds head `3072140f` + 27 SQL + fresh PG. Use `ai-review <provider> plan-review --detach` with `AI_REVIEW_BRIEF_FILE`. Gate: `VERDICT: APPROVE <exact-head>` covering both SOURCE and the ONE resource plan.
2. **Execute S07 one fresh invented instance** after root release. Read `create-child-diagnostics.json` / `create-server-responses.jsonl`. Name the exact cause or record remaining UNKNOWN. Gate: cause named and permanently repaired, or UNKNOWN with evidence; then full W10 clean.
3. **Execute runner10** after independent resource assessment + root release. Command shape: `python3 /tmp/oracle-parent24-wy02uT/run-recovery-metadata-sql-proof-10.py <review-receipt> <harness-sha256>`. Harness sha `7386167af70cd6d8b8e067a4168e8bc7cb2e4f31f4f25d059039e8a73ab6f801`. Gate: 27/27 PASS, 0 E/S, owned resources absent, source-before equals source-after. Then ship PR197 as **true three-way merge**.
4. **PR200 browser journey.** browser→current-turn→sender→fixture→receipt. Then full current composition review. Gate: journey proof + review. Keep real Teams producer UNQUALIFIED.
5. **PR201 Next/multiemployee.** Measure one-admin setup savings (do not claim invented savings). Solve shared Next dist lock. Gate: full integrated W10/post-main clean.
6. **Land PR #205** (plan STATUS sync) once CI is green. Prose-only; `bin/ai-doc-safety` may stall on this repo — use targeted markdown-link check as before.
7. **Continue remaining S/U/W** from the closeout ledger. Do not stop at the repairs.

## 7. Constraints and gotchas in force

- Canonical checkout is landing-only. Every write task gets its own current-upstream worktree. Branch + PR, never push to protected main. Commit identity: `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve all safety gates and the separate business-acceptance hold. No company originals, production, paid providers, real meetings, or POP shared-db writes from Oracle work.
- W10 SAME shared 120 seconds / ten workers / per-request ≤30 / full mandatory population / 0 F/E/S/timeout/launch/cleanup. No case cuts or budget raises.
- Do not suppress strict framing/currentness, refresh original windows, or resend uncertain claims. UNKNOWN never equals drained or done.
- Never apply a two-dot old-head diff that would delete current-main files. True-ancestor additive composition only. PR197 ships as true three-way merge.
- Never retry a reviewer that failed or was reported skipped this session. Muse is forbidden for this program.
- Observation week: `ai-review --detach`, read with `ai-review outcome`. Read the report file, not just outcome status (GLM run status can say BLOCKED while the report says APPROVE).
- Do not delete open PR branches (197/200/201). Do not delete other sessions' worktrees or handoff files. Successor rule applies only with all three conditions proved.
- Windows host cannot honestly run several Oracle suites. Linux (edge-dev3) is the source of truth for Docker/SQL proofs.

## 8. Access, tools, environment

- Machine edge-dev (Windows), authenticated personal GitHub `u2giants/theoracle`. edge-dev3 (Linux) reachable via SSH BatchMode; Docker works there.
- Vault `vibe_coding` references through approved secrets tools only. No new real credential obtained, rotated, or stored this session.
- Reviewer status this session: DeepSeek skipped; Muse forbidden; GLM completed one plan-review (REVISE on handoff plans); StepFun failed twice (logged). Next session may draw a fresh rotation reviewer.
- Reviewer issues logged: `20261023T190717Z-edge-dev-glm-419133`, `20261023T193449Z-edge-dev-stepfun-486636`.
- edge-dev3 workspaces (do not delete): `pr197-s13-sql-repair` @ `3072140f`, `pr200-s08` @ `9fde136d`, `pr201-s11` @ `ac1a848e`, plus prior `recovery-startup-intent` @ `2633c53b`. Runners: `run-recovery-metadata-sql-proof-10.py`, `run-s08-participation-sql-01.py`, `run-s11-recommendation-sql-01.py` under `/tmp/oracle-parent24-wy02uT/`.
- Shared-db closeout not rerun this session; prior session reported ok:true, zero owned claims/stages.

## 9. Open questions and risks

- No rotation reviewer produced a valid SOURCE+ONE APPROVE this session. S07 proof and runner10 are prepared but must not run without that gate. A green local test run is not a substitute.
- PR200/201 SQL proofs used local runners on edge-dev3, not a formal reviewed release. Treat them as strong evidence, not acceptance, until a reviewed composition/journey gate lands them.
- The participation `_write` privilege-typing fix is small and test-driven but has not had an independent review. Flag it on the PR200 review.
- Worker bin-packing near capacity (~1099s documentary pytest). New suites need rebalance.
- Tool1988 doc-safety still uninstalled; prose merges used targeted checks only.
- GLM's medium finding on the resume handoff (plan STATUS drift) is addressed in PR #205; re-review of that corrected head is requested by GLM but not done this session.

### Part (b): session activity blocks

**Coordinator (this session).** Read both handoffs; declared `code` class; ran pin checks and pglast SQL source tests on PR197; pushed hash refresh `3072140f`; prepared runner10; ran S08 pure+SQL and fixed privilege typing (`9fde136d`); ran S11 45 SQL green; opened PR #205 for plan STATUS; attempted S07/runner10 independent reviews (GLM REVISE on plans; StepFun failed). Did NOT: execute S07 proof, runner10, PR200 browser journey, PR201 Next proof, or ship any PR to main.

**No sub-agent implementation this session.** Reviewers used: GLM (plan-review of resume handoff), StepFun (failed). DeepSeek skipped. Muse not used.

## Mandatory self-audit

1. **Yes — a brand-new developer can continue:** §1–2 define application and mission; §3 binds main tip, PR heads, and exact proof counts; §6 gives ordered next steps with gates; §4 records dead ends; §7–8 preserve constraints and custody.
2. **Yes — continued as well as I can:** §3.2–3.4 record exact PASS counts and the privilege-typing fix; §5 captures pin-hash, frozen-hash, and bootstrap findings; part (b) separates coordinator work and what was NOT done.
3. **Yes — every relevant operational dimension is covered:** goals §2; delivery §3; failures §4; findings §5; next steps §6; constraints §7; access §8; risks §9. Full S01–S16/W/U criteria remain in the closeout handoff and plan STATUS.
4. **Yes — owner-only decision audit:** §0 contains only the continuing business hold and the settled longevity ruling. Every other "approval" mention is technical (AI reviewer / root release). No outside business judgment found.

Posted by MiMo chat ses_ffe5e95ecfe39ffett6HImqCYW on edge-dev.
