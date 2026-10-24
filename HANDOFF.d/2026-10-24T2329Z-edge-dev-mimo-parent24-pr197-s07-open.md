---
issue: 24
status: OPEN
owner: mimo/parent24-pr197-shipped-2026-10-24
---

# Parent24 after PR197 three-way ship: recovery SQL 27/27 green; S07/PR200/PR201 still open

Record owner: MiMo chat on edge-dev (session `ses_ffe5e95888a5affe9JZUUCmt0D`). Human-facing observations rechecked October 23–24, 2026, approximately 3:45–7:30 PM EDT (America/New_York), machine clock UTC stamp for this file `2026-10-24T2329Z`. Dated observations, not transferable authority. Program is NOT complete. No company use, production adoption, or parent closure is claimed.

## 0. Business decisions only the owner can make

**No new business question is outstanding now.** Continue every permitted structural and invented-data obligation before requesting company use. The business-acceptance hold stays until the whole readiness list is proved. Then present the entire genuine business-question list together, once.

**Already settled — do NOT re-ask:**
- October 22, 2026: Albert answered "Remain in force until withdrawn" to whether rules already approved should survive loss of approval authority. Applies only to the exact immutable assertion/version/scope previously approved. Already landed through PR182 and recorded on #29/the plans.
- The closeout, resume handoffs, and original completion request are not separate permission for company use.
- October 23, 2026: Albert said "muse and deepseek are working fine as reviewers" — this unblocked SOURCE+ONE reviews for this session after the prior session barred DeepSeek/StepFun/GLM/Muse. Treat that as a session-scoped routing correction, not a permanent registry change.

No technical review, platform access, schema decision, or source admission belongs in this section. The coordinator and assigned AI reviewers own those steps.

## 1. What this application is

The Oracle repository is POP Creations' evidence-backed company consultant ([u2giants/theoracle](https://github.com/u2giants/theoracle)). It ingests permitted originals and explicitly invited conversations/meetings, retains quote-level evidence, models connected workflows/history/conflicts/unknowns, and produces cited answers under current permissions. The outcome is explainable business knowledge, not a test count.

Retained application: Next/TypeScript on Vercel, Trigger.dev workers, Supabase. Replacement: isolated Python/PostgreSQL/FalkorDB/stock GraphRAG operating model with protected mTLS boundaries. Coolify owns app namespaces; Ansible owns host changes.

Authoritative sources, STATUS first:
- [plan_oracle_consultant_overhaul.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_consultant_overhaul.md) and [parent #24](https://github.com/u2giants/theoracle/issues/24)
- [plan_oracle_workflow_integrity.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_workflow_integrity.md), [plan_oracle_source_processing_qualification.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_source_processing_qualification.md), [plan_oracle_replacement_documentary_journey.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_replacement_documentary_journey.md), [plan_oracle_native_fresh_v2.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_native_fresh_v2.md)
- Closeout of record (NOT retired): [2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md)
- Prior batons (NOT retired this wrap-up; successor rule not fully proved): [2026-10-23T1425Z-edge-dev-mimo-parent24-resume.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-23T1425Z-edge-dev-mimo-parent24-resume.md), [2026-10-23T1943Z-edge-dev-mimo-parent24-phase-progress.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-23T1943Z-edge-dev-mimo-parent24-phase-progress.md)
- S07 plan (PR #207, open): [s07-create-child-fresh-proof-plan.md](https://github.com/u2giants/theoracle/blob/codex/parent24-s07-plan-muse-h1h7/docs/verification/oracle2/s07-create-child-fresh-proof-plan.md)

## 2. What we set out to do this session, and why

Albert asked: resume parent #24 from current main; get independent SOURCE+ONE resource review of the S07 brief and runner10 brief; after APPROVE run S07 one fresh invented instance and runner10; land PR #200 after the browser journey and PR #201 after Next/multiemployee; ship PR197 as a true three-way merge. Later: "muse and deepseek are working fine as reviewers" and "proceed on full speed" / spawn subagents. Then `/wrap-up`.

Technical objective: clear the SOURCE+ONE gate, execute the recovery SQL proof, ship PR197 additively, and advance S07/PR200/PR201 as far as review allows.

## 3. Current state — what is true right now

### 3.1 Main tip and shipped work

Main tip after this session's ship: merge commit [`4e365535`](https://github.com/u2giants/theoracle/commit/4e365535f294c28a804827bd9293885bd09b9e6c) (PR [#197](https://github.com/u2giants/theoracle/pull/197) MERGED 2026-10-23T21:59:29Z as a **true three-way merge**, not squash).

W10 on the PR197 merge head was green (`Oracle offline suites` pass). Prior main W10 **5472 success:true** (run 39855010833) remains the last full-population green on the pre-197 tip. Business acceptance false.

### 3.2 PR197 S13 recovery SQL — SHIPPED

Branch `codex/parent24-s13-sql-repair`, final shipped head [`c4d5df84`](https://github.com/u2giants/theoracle/commit/c4d5df84). Merge branch `codex/parent24-s13-sql-repair-merge` @ `c4d5df84` was pushed onto the PR branch then merged.

This session's proof chain:
1. Muse SOURCE+ONE **APPROVE** on `3072140f` ([report](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-23T1943Z-edge-dev-mimo-parent24-phase-progress.md) era head; local report `muse-plan-review-20261023T205800-621296-29310.md` under the review worktree).
2. Runner10 on edge-dev3: infra fault (psycopg missing — harness overwrites `PYTHONPATH`), then **22 failed / 5 passed** with `AmbiguousColumn: observed_at`.
3. Fix 1 (ratified): `#variable_conflict use_variable` in `_recovery_operational_denials_v1` because `meeting_participation_observations_v1.observed_at` collides with the function parameter. Head `c25ac51c`. Static 20/20 PASS.
4. Runner11: cleared AmbiguousColumn; **22 failed** on `RecoveryCurrentV1` `int_type` (`input_value='16808'` str) for `source_database_oid`.
5. Fix 2 (ratified): `source_database_oid` cast `oid::bigint` in `_recovery_census_v1` jsonb_build_object (PostgreSQL `to_jsonb(oid)` emits a string). Head `acf7d706`. Outside-context frozen hash refreshed.
6. **Runner12: 27/27 PASS, 0 F/E/S, `absence_proven: true`, `source_manifest_unchanged: true`.** Scratch `recovery-metadata-owned-sql-12`, project `oracle2-synthetic-p24rec12-mimo-<uuid>`, database `oracle_operating_model_test_fb721b167dee41d887ac3479fbe73f60`.
7. True three-way merge of `origin/main` into the PR branch (additive only; every main file kept). Conflicts resolved in `dev/oracle2/test_canonical_schema.py` (union 026 recovery + 024 question signatures), `scripts/oracle2/verify_workflow_integrity.py` (SYNTHETIC_MIGRATIONS includes 021/025/026), `recovery_contracts_v1.py` (took main's V2 superset). Verifier tests updated to the 12-item migration tail. First merge head failed W10 with 2 verifier assertion mismatches; fix `c4d5df84` then green.
8. Merged with `gh pr merge --merge --admin` (true merge commit, not squash).

GLM final-check APPROVE on `939cc280` plus the three-way-merge shipping rule from that review were honored.

### 3.3 S07 Create-child — plan still not approved

PR [#207](https://github.com/u2giants/theoracle/pull/207) open on branch `codex/parent24-s07-plan-muse-h1h7`, head [`f886989c`](https://github.com/u2giants/theoracle/commit/f886989c). Plan v3 rewritten from sealed source after Muse REJECT twice (`a693d210` and `9132df58`). Third Muse review of `f886989c` still **REJECT** (report `muse-plan-review-20261023T213157-676022-23280.md`): leftover medium items m5–m10 and minor n1–n8 (pre-child `try/finally` scope must include `start_unattended()`, `--basetemp` for artifact discovery, warmup-refusal files in the index, redaction hook beyond `error_message`, host-name drift edge-dev vs edge-dev3, remaining-time proxy labeling, etc.).

**No S07 fresh invented instance was executed.** Gate remains: SOURCE+ONE APPROVE on the plan+diagnostic upgrades, then one fresh run.

### 3.4 PR200 S08 and PR201 S11 — still open, reviews rejected

| PR | Branch | Head | State |
|---|---|---|---|
| [#200](https://github.com/u2giants/theoracle/pull/200) | `parent24-s08-compose-81742134` | [`9fde136d`](https://github.com/u2giants/theoracle/commit/9fde136d) | OPEN. SQL 21/21 and pure 230 already green. Journey plan + fail-closed runner prepared on edge-dev3 (`run-pr200-s08-journey-proof-01.py`). Muse SOURCE+ONE on the journey brief **REJECT**. Journey not executed. |
| [#201](https://github.com/u2giants/theoracle/pull/201) | `codex/parent24-s11-compose-01a16013` | [`ac1a848e`](https://github.com/u2giants/theoracle/commit/ac1a848e) | OPEN. SQL 45/45 already green. Next/multiemployee runner prepared with review-receipt gate (`run-s11-next-multiemployee-proof-01.py`). Setup savings 5→1 admin/pins measured test-only (UNPROVED for business). Next dist lock documented. Muse SOURCE+ONE **REJECT**. Not executed. |

Do not delete these branches.

### 3.5 What is NOT done

- S07 permanent repair / fresh invented proof (plan needs 4th Muse ACCEPT)
- PR200 browser→current-turn→sender→fixture→receipt journey after a valid SOURCE+ONE
- PR201 Next/multiemployee proof after a valid SOURCE+ONE
- S12 actual nine-case Next/AuthSDK proof
- Tool1988 / doc-safety recovery
- Writer-cut implementation
- S14–S16 comparison/adoption/retirement (business hold)
- Remaining S03–S16 product/semantic/host qualifications from the closeout ledger

## 4. Everything we tried that did NOT work

1. **Codex plan-review 401 Unauthorized** (`Missing bearer` on `api.openai.com/v1/responses`). `auth.json` `auth_mode=chatgpt`, tokens present, `last_refresh=2026-10-15`. Logged `20261023T205013Z-edge-dev-codex-595199`. Do not assume Codex reviews work until auth is repaired.
2. **Claude removed from the reviewer pool** (owner 2026-09-30: "take claude out of the reviewer pool… including the former approval-gate path"). Not usable for formal reviews.
3. **Gemini/Qwen quarantined** out of rotation (owner 2026-10-13). **Grok held for out-of-credit.**
4. **DeepSeek skipped this session** (`native-execution-failed` from 3:10 PM EDT) despite Albert saying it is working — the skip is session-scoped from an earlier launch. Muse worked.
5. **PowerShell `ChildProcess.kill`** on long `ai-review` / `Start-Process` invocations. Workaround that worked: `Start-Process` of `C:\Program Files\Git\bin\bash.exe` with a `.sh` file (NOT WindowsApps `bash.exe`, which is WSL with no distro). Output still lands in `~/.local/state/ai-devops/review-detached/`.
6. **Short SHA in `--assert-head`** caused `source-head-mismatch` (expected `f886989c`, actual full SHA). Always pass the full 40-char SHA.
7. **Runner10/11 harness overwrites `PYTHONPATH`**, dropping the pglast venv site-packages that hold `psycopg`. Invoke with `/tmp/pglast-venv-20261023/bin/python3`, not bare `python3`.
8. **Hyperscratch `mkdir` without `exist_ok`** — a precreated scratch dir raises `FileExistsError`. Move the old dir aside (retain artifacts) before re-run.
9. **First three-way merge head failed W10** with 2 `test_operating_model_verifier.py` assertions that still expected the old SYNTHETIC_MIGRATIONS list without 021/025/026. Fix the assertions; do not drop the migrations.
10. **Muse rejected the S07 plan three times** (H1–H7, then H-A–H-E/M-A–M-K, then m5–m10/n1–n8). Plan prose must be grounded in sealed source test names, env vars, and teardown order — not aspirational.
11. **PowerShell `TZ=America/New_York date` is not valid** on this host; use `Get-Date` with offset.

## 5. Root causes and key findings

- PostgreSQL `jsonb_build_object` / `to_jsonb(oid)` emits a **string**. Pydantic `int` fields need `oid::bigint` (or an explicit cast) or `model_validate` fails with `int_type` on `'16808'`.
- PL/pgSQL function parameter `observed_at` is **ambiguous** with `meeting_participation_observations_v1.observed_at`. `#variable_conflict use_variable` is the minimal fix when every bare `observed_at` in the function means the parameter.
- The two earlier ratified repairs (receipts `claim_id` join; `AS recovery_scope_item(value)`) plus these two are **four** recovery SQL defects. A fifth class of bug (verifier list drift) appeared only at W10 merge time.
- Windows CRLF hashes ≠ git blob hashes for SQL pins. Always `git show HEAD:path | sha256sum`.
- W10 `tests:` only sums JUnit from workers that wrote XML. A failing worker with JUnit present still counts its tests; `success:false` with full population means real case failures, not a registration cut.
- True three-way merge: `git merge origin/main` into the PR branch, resolve additively (keep every main file), then `gh pr merge --merge` (NOT `--squash`). A two-dot old-head diff would delete main-side files.
- Muse SOURCE+ONE reviews take ~4–10 minutes detached. Poll `ai-review outcome <id>`. Read the report file, not just the status word.
- S07 does not use conftest `admin_url`; its runner must call `bootstrap_canonical_test_schema` or the suite errors before any child (same class as S08's historical 21 errors).
- Working-hypothesis S07 path error type is always `RecallWireUncertaintyV1` (production `within()` erases the inner cause). A first S07 run may only be able to record UNKNOWN naming that impossibility.
- Fixture stack creates **9** cluster LOGIN roles (3 in `meeting_sql` + 6 in unattended `role()`), not 6; they survive a DB drop.

## 6. Exact next steps

1. **S07 plan v4.** Fix Muse leftovers in [s07-create-child-fresh-proof-plan.md](https://github.com/u2giants/theoracle/blob/codex/parent24-s07-plan-muse-h1h7/docs/verification/oracle2/s07-create-child-fresh-proof-plan.md): include `start_unattended()` in pre-child `try/finally`; pin `--basetemp`; add warmup-refusal files to the §7 index; implement redaction enforcement beyond `error_message`; one host name; label remaining-time as elapsed-proxy. Then Muse SOURCE+ONE again. Gate: `VERDICT: APPROVE <full-head-sha>`. Then one fresh invented instance.
2. **PR200 journey.** Read the Muse REJECT on the journey brief (`muse-plan-review-20261023T212501-656231-20253.md` under `C:/tmp/oracle-s08-compose/.ai/reviews/` on edge-dev; also copy from that worktree). Fix the brief/plan, re-review, then one-shot with receipt + `ai-task-gates check --before database`. Gate: browser→current-turn→sender→fixture→receipt proof + composition review. Keep real Teams producer UNQUALIFIED.
3. **PR201 Next/multiemployee.** Same pattern from Muse REJECT `muse-plan-review-20261023T212501-656236-13249.md`. Then one-shot Next proof + measure setup savings as test-setup only. Gate: full integrated W10/post-main clean.
4. **Continue remaining S/U/W** from the closeout ledger. Do not stop at the repairs.

## 7. Constraints and gotchas in force

- Canonical checkout is landing-only. Every write task gets its own current-upstream worktree. Branch + PR, never push to protected main. Commit identity: `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve all safety gates and the separate business-acceptance hold. No company originals, production, paid providers, real meetings, or POP shared-db writes from Oracle work.
- W10 SAME shared 120 seconds / ten workers / per-request ≤30 / full mandatory population / 0 F/E/S/timeout/launch/cleanup. No case cuts or budget raises.
- Do not suppress strict framing/currentness, refresh original windows, or resend uncertain claims. UNKNOWN never equals drained or done.
- Never apply a two-dot old-head diff that would delete current-main files. True-ancestor additive composition only. PR197 shipped as true three-way merge — keep that rule for future recovery integrations.
- Never retry a reviewer that failed or was reported skipped this session without a new reason. Muse is working (owner 2026-10-23). DeepSeek was session-skipped this run. Muse was forbidden for a prior 2026-10-22 incident in an older handoff — the 2026-10-23 owner message supersedes that for routing; do not re-litigate.
- Observation week: `ai-review --detach`, read with `ai-review outcome`. Read the report file, not just outcome status.
- Do not delete open PR branches (200/201/207). Do not delete other sessions' worktrees or handoff files.
- Windows host cannot honestly run `os.getuid`/`O_PATH`/`mkfifo`/hnswlib suites. Linux (edge-dev3) is the source of truth for Docker/SQL proofs.
- Always use full 40-char SHAs in `--assert-head`.
- Invoke edge-dev3 runners with `/tmp/pglast-venv-20261023/bin/python3`.

## 8. Access, tools, environment

- Machine edge-dev (Windows), authenticated personal GitHub `u2giants/theoracle`. edge-dev3 (Linux) reachable via SSH BatchMode; Docker works there.
- Vault `vibe_coding` references through approved secrets tools only. No new real credential obtained, rotated, or stored this session. Codex auth is stale (`last_refresh=2026-10-15`, 401); repair is a tooling task, not a secret to paste.
- Reviewer status this session: Muse SOURCE+ONE used successfully (runner11 APPROVE, S07 three REJECTs, PR200/201 REJECTs). DeepSeek skipped. Codex 401. Claude out of pool. Gemini/Qwen quarantined. Grok out of credit.
- edge-dev3 artifacts to keep (do not delete): `/tmp/oracle-parent24-wy02uT/` runners 10–12, manifests, `recovery-metadata-owned-sql-10*`, `recovery-metadata-owned-sql-11*`, `recovery-metadata-owned-sql-12`, Muse APPROVE receipt `muse-runner11-source-plus-one-approve.md`, PR200 journey plan/runner, PR201 Next runner.
- Session worktrees created this wrap-up that are safe to remove after review: `oracle-wt-s07-review`, `oracle-wt-r10-review`, `oracle-wt-s13-merge` (merge branch pushed; PR197 merged). Keep `oracle-wt-s07-plan` until PR #207 lands or is abandoned with the branch kept. Keep `/tmp/oracle-s08-compose` and `/tmp/oracle-s11-compose-01a16013` for PR200/201.
- Shared-db: this session did not touch `popcre/shared-db` or hold a shared-db claim.

## 9. Open questions and risks

- S07 Create-child remains flaky and unexplained (historical fail 39760061151, pass 39846165685). A green single instance is not a repair. Plan v3 already states this; v4 must keep it.
- PR200/201 W10 failures on their branches may be inherited; read counts and JUnit before calling a regression.
- Worker bin-packing near capacity (~1099s documentary pytest). New suites need rebalance.
- Tool1988 doc-safety still uninstalled; prose merges used targeted checks only.
- Four recovery SQL defects were found only by actually running the 27-case proof after SOURCE+ONE. Do not trust static audit alone for name-collision or JSON-type bugs.
- Codex auth 401 is an unresolved tooling defect (logged). Do not dispatch Codex reviews until repaired.

### Part (b): session activity blocks

**Coordinator (this session).** Read three handoffs; dispatched Muse SOURCE+ONE; executed runner10/11/12 on edge-dev3; ratified two new SQL defects; built and shipped PR197 as a true three-way merge; prepared S07 plan v3 (still REJECT); prepared PR200/201 journey runners (reviews REJECT). Sub-agents used: general-1 (PR200 journey plan), general-2 (PR201 Next runner), general-3 (S07 plan v3), general-4 (runner11 + Muse APPROVE), general-5 (PR200/201 Muse briefs). All returned. No shared-db claims.

**general-1 PR200.** Asked for browser→receipt journey. Did: pure 230 green on `9fde136d`; no reviewed journey runner existed; wrote plan + fail-closed skeleton on edge-dev3. Did NOT execute the journey.

**general-2 PR201.** Asked for Next/multiemployee. Did: prepared runner with review-receipt gate; measured setup 5→1 test-only; documented Next dist lock. Did NOT execute Next/DB.

**general-3 S07 plan v3.** Asked to rewrite the plan from sealed source. Did: commit `f886989c`, grounded H-A..L-E. Did NOT obtain Muse APPROVE (third REJECT on m5–n8).

**general-4 runner11.** Asked to re-review and run after the observed_at fix. Did: runner11 + Muse APPROVE on `c25ac51c`; execution found the fourth defect (`source_database_oid` type). Did NOT reach 27/27 (coordinator landed that on runner12).

**general-5 PR200/201 reviews.** Asked to launch SOURCE+ONE for both. Did: two Muse detached runs; both REJECT. Did NOT execute any journey.

## Mandatory self-audit

1. **Yes — a brand-new developer can continue:** §1–2 define application and mission; §3 binds main tip `4e365535`, PR197 ship proof, open PRs 200/201/207; §6 gives ordered next steps with gates; §4 records dead ends; §7–8 preserve constraints and custody.
2. **Yes — continued as well as I can:** §3.2 records the exact 27/27 packet and four defects; §5 captures oid-jsonb and observed_at findings; part (b) separates every sub-agent including what they did NOT do.
3. **Yes — every relevant operational dimension is covered:** goals §2; delivery §3; failures §4; findings §5; next steps §6; constraints §7; access §8; risks §9. Full S01–S16/W/U criteria remain in the closeout handoff and plan STATUS.
4. **Yes — owner-only decision audit:** §0 contains only the continuing business hold, the settled longevity ruling, and the 2026-10-23 reviewer-routing correction. Every other "approval" mention is technical (AI reviewer / root release). No outside business judgment found.

Posted by MiMo chat ses_ffe5e95888a5affe9JZUUCmt0D on edge-dev.
