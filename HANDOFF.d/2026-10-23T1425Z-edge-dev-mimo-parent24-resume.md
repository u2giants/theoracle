---
issue: 24
status: OPEN
owner: mimo/parent24-resume-2026-10-23
---

# Parent24 resume after closeout: recorded verification failures first, then remaining phases

Record owner: MiMo chat on edge-dev (session ses_ffe5e9b3fe2e6ffeolqy4r1hyC). Human-facing observations below were rechecked October 23, 2026, approximately 8:00 AM–10:25 AM EDT, America/New_York. These are dated observations, not transferable authority. This session resumed from the closeout handoff and advanced multiple phases; the program is NOT complete. No company use, production adoption, or parent closure is claimed.

## 0. Business decisions only the owner can make

**No new business question is outstanding now.** Continue every permitted structural and invented-data obligation before requesting company use. The continuing business boundary from the closeout is intentional and unchanged: real company originals, employees, company questions/reports/grading, business acceptance, production adoption and retirement remain separately held. Recommendation: retain that hold until all permitted technical readiness is independently proved. Then present the entire genuine business-question list together, once.

**Already settled — do NOT re-ask:**
- October 22, 2026: Albert answered "Remain in force until withdrawn" to whether rules already approved should survive loss of approval authority. It applies only to the exact immutable assertion/version/scope previously approved. No successor/source revision/new scope inherits approval. Already landed through PR182 and recorded on #29/the plans.
- The closeout and the original completion request are not separate permission for company use.

No technical review, platform access, schema decision, source or resource admission belongs in this section. The coordinator and assigned AI reviewers own those steps.

## 1. What this application is

[The Oracle repository](https://github.com/u2giants/theoracle) is POP Creations' evidence-backed company consultant. It ingests permitted originals and explicitly invited conversations/meetings, retains quote-level evidence, models connected workflows/history/conflicts/unknowns, and produces cited answers, recommendations and operational views under current permissions. The outcome is explainable, correct business knowledge, not a test count.

The retained application is Next/TypeScript on Vercel, Trigger.dev workers and Supabase. The replacement is an isolated Python/PostgreSQL/FalkorDB/stock GraphRAG operating model with protected mTLS boundaries, durable SQL claims, original deadlines and immutable evidence. Keep FalkorDB/GraphRAG and the clean replacement. Coolify owns app namespaces; Ansible owns host changes.

Authoritative requirement sources, STATUS first:
- [plan_oracle_consultant_overhaul.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_consultant_overhaul.md) and [parent #24](https://github.com/u2giants/theoracle/issues/24), children #25–40, [S03/#27](https://github.com/u2giants/theoracle/issues/27), proof card [#58](https://github.com/u2giants/theoracle/issues/58).
- [plan_oracle_workflow_integrity.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_workflow_integrity.md), [plan_oracle_source_processing_qualification.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_source_processing_qualification.md), [plan_oracle_replacement_documentary_journey.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_replacement_documentary_journey.md), [plan_oracle_native_fresh_v2.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_native_fresh_v2.md).
- Closeout of record: [2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md). That file is NOT retired — it still holds the full S/W/U criteria and many open obligations this session did not finish.
- Original completion prompt: [2026-10-21T1947Z-edge-dev3-codex-parent24-completion-prompt.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-21T1947Z-edge-dev3-codex-parent24-completion-prompt.md).

## 2. What we set out to do this session, and why

Albert asked: pull the latest repo and resume parent #24 from current main using sub-agents (no more than 3 simultaneously), read the complete closeout handoff first, begin with its recorded verification failures, then continue every remaining phase, preserving all safety gates and the separate business-acceptance hold.

Technical objective: (a) address the two recorded verification failures (S07 Create-child W10 failure; S13 recovery SQL 25/27 failure), (b) compose the parked source leaves onto current main, (c) keep going through remaining ready phases with bounded sub-agents.

## 3. Current state — what is true right now

### 3.1 Main tip and landed work

Main tip **889b42d4** (checked 2026-10-23T14:23Z). This session landed on main via squash PRs:

| PR | What | State |
|---|---|---|
| [#195](https://github.com/u2giants/theoracle/pull/195) | S12-04 successor public review brief | MERGED |
| [#196](https://github.com/u2giants/theoracle/pull/196) | S07 Create-child fixture-only diagnostics | MERGED |
| [#199](https://github.com/u2giants/theoracle/pull/199) | S14 writer-cut source-owner design + inventory | MERGED |
| [#202](https://github.com/u2giants/theoracle/pull/202) | S07 Create-child fresh invented proof plan | MERGED |
| [#198](https://github.com/u2giants/theoracle/pull/198) | S09 question compose + TLS diagnostics + W10 population/timeout/lease fixes | MERGED (W10 **5472 success:true**) |
| [#203](https://github.com/u2giants/theoracle/pull/203) | S13 fixed-child V2 DTOs + classic-BPF builder/evaluator | MERGED |

### 3.2 Open source-preservation PRs (NOT merged)

| PR | Branch | Head | CI state | Why open |
|---|---|---|---|---|
| [#197](https://github.com/u2giants/theoracle/pull/197) | codex/parent24-s13-sql-repair | 939cc280 | W10 fail (inherited) | GLM APPROVE; needs three-way merge; Linux pin checks before runner10 |
| [#200](https://github.com/u2giants/theoracle/pull/200) | parent24-s08-compose-81742134 | 450dd3e6 | W10 fail | S08 eight-source compose; needs Linux 256 pure + actual 21 SQL |
| [#201](https://github.com/u2giants/theoracle/pull/201) | codex/parent24-s11-compose-01a16013 | ac1a848e | W10 fail | S11 compose + registration; needs 45 SQL+Next/multiemployee |

Do not delete these branches. Do not apply their two-dot diffs onto later main (GLM medium finding on PR197).

### 3.3 The two recorded verification failures

**S07 Create-child (was 5370/1 fail on main).** Diagnostics source landed (PR196). Cause hypothesis: second `current_v1` inside `beforeWrite` during `exchange_provider_v1` gets 503 from the protected service (Python create-worker server `_fresh_supervision()` → supervisor `current()`). Exact private predicate still UNKNOWN. Fresh-proof plan landed (PR202). On S09 CI run 39846165685 the Create-child case **passed** (40.88s) — the failure is flaky, not deterministic. Still needs one fresh invented proof that captures the new diagnostics when it fails.

**S13 recovery SQL (was 25/27 fail).** Both ratified fixes applied on PR197: (1) receipts census joins `claim_id` to claims owner workspace; (2) `AS recovery_scope_item(value)` replaces naked `scope` alias at two sites. Full audit: 75 census queries + 18 DECLARE sites, zero additional defects. pglast imports guarded after DeepSeek REJECT. **GLM final-check APPROVE** with one shipping rule: **true three-way merge only** so main's post-bf788080 records are not deleted by a two-dot-diff apply. Before runner10: Linux pglast test + sha256 of 021/024/025 pins + 27 actual SQL bodies.

### 3.4 S09 W10 — now green at full population

Three defects were fixed on the S09 branch before merge:
1. documentary-09 JUnit abandon from `conversation_native_sql` placement (must stay on documentary-03).
2. Shared `timed_out` flag marking all 10 workers when only one exceeded 120s.
3. Protected-channel lease regex stricter than `canonicalInstantV1` (refused ms=000 deadlines) — root cause of the 25MiB viewer 503.

Result: W10 `success:true, tests:5472, skipped:0` on run 39855010833. This is the first complete-population green W10 on this compose. Business acceptance remains false.

### 3.5 What is NOT done

- S07 permanent repair (needs fresh invented proof with new diagnostics).
- S13 runner10 / actual 27-case proof (needs Linux pin checks + root release).
- S08 actual 21 SQL + browser→receipt journey (PR200 open).
- S11 actual 45 SQL+Next/multiemployee (PR201 open).
- S12 actual nine-case Next/AuthSDK proof (brief is on main; proof never executed).
- Tool1988 / documentation-check capability recovery (parked candidate 2634).
- Global writer-cut implementation (design only is on main).
- S14–S16 actual comparison/adoption/retirement (business hold).
- All remaining S03–S16 product/semantic/host qualifications from the closeout ledger.

## 4. Everything we tried that did NOT work

1. **Installed `ai-doc-safety` and candidate 2634 both stall/killed** on this repo (known quadratic tailnet scan). Markdown-link check alone passes. Used targeted markdown-link check + diff-only boundary scan for prose PRs. Documentation-check capability remains unrecovered (tool1988).
2. **DeepSeek final-check appeared stuck** at `door-call` with dead PID; logged a reviewer issue. It later completed with REJECT. Lesson: detached reviews can look dead and still finish; wait for `result.json` before declaring failure. The logged issue 20261022T185526Z-edge-dev-deepseek-2167030 is a false alarm on the "stuck" claim — the REJECT itself was real.
3. **First S09 repack recreated the doc09 timeout** by moving `conversation_native_sql` onto documentary-09. Main deliberately keeps it on documentary-03 (PR191: doc09 exhausted at 794/795). Fix: restore to doc03.
4. **`run_test_groups` shared `timed_out` flag** marked all 10 workers when one was slow — made a fully green 5472-case run look failed. Fixed with per-worker timeout tracking.
5. **Lease regex `/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/`** refused `canonicalInstantV1` form when ms=000. Flaky 503 on 25MiB viewer. Fixed to match the canonical instant validator.
6. **`ai-review` / `ai-pr-wait` PowerShell kills** (`ChildProcess.kill`) after launching — output still lands in the log/result files. Do not assume the launch failed.
7. **`ai-pr-wait` refused under `code` class** because the change set included `.github/workflows/**` (deployment escalation). Redeclare `deployment` for those PRs.
8. **GLM review status `BLOCKED` while the report ends `APPROVE`.** The run-level BLOCKED was sandbox retention noise; the verdict in the report file is APPROVE. Read the report file, not just the outcome status.
9. **Windows host cannot honestly run several Oracle suites**: `os.getuid`, `os.O_PATH`, `os.mkfifo`, POSIX `Path('/…').is_absolute()`, `hnswlib`/MSVC. Linux CI is the source of truth.

## 5. Root causes and key findings

- W10 `tests:` only sums JUnit from workers that wrote XML. A timed-out worker silently drops its whole group from the count — a "missing population" can be one missing JUnit, not a registration cut.
- `conversation_native_sql` must stay on documentary-03; documentary-09 is the known timeout pool.
- Shared 120s deadline is per-run wall clock across parallel workers; per-worker pytest 110–117s leaves almost no margin. Future suite additions need rebalance.
- Lease/datetime regexes must match `canonicalInstantV1` (omit zero fractions). A stricter channel-only regex is a flake at ms=000 and a production risk.
- `refusalStage` is stale on lease/body/abort refusals — `wire-boundary` in logs does not prove the wire-size predicate.
- Classic `sock_filter` is `u16 code, u8 jt, u8 jf, u32 k` (8 bytes); far jumps need 32-bit `JA` pairs or inline `RET`.
- `ai-task-gates` escalates to `shared-db` if SQL prerequisites land in a change set, and to `deployment` for workflow files. Keep DTO/BPF PRs free of SQL.
- OAuth token on edge-dev has `repo` but not `workflow` scope; pushes touching `.github/workflows/**` need SSH (`git@github.com:u2giants/theoracle.git`).
- Three-way merge rule for PR197: a two-dot diff against later main would delete S07 diagnostics, S12-04 brief, and S14 writer-cut records.

## 6. Exact next steps

1. **S07 fresh invented proof.** Use the plan at [docs/verification/oracle2/s07-create-child-fresh-proof-plan.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/oracle2/s07-create-child-fresh-proof-plan.md). Independent exact SOURCE + ONE resource assessment → true database gate → root one-fresh release → run one instance → read new diagnostics → name the exact cause or record remaining UNKNOWN. Gate: exact cause found and permanently repaired; full W10 5370+ clean.
2. **S13 runner10 after Linux checks.** On PR197: Linux pglast test + `sha256sum` of 021/024/025 against `OPERATIONAL_OWNER_SOURCE_PINS_V1` + 27 actual SQL bodies. Then independent resource assessment + root release + fresh runner10 (never replay 09 identities). Ship as **true three-way merge**. Gate: all 27 PASS, 0 E/S, owned resources absent.
3. **Land PR200 (S08).** Linux 256 pure + actual 21 SQL + browser→current-turn→sender→fixture receipt. Keep real Teams producer UNQUALIFIED. Gate: full current composition review + journey proof.
4. **Land PR201 (S11).** Actual 45 SQL+Next/multiemployee; measure one-admin setup savings; solve shared Next dist lock legitimately. Gate: full integrated W10/post-main clean; no invented business saving claimed.
5. **S12 actual nine-case proof.** Brief is on main. Independent SOURCE + ONE resource review of runner 04 packet → root release → execute. Gate: 9 cases 0 F/E/S/120 with source-before/after and owned-resource absence.
6. **Tool1988 / doc-safety recovery.** Inspect preserved candidate 2634; legitimate merge + lifecycle APPROVE + install through supported updater. Gate: original full Oracle checker completes.
7. **Writer-cut implementation.** Design is on main under `docs/verification/oracle2/s14-writer-cut/`. Implement stages 1–9 and the 20-case race matrix. Business comparison/cutover stays held.
8. **Continue remaining S/U/W** from the closeout ledger. Do not stop at the repairs.

## 7. Constraints and gotchas in force

- Canonical checkout is landing-only. Every write task gets its own current-upstream worktree. Branch + PR, never push to protected main. Commit identity: `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve all safety gates and the separate business-acceptance hold. No company originals, production, paid providers, real meetings, or POP shared-db writes from Oracle work.
- W10 SAME shared 120 seconds / ten workers / per-request ≤30 / full mandatory population / 0 F/E/S/timeout/launch/cleanup. No case cuts or budget raises.
- Interviews retain SQL019 max 8 TOTAL questions per conversation and 10-minute segment.
- Do not suppress strict framing/currentness, refresh original windows, or resend uncertain claims. UNKNOWN never equals drained or done.
- Never apply a two-dot old-head diff that would delete current-main files. True-ancestor additive composition only.
- Never retry a reviewer that failed or was reported skipped this session. Muse is forbidden for this program after the 2026-10-22 incident.
- Do not delete other sessions' worktrees or handoff files. Successor rule applies only with all three conditions proved.
- Observation week rules apply for reviews (`--detach`, `ai-review outcome`).

## 8. Access, tools, environment

- Machine edge-dev (Windows), authenticated personal GitHub `u2giants/theoracle`. Use `ai-gh` / `gh` for GitHub. Never confuse personal Oracle with POP DesignFlow.
- Vault `vibe_coding` references through approved secrets tools only. No new real credential was obtained, rotated, or stored this session.
- Qualified test tools: Node 24 toolcache, Python venv with psycopg/pglast/pytest on Linux CI. Windows host cannot run `os.getuid`/`O_PATH`/`mkfifo`/hnswlib suites honestly.
- Shared-db closeout check `ai-shared-db-closeout-check --session-id ses_ffe5e9b3fe2e6ffeolqy4r1hyC` returned `ok:true`, zero owned claims/stages (2026-10-23).
- Detached review IDs this session: `d20261022T184557-2154134-21749` (DeepSeek REJECT→fixed), `d20261022T191054-2185466-8337` (GLM APPROVE).

## 9. Open questions and risks

- S07 Create-child is flaky (passed on one full run). A single green rerun is not a repair; the exact cause must still be named from diagnostics.
- PR197/200/201 W10 failures are inherited or need Linux proof; do not treat a failed W10 on those branches as a new regression without reading the count and worker JUnit.
- Worker bin-packing is near capacity (~1099s documentary pytest across 9 workers). Any new suite needs a corresponding rebalance.
- Tool1988 doc-safety is still uninstalled; prose merges used targeted checks only.
- GLM's medium finding (two-dot diff would delete open-workstream records) is a shipping-method hazard, not an authored defect. Verify post-merge that the five docs and fixture diagnostics survive any integration of PR197.

### Part (b): one factual subagent block each

**Agent S07 Create-child diagnostics.** Asked to diagnose and add fixture-only diagnostic metadata. Did: branch `codex/parent24-s07-create-diag` f6e783e7, PR196, merged. Found: failure at second `current_v1` in `beforeWrite`; protected service 503; exact predicate UNKNOWN. Did NOT: run fresh proof or permanent fix.

**Agent S13 SQL repair.** Asked to compose 2633 and apply ratified fixes + 56-query audit. Did: branch `codex/parent24-s13-sql-repair` 1738f945→ce06f249→939cc280, PR197 open. Found: two ratified defects were the only ones; receipts table has no workspace_id. Did NOT: execute runner10 or actual DB proof.

**Agent S09 question compose.** Asked to compose 11221 + TLS diagnostics. Did: branch `codex/parent24-s09-compose`, PR198 eventually merged after three follow-up fixes. Found: additively composable; doc06 tightest fit. Did NOT: reopen PR192 or claim W10 acceptance at compose time.

**Agent Writer-cut inventory.** Asked for writer inventory + source-owner design. Did: branch `s14-writer-cut-source-owner-design` 3b43c35c, PR199 merged. Found: 55 confirmed writer files, 28 candidates, 5 external classes; 662 lexical sites are not a writer count. Did NOT: implement the cut or open POP claims.

**Agent S11 compose.** Asked to compose ac539 + register TS suites. Did: branch `codex/parent24-s11-compose-01a16013` ac1a848e, PR201 open. Found: Windows host limits; purpose_worker_startup pairing constraint. Did NOT: claim 45 SQL+Next proof or realized savings.

**Agent S08 compose.** Asked to compose 81742134 eight files. Did: branch `parent24-s08-compose-81742134` 450dd3e6, PR200 open. Found: canonical 021 digest LF; `os.getuid` blocks 57 pure cases on Windows. Did NOT: run actual 21 SQL or browser journey.

**Agent Native V2 DTOs/BPF.** Asked for closed V2 DTOs + BPF builder/evaluator source only. Did: branch `codex/s13-child-v2-dto-bpf-01a16013` 315da613, PR203 merged. Found: sock_filter 8-byte layout; far-jump constraints. Did NOT: run any child/filter/prlimit effect.

**Agent S09 population gap (two waves).** Asked to diagnose 4690 vs 5370. Did: identified doc09 JUnit abandon, then conversation_native_sql misplacement, then shared timed_out flag. Found: W10 count only sums written JUnit. Did NOT: cut cases or raise budgets.

**Agent S09 failure diagnosis.** Asked to diagnose complete-population W10 success:false. Did: proved 5472/0 failures; fixed per-worker timeout tracking + rebalanced doc03. Found: shared timed_out was the only defect. Did NOT: change test bodies.

**Agent Original-viewer 503 fix.** Asked to fix 25MiB viewer 503. Did: fixed lease regex in `protected-service-channel.ts` to match `canonicalInstantV1`. Found: ms=000 flake. Did NOT: weaken guards.

## Mandatory self-audit

1. **Yes — a brand-new developer can continue:** §1–2 define application and mission; §3 binds main tip, merged PRs, open PRs, and both verification-failure states; §6 gives ordered next steps with gates; §4 records dead ends; §7–8 preserve constraints and custody.
2. **Yes — continued as well as I can:** §3.4 records the green 5472 W10 and the three S09 fixes; §5 captures lease regex, timeout accounting, and packing findings; part (b) separates every sub-agent including what they did NOT do.
3. **Yes — every relevant operational dimension is covered:** goals §2; delivery §3; failures §4; findings §5; next steps §6; constraints §7; access §8; risks §9. Full S01–S16/W/U criteria remain in the closeout handoff and plan STATUS, not restated here.
4. **Yes — owner-only decision audit:** §0 contains only the continuing business hold and the settled longevity ruling. Every other "approval" mention is technical (AI reviewer / root release), not an Albert question. No outside business judgment found.

Posted by MiMo chat on edge-dev.
