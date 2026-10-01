---
issue: 27
status: OPEN
owner: next Oracle coordinator session (S03 real-data preview / #58)
---

# S03 code merged, worker watch recorded, hygiene done — coordination wrap-up

## 0. Decisions only the owner can make

**None blocking right now.** Put this whole list to the owner in ONE message only if an item becomes live.

Already settled — do NOT re-ask (2026-09-28 EDT, Albert's chat):
- All data can be shared with all AI providers.
- Use Ilona for the whole licensing workflow (S03 real-data process owner; also on #27).
- Instead of MiMo use StepFun; put z.ai on hold; use the others.
- Let GitHub start test jobs on edge-dev3 automatically.
- Never ask a human to approve; AI reviewers gate technical actions; never hand Albert commands.

Future owner items (not yet live; recommendations included):
1. **Real-data preview scope** — when #58 runs, confirm Ilona's licensing document set and answer keys are the authorized source. Recommend: use the existing private Oracle storage under verified admin access; no new account. Blocks S03 acceptance.
2. **Cheaper primary/fallback models** — Albert said the S02 pair (`claude-sonnet-5` / `gpt-5.5-2026-04-23`) is "way too expensive." Recommend: re-run `scripts/oracle2/evaluate_models.py` and propose a cheaper pair on #24 before S04 scales calls. Blocks cost, not S03 code.
3. **R2 reason-code continuation** — one owner decision remains in `HANDOFF.d/2026-08-27T1600Z-al8960ofc-claude-r2-reason-feedback-regressed.md` (whether to continue after regression; plus re-save of an API-key prefix on a 1Password item). Recommend: leave parked until the Oracle overhaul reaches S05+. Blocks nothing in S03–S04.

## 1. What this application is

Oracle (`u2giants/theoracle`) is POP Creations / Spruce Line's evidence-backed knowledge and consulting app. Employees chat with it and upload documents; workers extract claims with evidence; validators gate promotion; Brain synthesis keeps traceable sections. The **Oracle consultant overhaul** (parent [#24](https://github.com/u2giants/theoracle/issues/24), plan `plan_oracle_consultant_overhaul.md`) is replacing/expanding this into a company consultant: cited connected knowledge, authorized corrections, interviews, invited meetings, industry research, measurable recommendations.

Where it runs: web on Vercel (`oracle.designflow.app`, project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`, team `popcre`); workers on Trigger.dev (`proj_wgpzsvhmsopqhvwqaycn`); data on Oracle's own Supabase project `eqccjfbyrywsqkxxpjvg` (NOT `popcre/shared-db`).

## 2. What this session set out to do

Albert asked (2026-10-01) to (1) pull latest and report overhaul status, (2) dispatch three sub-agents in parallel: implement S03 (#27), finish the worker-release watch (#50), clean handoffs/checkout, (3) then `/wrap-up`. This session is a **coordinator**: it dispatched sub-agents and decided the S03 merge. See part (b).

## 3. Current verified state (2026-10-01 ~11:45 AM EDT)

- `origin/main` = `1cdca59` — PR [#57](https://github.com/u2giants/theoracle/pull/57) **MERGED** (squash, admin) 2026-09-29 7:19 PM EDT. S03 pilot journey is on main: Python `oracle_brain/{workflows/pilot,ingest/document,retrieval/pilot,consultant/pilot,knowledge/admission,knowledge/authority}.py`, `sql/002_pilot.sql`, web `apps/web/app/consultant/**`, `lib/oracle2-client.ts`, `components/consultant/pilot-workspace.tsx`, Playwright `tests/oracle2/pilot.spec.ts`.
- Offline gate green in CI run `36644212614`: `verify_phase.py S03 --mode offline` **11/11** (provider policy, pilot journey, authority adversarial, review concurrency). Build @oracle/web, verify, Vercel preview all green.
- **Not proved:** real-data preview journey with Ilona (licensing). Playwright pilot test is written but needs a running Next.js server (not in offline CI). Leftover-proof issue [#58](https://github.com/u2giants/theoracle/issues/58). Keep #27 open until #58 is done. Do not name S04 (#28) as next until then.
- Plan `plan_oracle_consultant_overhaul.md` STATUS updated: S03 row = merged `1cdca59` / offline green / real-data unproved; "next session" line points at #58, not S04.
- Worker watch (#50): `20260929.1` (deployment `o8x48rxv`, SDK 4.5.15, 25 tasks) **healthy** on all morning checkpoints 2026-09-29. Catalog refresh `run_06geo153l25kmot8hmp7lmdg01` 3:15 AM: ok, written 234, benign `ZAI_API_KEY not set`. One failed run `run_06getmvkes6smb9hn22rlap201` is §2 baseline-class `job_runs` insert, not a §3 stack regression. Evidence comment: https://github.com/u2giants/theoracle/issues/50#issuecomment-5900511066. **#50 stays open** per dispatch rev 7 close criteria (natural document-ingestion, 2026-10-05 checks, release row). Sub-handoff `2026-09-28T1943Z-edge-dev3-claude-worker-release.md` not retired (successor rule unmet).
- Hygiene: no HANDOFF.d file cleared the successor rule (condition 1 fails on all — none say committed-and-pushed on their status line). Deleted 7 merged remote branches (`codex/connected-business-answers-20260920`, `codex/issue-335-phase3-task-gates-01a086`, `codex/oracle-consultant-overhaul`, `codex/oracle-s02-foundation`, `codex/r2-contract-v2`, `codex/r2-first-divergence`, `codex/r2-support-contract`). Retained dirty `oracle-worktrees/r2-bounded-correction` and unproven `origin/claude/worker-release-dispatch`, `origin/codex/jev-integration-plan`.
- Post-release note: Albert selected `meta_muse/muse-spark-1.3-contributor` in `model_pool_vision` (allowed; no zai/glm-).

## 4. Everything we tried that did NOT work

- **First spawn of all three sub-agents stalled** (status `idle`/`stopped`, no deliverable: no S03 code, #50 still open, handoffs unchanged). Parent resumed each with "finish or return verbatim blocker evidence." All three then completed. Lesson: always verify sub-agent output on disk/GitHub, never trust `success` alone.
- `ai-task-gates check --before shipment|merge|pr` → `unknown action`. Only `start --class <class>` works reliably. Classes: `code` for implementation, `prose` for docs/handoffs (found in `ai-devops-reviewer-install/config/task-gates.json`), `deployment` for deploys.
- Local Windows Postgres via scoop is unreliable (autovacuum `0xC0000142` crash). Full `verify_phase.py S03 --mode offline` needs the CI runner with Docker Compose stores — do not try to reproduce the gate on this machine.
- `npx trigger.dev@4.5.15 mcp --readonly` is the reliable Trigger read path; raw REST `/deployments` rejects unscoped params.
- `op read 'op://…/Trigger.dev Personal Access Token (management)/…'` fails: parentheses are invalid in secret references; use the item id instead.
- When adding npm deps, `pnpm-lock.yaml` must be updated or CI `--frozen-lockfile` fails immediately.

## 5. Root causes and key findings

- S02 authority model (`appointments` + `has_authority`) already supports all five S03 adversarial authority cases with minimal extension (`test_authority.py`).
- `test_provider_policy.py` already covered S03 provider-policy gate cases (unapproved fallback, changed terms, telemetry leak, no outbound on deny).
- A CI-caught `NotNullViolation` in `create_draft` was fixed post-push (`status='draft'`); faster than local pre-verify when local stores are unavailable.
- Handoff pile (11–12 files) is **not** a count problem (owner ruling 2026-08-13). Stale = issue already closed. Successor-rule condition 1 ("status line says committed and pushed") is why nothing could be deleted — owners must mark status when they ship.
- Squash-merged PR branches are deletable when `headRefOid` equals the branch tip and the PR is MERGED; branches without an exact PR head match must stay.

## 6. Exact next steps

1. **S03 real-data preview (owner of #58 / #27).** Create a current-upstream worktree. Independent-reviewer APPROVE is required before any preview infrastructure. Ilona reviews one licensing journey using the S01 rubric. Record sanitized results in `docs/verification/oracle2/S03-pilot.md`. Gate: process owner accepts the cited answer; then update plan S03 row to ✅, close #27 and #58, delete this session's predecessor S03 baton `2026-09-29T2306Z-edge-dev-mimocode-s03-pilot-journey.md` under the successor rule, and only then name S04 (#28) next on #24.
2. **#50 release row (on 2026-10-05).** Record the dated checks per `docs/operations/2026-09-28-worker-release-dispatch.md` rev 7 step 7 and close #50 if healthy. Gate: #50 closed with the release row comment.
3. **Cheaper model pair** (after S03 or in parallel as a non-blocking child under #24). Run `scripts/oracle2/evaluate_models.py` and record the chosen primary/fallback on #24. Gate: Albert acknowledges the cheaper pair.
4. **Handoff retirement** (when a successor ships the next step of a workstream). Each baton's owner must set `status` to committed-and-pushed before a successor can delete it. Do not batch-delete. Keep the legacy archive `2026-08-06T1510Z-t16-codex-legacy-migrated-handoff.md` until the GAP/REL register is moved into a plan with STATUS.

You'll know step 1 worked when `docs/verification/oracle2/S03-pilot.md` exists with Ilona's review outcome and plan S03 is ✅. You'll know step 2 worked when #50 is closed.

## 7. Constraints and gotchas in force

- One ordered child at a time under #24. Worktrees only; branch + PR; never push protected `main`. Docs-only PRs may be `gh pr merge --squash --admin` immediately. Code PRs need green checks (use `bin/ai-pr-wait` when waiting).
- Oracle 2 stays synthetic-only until S03's approved real-data scope. No production writes without assigned AI reviewer APPROVE on exact inputs. Never `trigger.dev deploy --env prod` from a session whose classifier blocks it — a principal with permission must run it (Albert did `20260929.1`).
- Rollback is revert + forward deploy, never promote-older.
- Secrets: vault `vibe_coding` only; values never in chat/commits. Reviewer wrappers do not call 1Password during review.
- Sign GitHub bodies: `Posted by MiMo chat <id> on <machine>`.
- Shared-database gate for wrap-up: this session did **not** touch `popcre/shared-db` or the shared Supabase; sub-agents were Oracle implementation/watch/hygiene, not database agents. No orchestrator-marker was held.
- Handoff rules: one write-once file per session; never rewrite root `HANDOFF.md`; never edit another session's file; no file-count cap.

## 8. Access and environment

- Machine: `edge-dev` (Windows). Canonical checkout `C:\repos\oracle` on `main`.
- `gh` authenticated as `u2giants` (repo `u2giants/theoracle`). Vercel CLI as `u2giants` team `popcre`. Trigger MCP via `npx trigger.dev@4.5.15 mcp --readonly` (hello@popcre.com).
- Prod DB: 1Password item `qcuyabwseaptvuzvtjejffi2ou` field `oracle_session_pooler` (vault `vibe_coding`). Do not use `oracle.old`.
- Docker/Test stores: CI on `edge-dev3` (`~/actions-runner-theoracle`). Local Windows Postgres is not trustworthy for the offline gate.
- Leftover worktrees on this machine: `C:/repos/oracle-s03` (branch `feature/s03-pilot-journey`, clean, PR merged — safe to remove after local pull); `C:/repos/oracle-worktrees/r2-bounded-correction` (256 dirty deletions — NEVER force-remove; another workstream).

## 9. Open questions and risks

- Real-data quality gate (#58) is the only thing keeping S03 from accepted; without it no business-quality claim.
- Worker `20260929.1` carries two months of changes (R2 reader, retrieval); one §2 baseline-class failure already appeared — watch for more failure classes after Oct 5.
- StepFun rate limit 10 req/min; step-5-preview occasionally off-schema (retry once landed in #51).
- Z.ai key works only on the Coding Plan endpoint; general endpoint says "Insufficient balance" — keep z.ai on hold.
- Model cost objection is unresolved (owner item 2).
- Old open workstreams unrelated to this overhaul: #14 (Jev), #15 (connected answers) — their handoffs remain open with live-proof obligations; do not import them into the overhaul path.
- `.playwright-cli/` in the canonical checkout is pre-existing Playwright tool cache (logs dated 2026-09-23), untracked, not this session's work — left in place deliberately. Prefer `.gitignore` in a future housekeeping PR rather than deleting another tool's cache.

---

## Part (b) — sub-agent blocks (coordinator session)

### Sub-agent 1: `general-1` — Implement S03 pilot journey

- **Asked:** implement only S03 (#27) in a fresh worktree; offline gate; branch+PR; leftover-proof issue if real-data unproved; update plan STATUS; sign GitHub posts.
- **Actually did:** implemented the full pilot journey (Python + web + API + Playwright + SQL `002_pilot.sql` + `verify_phase.py S03` support). PR #57, commits `2eb2cb3`, `a1e0144`, `1b9dd13`, `870b434`, `6543776`. CI `36644212614` 11/11 offline tests green. Opened leftover-proof #58. Wrote baton `HANDOFF.d/2026-09-29T2306Z-edge-dev-mimocode-s03-pilot-journey.md`. Commented on #24 without naming S04 next.
- **Found:** local Windows Postgres crash `0xC0000142`; `ai-task-gates check` has no `pr`/`merge` action; lockfile must update with new npm deps; CI caught `create_draft` NotNullViolation (fixed).
- **Worktree:** `C:/repos/oracle-s03` on `feature/s03-pilot-journey` — clean; PR MERGED; safe to remove after pull. Do not delete until local main contains `1cdca59`.
- **Did NOT:** provision preview infra, run Playwright against a live server, claim business acceptance, tick #27, start S04.
- **Parent follow-through:** coordinator verified checks green and admin-merged PR #57 → `1cdca59`.

### Sub-agent 2: `general-2` — Worker-release watch (#50)

- **Asked:** read-only health check of Trigger prod `20260929.1`; comment + close #50 only if healthy per dispatch rev 7; no production mutations.
- **Actually did:** manual watch ~4:30 PM EDT Sep 29 (scheduled task `oracle-worker-release-watch` was absent on the host). Verified 25 tasks, 4-hour cycles ×5 Completed (12:01 AM–4:01 PM), catalog refresh written 234 with benign ZAI message, one §2 baseline-class failure. Posted evidence on #50 (comment `5900511066`). Left #50 **open** because dispatch §6 step 7 requires natural document-ingestion, 2026-10-05 checks, and the release row.
- **Found:** `npx trigger.dev@4.5.15 mcp --readonly` works; raw REST does not. Albert set `meta_muse/muse-spark-1.3-contributor` in `model_pool_vision` post-release.
- **Worktree:** none. **Files touched:** none.
- **Did NOT:** deploy, change env vars, roll back, or close #50.

### Sub-agent 3: `general-3` — Handoff and checkout hygiene

- **Asked:** successor-rule audit of HANDOFF.d; clean only merged clean worktrees/branches; keep the legacy archive; carry forward obligations if deleting.
- **Actually did:** audited all 11 handoffs — **none** qualify for deletion (condition 1 fails: no status line says committed-and-pushed). Deleted 7 remote branches whose PR head matched a MERGED PR. Retained dirty `r2-bounded-correction`, unproven `claude/worker-release-dispatch` and `codex/jev-integration-plan`, and unique-work dirs (`oracle-issue15-q2q3-live-proof`, etc.). No file changes (nothing retired).
- **Found:** a second worktree `C:/repos/oracle-s03` with untracked S03 work (later completed by sub-agent 1); `ai-task-gates` class for docs is `prose`.
- **Did NOT: delete the legacy archive; force-remove dirty worktrees; delete branches without exact PR-head merge proof.

## Self-audit (handoff-writer gate)

1. **Comprehensive for a brand-new developer?** Yes — §1 product/locations, §3 exact SHAs/PRs/run IDs, §4 dead ends, §6 ordered steps with gates, part (b) per sub-agent.
2. **As effective as this session?** Yes — sub-agent findings, gate CLI limits, Windows Postgres trap, worker-watch evidence, and owner items are all recorded.
3. **Every relevant detail?** Yes — goals, state, failures, decisions, constraints, risks, next actions, verification evidence, access; secrets by location only.
4. **Section 0 complete?** Yes — settled list plus three future owner items with recommendations and what each blocks; sweep of §1–§9 and part (b) found no additional owner asks (Ilona scope and model cost are listed; R2 item is listed; technical approvals are assigned to AI reviewers, not Albert).

Posted by MiMo chat $MIMO_SESSION_ID on edge-dev
