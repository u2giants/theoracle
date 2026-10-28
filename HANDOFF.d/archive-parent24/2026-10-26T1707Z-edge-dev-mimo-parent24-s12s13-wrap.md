---
issue: 24
status: OPEN
owner: mimo/parent24-s12s13-wrap-2026-10-26
---

# Parent24 wrap: S13 full recovery green; S12 live 8/1/0/0 with Case 1 TLS isolation open

Record owner: MiMo chat on edge-dev (session ses_ffe5e875a316cffeMODFYQK7Yl). Observations rechecked October 26, 2026, approximately 10:30 AM–1:10 PM EDT (America/New_York). Dated observations, not transferable authority. Program is NOT complete. No company use, production adoption, or parent closure is claimed. Business-acceptance hold remains.

## 0. Business decisions only the owner can make

No new business question is outstanding. Continue every permitted structural and invented-data obligation before requesting company use. Then present the entire genuine business-question list together, once.

Already settled — do NOT re-ask:

- October 22, 2026: "Remain in force until withdrawn" for previously approved immutable assertion/version/scope (PR182 / #29).
- October 23, 2026: "muse and deepseek are working fine as reviewers" — session-scoped routing. Muse used this session (SOURCE+ONE APPROVE twice).
- October 25–26, 2026: PR200 merge is an owner-timing choice ("when Albert wants it"); APPROVE + 21 SQL + one-shot already done. Do not ask again; merge when he says, or if he never says, leave the PR open and keep the branch.
- Closeout/resume/completion handoffs are not permission for company use.

PR200 merge timing is the only owner-facing action left on this thread, and it is already settled as "when you want it." Recommendation: merge when convenient; it is not on the critical path for S12/S13.

## 1. What this application is

The Oracle (u2giants/theoracle) is POP Creations' evidence-backed company consultant. Replacement: isolated Python/PostgreSQL/FalkorDB/GraphRAG operating model with protected mTLS boundaries. STATUS-first sources: plan_oracle_consultant_overhaul.md and parent #24, plus the four companion plans on main. Closeout of record (NOT retired): 2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md. Prior baton (on PR201 branch, not yet successor-retired): 2026-10-26T1413Z-edge-dev-mimo-parent24-pr201-muse-oneshot-green.md.

## 2. What we set out to do this session, and why

Resume parent #24 as COORDINATOR after PR201 Muse APPROVE + one-shot green. Named next actions: (1) S12 live nine-case under ai-task-gates check --before database after SOURCE+ONE and root release — gate JUnit 9/0/0/0; (2) S13 full recovery (dump/restore, archive child, RTO/RPO). Holds: S14–S16 business-held; Tool1988 StepFun pacer fix before landing; PR200 merge when Albert wants it. Keep real Teams producer UNQUALIFIED. Business-acceptance hold remains.

## 3. Current state — what is true right now

### 3.1 S13 full recovery — EXERCISE GREEN (branch pushed, not merged)

Branch https://github.com/u2giants/theoracle/tree/codex/parent24-s13-full-recovery-20261026 head https://github.com/u2giants/theoracle/commit/48cfc494d06056ab2736ac1456621b0e179134b3

One isolated synthetic DR exercise (`test_s13_full_recovery_exercise_v1.py`) on edge-dev3:

| # | Test | Result |
|---|---|---|
| 1 | test_native_dump_restore_fresh_stores | PASSED |
| 2 | test_archive_child_pack_verify_unpack | PASSED |
| 3 | test_private_roots_mode_and_checksums | PASSED |
| 4 | test_vector_embeddings_survive_restore | PASSED |
| 5 | test_license_status_recorded_honestly | PASSED |
| 6 | test_once_cost_tail_survives_restore | PASSED |
| 7 | test_019_checkpoint_paused_workflow_resumable | PASSED |
| 8 | test_acknowledged_events_accounted_after_replay | PASSED |
| 9 | test_denied_deleted_evidence_remains_unavailable | PASSED |
| 10 | test_rto_rpo_measured_honestly | PASSED |
| 11 | test_scale_recorded | PASSED |

**JUnit: 11 passed, 0 failed, 0 errors, 0 skipped.** JUnit XML SHA-256 `0070bccae6de7bf145ef5ddb836db98941e1d3493d4184e48651339c667d18bf`.

Measured: service restore (RTO) **1.275 s** (target ≤ 60 min); ledger backup **0.212 s** (target ≤ 15 min); RPO exposure 0.0 s only because backup ran immediately before the simulated outage — production RPO depends on backup cadence, not restore speed. Tested scale: 25 accepted events, 8 artifacts, 5 conversation events, 1 once-intent, 1 cost observation, 9 private archive files, 8 vector embeddings. Dump 1,249,718 bytes / 120 tables.

Evidence on the branch: docs/verification/oracle2/S13-recovery.md, docs/verification/oracle2/s13-full-recovery-20261026/ (README.md, dr-result.json, runner-result.json, s13-full-recovery-junit.xml). Also on edge-dev3 under /tmp/oracle-parent24-wy02uT/s13-full-recovery-run-20261026/.

Still UNPROVEN for S13: live FalkorDB graph census after full ledger replay; real vector-model license proof (synthetic embedder only); production RPO under real backup cadence; alerts/retention/quota operational exercise; source/runtime admission beyond metadata SQL; business acceptance; real Teams producer.

### 3.2 S12 live nine-case — 8/1/0/0 after Muse APPROVE; Case 1 TLS isolation OPEN

**First packet (frozen consumer HEAD 7defd1ee):**

- Muse SOURCE+ONE **APPROVE** run `20261026T144920-218656-5437` on full 40-char head `7defd1eeeaccad46ba04b96952c439305065c796`. Report: .ai/reviews/muse-plan-review-20261026T144920-218656-5437.md. Receipt SHA256 `5afd68da91747b66fb20d1ae0587222c807890698cc1fe21b776f03971fad4ea`.
- Database gate ALLOW (owner ruling 2026-10-14: database writes skip second-AI approval).
- Root one-fresh-release recorded naming HEAD 7defd1ee and runner SHA `5b05cb4a41a8bc50b6284b4c1d09fa99b7003deb0680e8e9fd5063fd48731911`.
- Live runner 04 on edge-dev3: cases 2–9 (eight malformed employee-pair negatives) **all PASS**. Case 1 failed at proof line 87: after `disable-a`, `action(b,'Read current knowledge',1)` returned 503 instead of 200. Cleanup `absence_proven: true`. Source manifest unchanged.

**Case 1 diagnosis and fix attempts** (branch https://github.com/u2giants/theoracle/tree/codex/parent24-s12-case1-fix-20261026):

| Commit | Change | Result |
|---|---|---|
| efb291d1 | bounded reconnect after owned close | insufficient |
| d2eb2913 | unique graph TLS identity per recipient | regressed first positive (503 at line 59) |
| afc0390b | unique graph key-pair + WORKER URI | 6 positives restored; Case 1 still fails at line 87 |

Current head https://github.com/u2giants/theoracle/commit/afc0390bd9a720e33b4be6e2e6c5d7249cce7d66. Muse SOURCE+ONE APPROVE on this fix path (run `20261026T161315-304419-14595` for d2eb2913; later Muse run on afc0390b also APPROVE).

Live after afc0390b: JUnit **9 tests, 1 failure, 0 errors, 0 skipped** (cases 2–9 still pass). Failure at `workspace-next-recipients-proof.ts:87` — `action(b,'Read current knowledge',1)` expects 200, gets 503.

Verbatim root-cause evidence from workspace-two-recipients.stdout after the foreign-process negative:

```
ORACLE-DIAG listener deny path=/v1/employee/answer exc=PermissionError: process outside current qualified model
ORACLE-DIAG listener deny path=/v1/employee/answer exc=ConnectionError: Error connecting to localhost:46357.
ConnectionResetError   (redis/asyncio/sslproto.py:581 _on_handshake_complete)
redis.exceptions.ConnectionError: Error connecting to localhost:46357.
```

Stack for B: `answer_workspace_v1` → `projection.load()` → `_check_graph_snapshot` → `connection.query` → falkordb `ro_query` → redis `pool.get_connection` → `ensure_connection` → TLS handshake `ConnectionResetError`.

**Critical finding:** a non-TLS two-`FalkorDBConnection` isolation repro on edge-dev3 (close A, then B.query and a fresh C) **all succeed**. Pools are not shared. The remaining defect is **TLS-specific** (client-cert session teardown / Falkor TLS listener reset after one client pool `aclose()`), not a shared redis pool.

### 3.3 Prior state that still holds

- PR201 (#201) Muse SOURCE+ONE APPROVE at 0d155a05 + one-shot green. PR open — merge through normal release path. Do not push to protected main.
- PR200 (#200) DONE technically; merge when Albert wants it. Keep branch parent24-s08-compose-81742134.
- PR207 / PR210 still open branches (S07 plan v5 / diagnostics). Do not delete.
- S07 W10 two clean full runs at main 4e365535 (5472/0). Business acceptance false.
- Real Teams producer UNQUALIFIED. Business-acceptance hold remains.
- S14–S16 company comparison / adoption / retirement — business hold. Structural writer-cut on codex/parent24-writercut-tool1988-20261026.
- Tool1988 / doc-safety HELD: StepFun pacer `tests/test-ai-stepfun.sh::paces_before_call` fails CI (1s gap vs 2s under concurrency). PR1988 stays parked.

### 3.4 What is NOT done

- S12 Case 1 live 9/0/0/0 (TLS isolation after peer projection close).
- PR201 / PR200 / S13-recovery / case1-fix not merged to main.
- Tool1988 StepFun pacer fix + separate review.
- S14–S16 business-held. Real Teams producer qualification.
- Remaining S03–S16 product/semantic/host qualifications and W01–W12 / U1–U6 from the closeout ledger.

## 4. Everything we tried that did NOT work

- **pglast venv lacked psutil** — runner 04 died on `import psutil` in verify_workflow_integrity.py before any test. Fix: copy system psutil into /tmp/pglast-venv-20261023 site-packages.
- **Child pytest PYTHONPATH overwrite** — the runner sets PYTHONPATH to workspace-only paths, so psycopg from the venv vanished and collection failed with ModuleNotFoundError. Fix: use the pglast python as sys.executable with psutil installed in that venv (do not rely on a parent PYTHONPATH).
- **Bounded reconnect (efb291d1)** — retry around a destroyed TLS session does not fix a peer-side reset. Wrong layer.
- **Unique graph TLS cert per recipient with spiffe://…/invented-workspace-graph-N (d2eb2913)** — Falkor TLS listener accepts WORKER URI; custom URI caused the first positive `action()` to 503 (`Replacement control unavailable`). Regression.
- **Unique key-pair with WORKER URI (afc0390b)** — restored the 6 positives but did not fix B after A's `_close_owned_projection_v1`.
- **Assuming a shared redis pool** — disproved by non-TLS isolation repro (edge-dev3): two FalkorDBConnection objects, close A, B still queries, fresh C works.
- **PowerShell + SSH heredocs** — parse errors. Ship scripts as base64 (still true).
- **Muse run IDs from the subagent were not in the Windows detach dir** — do not trust a subagent-reported Muse run id without `ai-review outcome` on this machine. Coordinator re-ran Muse itself (`d20261026T161311-304200-6649` → APPROVE).

## 5. Root causes and key findings

- S12 Case 1: foreign-process negative (`qualified_workspace_v1.py` `PermissionError: process outside current qualified model`) runs on A's backend, then `finally` calls `_close_owned_projection_v1` (`replacement_result_service_v1.py`) → `projection.connection.close()` → `FalkorDBConnection.close()` → `BlockingConnectionPool.aclose()`. B's next request builds a **new** FalkorDBConnection and dies in `redis/asyncio/sslproto.py:581` `ConnectionResetError` during TLS handshake. Non-TLS isolation works; TLS does not. Next step is TLS-session/SSLContext/`ssl_check_hostname`/server-side reset analysis, or per-recipient Falkor instances — **not** more retries.
- `pool_timeout=1` and `retry_count=1` in `connected_answer_settings_v1.py` `projection()` are very tight; a post-close handshake can look like ConnectionResetError if the server is slow to accept. Worth measuring before blaming the server.
- A's expected 503 for `disable-a` is proxy-level (`proxy.ts` `readInstalledEmployeeBindingV1` on `disabledAt!==null`) and is correct fail-closed — no route-handler log. Absence of `Oracle qualified read refused` does not mean the request never happened.
- The foreign-process negative is green partly for the wrong reason (backend `PermissionError` → `_deny` 503 masked as transport). Named finding; does not by itself block Case 1's 9/0/0/0.
- S13 full recovery is honestly proven at synthetic scale with stated RPO limitation. Metadata recovery (27/27 at a0a7465f) is not full restore; this exercise is the first full synthetic DR proof.
- `ai-task-gates` must run from the worktree holding the change set; Windows canonical checkout falsely escalates to `deployment (protected)`.
- Complete-source runner packets cannot accept mutated workspace sources — after any source fix, rebuild manifest + runner SHA and re-run Muse SOURCE+ONE on the new head.

## 6. Exact next steps

1. **S12 Case 1 TLS isolation** — finish to JUnit 9/0/0/0 on branch codex/parent24-s12-case1-fix-20261026 (or successor). Start from the stack in §3.2 and the non-TLS repro result in §5. Rebuild manifest+runner, Muse SOURCE+ONE on the new head, live runner on edge-dev3. Gate: JUnit {tests:9,failures:0,errors:0,skipped:0}, absence_proven:true, source-manifest unchanged. You'll know it worked when Case 1 `action(b)` after `disable-a` returns 200 and all eight negatives still pass.
2. **S13 remaining UNPROVEN list** (§3.1) — graph census after full ledger replay, real vector license, alerts/retention/quota, production RPO honesty. Gate: named UNPROVEN rows shrink with exact JUnit, never a silent skip.
3. **PR201 / S13-recovery / case1-fix merge** through the normal release path when the program is ready. Do not push to protected main.
4. **PR200 merge** when Albert wants it. Keep branch parent24-s08-compose-81742134.
5. **Tool1988** — separately reviewed StepFun pacer fix on top of 2634e51f before landing. Do not claim green CI before that.
6. **S14–S16** stay held until business acceptance. Structural writer-cut pieces on codex/parent24-writercut-tool1988-20261026.
7. Continue remaining S/U/W from the closeout ledger. Real Teams producer stays UNQUALIFIED.

## 7. Constraints and gotchas in force

- Canonical checkout is landing-only. Every write task gets its own current-upstream worktree. Branch + PR, never push to protected main. Commit identity Albert Hazan <u2giants@users.noreply.github.com>.
- Preserve all safety gates and the separate business-acceptance hold. No company originals, production, paid providers, real meetings, or POP shared-db writes from Oracle work.
- W10 SAME shared 120s / ten workers / per-request ≤30 / full mandatory population / 0 F/E/S/timeout/launch/cleanup. No case cuts or budget raises.
- Do not suppress strict framing/currentness, refresh original windows, or resend uncertain claims. UNKNOWN never equals drained or done. Never-written refusals are deterministic, not UNKNOWN.
- Never apply a two-dot old-head diff that would delete current-main files. True three-way merge for recovery integrations.
- Observation week: ai-review --detach, read with ai-review outcome. Full 40-char --assert-head SHAs only. Muse via Git bash.exe launcher with PATH: jq, Python313, PowerShell 7, mingw64 bin, /usr/bin before System32. AI_POOL_CALLER=mimo AI_IMPLEMENTER_ENGINE=mimo.
- Do not delete open PR branches (200/201/207/210). Do not delete other sessions' worktrees or handoff files. Successor rule applies to predecessor handoffs only when their work is verified on main and obligations are carried forward.
- edge-dev3 runners: PATH including /home/ahazan/.local/bin; python /tmp/pglast-venv-20261023/bin/python3 (psutil now copied in). Docker/SQL proofs are Linux-only.
- Windows core.autocrlf=true corrupts runner SHA on checkout; use git cat-file blob byte writes for exact-bytes artifacts.
- Move leftover scratch dirs aside before reruns (*-prev-<ts>). Receipt files are operator-minted JSON outside scratch and must match the checked-out head.
- PowerShell corrupts SSH heredocs and inline Python. Ship scripts as base64.
- Sealed SQL 017 and 025 unchanged — do not weaken fail-closed for genuine integrity failures.
- After any source mutation, the frozen complete-source manifest no longer matches: rebuild manifest + runner SHA and re-review before the live gate.

## 8. Access, tools, environment

- Machine edge-dev (Windows), authenticated personal GitHub u2giants/theoracle. edge-dev3 (Linux) via SSH BatchMode; Docker works there.
- Muse SOURCE+ONE used successfully this session (APPROVE on 7defd1ee and on case1-fix heads). Read outcomes with `ai-review outcome <id>`.
- edge-dev3 S12 workspace: /tmp/oracle-parent24-wy02uT/workspace-preauth-current (was 7defd1ee; now at case1-fix head when that work runs). S13 exercise worktree /home/ahazan/repos/oracle on branch codex/parent24-s13-full-recovery-20261026.
- Windows worktrees: C:/tmp/oracle-s12-source-7defd1ee (now on codex/parent24-s12-case1-fix-20261026), C:/tmp/oracle-s12-brief-20261026, C:/tmp/oracle-s13-repair-20261026.
- Secrets: none appeared this session except ephemeral synthetic test-fixture passwords (invented FalkorDB/history logins, regenerated per run). 1Password vault vibe_coding only if needed.
- Shared-db: no POP shared-db claims this session.

## 9. Open questions and risks

- S12 Case 1 is the single live proof blocker. The TLS-after-close reset is not yet explained; do not claim 9/0/0/0 without a green live run.
- S13 full recovery is synthetic-scale only. Do not treat 1.275s RTO as a production figure.
- PR201 is Muse-APPROVE + one-shot green but not merged. Release policy and W10-fit on the final merge head still apply. Do not infer company acceptance.
- Tool1988 will not land until StepFun pacer concurrency is separately fixed and reviewed.
- Browser TLS remains a named weakening (ignoreHTTPSErrors: true) versus "trust only the owned fixture CA bundle". Backend mTLS and DB verify-full are unaffected.
- Real Teams producer UNQUALIFIED. Business-acceptance hold remains.

## Part (b) — session activity blocks

**Coordinator (this session).** Read named baton + parent #24. Drove S12 Muse SOURCE+ONE APPROVE, DB gate, root release, live runner (8/1/0/0). Drove S13 full-recovery dispatch to green 11/11. Diagnosed Case 1 TLS reset (non-TLS isolation repro). Re-ran Muse when subagent run ids were not on this machine. Did NOT merge any PR to main.

**general-1 (S13 full recovery).** Built `test_s13_full_recovery_exercise_v1.py` + runner. Four setup failures (sources status CHECK, processing_model_admissions_v1 NOT NULL columns, archive path prefix, unpack return arity) then green 11/11 with measured RTO/RPO. Head 48cfc494 on codex/parent24-s13-full-recovery-20261026. Returned success. Note: branch lived in edge-dev3 `/home/ahazan/repos/oracle`; Windows clone needed `git fetch` to see it.

**general-2 (S12 Case 1 fix).** Proved foreign-process → `_close_owned_projection_v1` → B TLS reset chain. Three commits (efb291d1, d2eb2913, afc0390b) on codex/parent24-s12-case1-fix-20261026. Did not reach 9/0/0/0. Cancelled mid-stall after diagnosis-only reports; coordinator took over the isolation repro. Returned partial — fix not complete.

## Mandatory self-audit

1. Yes — §1–2 define application and mission; §3 binds heads, Muse run IDs, JUnit lines, and every named hold with GitHub URLs; §6 gives ordered next steps with gates.
2. Yes — §3 records exact HEADs and Muse run IDs; §4/§5 capture every failed attempt and the TLS-vs-pool distinction; part (b) separates every subagent.
3. Yes — goals §2; delivery §3; failures §4; findings §5; next steps §6; constraints §7; access §8; risks §9. Full S01–S16/W/U criteria remain in the closeout handoff and plan STATUS.
4. Yes — §0 contains only the continuing business hold and settled rulings (including PR200 merge timing). Every other approval is technical (Muse SOURCE+ONE / W10 / root release). Sweep of §1–§9 and part (b) found no other owner-only business judgment.

Posted by MiMo chat ses_ffe5e875a316cffeMODFYQK7Yl on edge-dev.
