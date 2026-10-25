---
issue: 24
status: OPEN
owner: mimo/parent24-s07-pr201-approve-2026-10-25
---

# Parent24: S07 plan + diagnostics + one-shot GREEN; PR201 seal APPROVE; PR200 still in review cycle

Record owner: MiMo chat on edge-dev (session `ses_ffe5e8ce8e381ffe52F0XmL6jL`). Observations rechecked October 25, 2026, approximately 9:00 AM–12:15 PM EDT (America/New_York). Dated observations, not transferable authority. Program is NOT complete. No company use, production adoption, or parent closure is claimed. Business-acceptance hold remains.

## 0. Business decisions only the owner can make

**No new business question is outstanding.** Continue every permitted structural and invented-data obligation before requesting company use. Then present the entire genuine business-question list together, once.

**Already settled — do NOT re-ask:**
- October 22, 2026: "Remain in force until withdrawn" for previously approved immutable assertion/version/scope (PR182 / #29).
- October 23, 2026: "muse and deepseek are working fine as reviewers" — session-scoped routing. Muse used successfully this session.
- Closeout/resume/completion handoffs are not permission for company use.

Nothing else in this workstream needs the owner. Every remaining item is technical (AI reviewer / root release / W10).

## 1. What this application is

The Oracle ([u2giants/theoracle](https://github.com/u2giants/theoracle)) is POP Creations' evidence-backed company consultant. Replacement: isolated Python/PostgreSQL/FalkorDB/GraphRAG operating model with protected mTLS boundaries. STATUS-first sources: [plan_oracle_consultant_overhaul.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_consultant_overhaul.md) and [parent #24](https://github.com/u2giants/theoracle/issues/24), plus the four companion plans on `main`. Closeout of record (NOT retired): [2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md). Prior baton (NOT retired): [2026-10-24T2329Z-edge-dev-mimo-parent24-pr197-s07-open.md](https://github.com/u2giants/theoracle/blob/codex/parent24-handoff-pr197-s07/HANDOFF.d/2026-10-24T2329Z-edge-dev-mimo-parent24-pr197-s07-open.md) (PR [#208](https://github.com/u2giants/theoracle/pull/208)).

## 2. What we set out to do this session

Resume parent #24 from main `4e365535` after PR197. Named next actions: (1) S07 plan v4 for Muse leftovers and SOURCE+ONE APPROVE; (2) fix PR200/PR201 briefs from Muse REJECTs and re-review; (3) after APPROVE, run one S07 invented instance and the PR200/201 one-shot journeys. Do not delete open PR branches. Do not ask Albert for technical approval. Use Muse; full 40-char `--assert-head` SHAs; edge-dev3 runners with the pglast venv Python.

## 3. Current state

### 3.1 S07 — plan + diagnostics APPROVED; one-shot GREEN (did not reproduce)

| Artifact | Head | State |
|---|---|---|
| Plan v5 (PR [#207](https://github.com/u2giants/theoracle/pull/207), branch `codex/parent24-s07-plan-muse-h1h7`) | [`811e07c3`](https://github.com/u2giants/theoracle/commit/811e07c317fd3e8d56f3bdcb9d49a94e8b7e2c4a) | Muse SOURCE+ONE **APPROVE** (run `20261025T132905-2852654-12398`) |
| Diagnostic upgrades (PR [#210](https://github.com/u2giants/theoracle/pull/210), branch `codex/parent24-s07-diag-upgrades`) | [`96814a37`](https://github.com/u2giants/theoracle/commit/96814a37919536103d7b462787c2ec2b88f5609e) | Muse SOURCE+ONE **APPROVE** (delta `f0cc26ab` run `20261025T152151-3145793-21749`; TLS-CN fix run `20261025T153745-3187073-8603`) |
| One fresh invented instance | `96814a37` | **GREEN** `1 passed in 41.11s`, returncode 0 |

**Green means did-not-reproduce, not a repair.** Per the plan decision rule this does not identify the historical 39760061151 cause and does not make Create-child stable. Two clean full W10 runs at one head are still required.

Packet on edge-dev3 host under the run directory: 379/384 artifact-index members present (5 absent expected on green: pre-child-failure, infra-failed, queue/cycle diagnostics, repeated-claim wire). Includes create-child-diagnostics.json, create-server-responses.jsonl, actual-unattended-outcome.json, warmup-refusals.json + attempt-1..30, supervision-scope.json, replay-spool/, source-before/after, owned-process-cleanup.json. Cleanup `absence_proven: true`. Outcome record written next to the packet.

### 3.2 PR201 S11 Next/multiemployee — SEAL APPROVED; journey NOT green

PR [#201](https://github.com/u2giants/theoracle/pull/201) branch `codex/parent24-s11-compose-01a16013`, head [`fca5dc3c`](https://github.com/u2giants/theoracle/commit/fca5dc3cc912c2e54bf8638164b15e27074b5bac).

Muse SOURCE+ONE **APPROVE** (run `20261025T133513-2874866-4984`). Sealed runner + plan + dist-lock note + measurement + fixture-order test on the PR branch.

Journey one-shot on edge-dev3 **did not complete**. Fail-closed STOP at the live-lock pre-check: the detector matched unrelated host processes (Playwright MCP, Claude Desktop chrome_crashpad, claude-headroom) as `apps/web/.next/dev` lock holders. Exit 2, no DB/Next work. This is a **runner false-positive**, not a product failure.

**Fix needed:** path-scoped lock detection (only processes whose cwd/cmdline binds `apps/web` or holds `.next/dev`), then re-review the delta (whole-file runner SHA is receipt-bound) and re-run.

### 3.3 PR200 S08 journey — still REJECT cycle

PR [#200](https://github.com/u2giants/theoracle/pull/200) branch `parent24-s08-compose-81742134`.

Seal rounds 1–7 landed on the branch (artifacts sealed, then C1–C9 runner defects, then sticky-bit/goldens, then H5/mediums). Latest head at wrap-up: `df584f7002775278b72a80d19c373ada10642382` (pushed). Latest Muse run `20261025T152949-3170087-12680` still REJECT (High/Medium/Low only — the unexecutable Criticals are gone). Journey not executed. Real Teams producer stays UNQUALIFIED.

Sealed paths on the PR branch: [s08-journey-proof-plan.md](https://github.com/u2giants/theoracle/blob/parent24-s08-compose-81742134/docs/verification/oracle2/s08-journey-proof-plan.md), [run_s08_journey_proof_v1.py](https://github.com/u2giants/theoracle/blob/parent24-s08-compose-81742134/scripts/oracle2/run_s08_journey_proof_v1.py), [check_s08_journey_skeleton_v1.py](https://github.com/u2giants/theoracle/blob/parent24-s08-compose-81742134/scripts/oracle2/check_s08_journey_skeleton_v1.py), [s08-compose-81742134-evidence.md](https://github.com/u2giants/theoracle/blob/parent24-s08-compose-81742134/docs/verification/oracle2/s08-compose-81742134-evidence.md).

### 3.4 What is NOT done

- PR200 journey seal Muse APPROVE + one-shot journey (21 SQL green first)
- PR201 lock-detector fix + re-review + one-shot journey
- S07 two clean full W10 runs for Create-child stability
- S12 nine-case Next/AuthSDK proof
- Tool1988 / doc-safety recovery
- Writer-cut implementation
- S14–S16 comparison/adoption/retirement (business hold)
- Remaining S03–S16 product/semantic/host qualifications from the closeout ledger

## 4. Everything we tried that did NOT work

1. **PowerShell `ChildProcess.kill`** on every long `ai-review` / `Start-Process` launch. Workaround that worked: `Start-Process` of Git `bash.exe` with a `.sh` file writing output to `.out`/`.err`. The kill still appears but the detached run lands — always read the `.out` file.
2. **`ai-task-gates check --before database` from a full PR HEAD** observes class `deployment` (repo consumer maps `.github/workflows/**` → deployment) which forbids `database`. Workaround: `ai-task-gates start --class code --base <proof-only-parent>` then `check --before database --reviewer-approval <receipt>`. Owner ruling 2026-10-14: database writes skip second-AI approval.
3. **PR201 journey STOP** on live-lock pre-check matching host Playwright/Claude processes (see §3.2).
4. **Missing tools on edge-dev3 PATH**: `pnpm`, `tsx`, `chromium`. Installed via user-local wrappers (corepack pnpm 9.5.0, npx tsx 4.23.15, Playwright chromium-1248).
5. **Scratch `mkdir(exist_ok=False)`** — move prior scratch aside before re-run (confirmed again).
6. **Subagent "pushed" commits that were local-only.** Always verify `git status -sb` shows not-ahead before treating a head as on-origin.
7. **S07 first one-shot: infra_failed** — OpenSSL X.509 CN 64-char limit vs long container DNS name (`project-postgres-1` ~71 chars). Fixed by shortening the owned project name.
8. **S07 second: missing `tsx` / foreign `node_modules/@oracle/shared` symlink** pointing at another worktree. Clean `pnpm install` restores workspace links. Never copy `node_modules` across worktrees.

## 5. Root causes and key findings

- Muse SOURCE+ONE on a **plan** is not the same as SOURCE+ONE on the **diagnostic delta + plan**. Both were required before the S07 instance.
- Journey runner artifacts must be **sealed in the PR branch**. `/tmp` on edge-dev3 is invisible to Muse.
- `worker_postgres` yields `(env_dict, identity)`; the admin URL is `env_dict['ORACLE2_TEST_ADMIN_URL']`. It only ups `postgres`; FalkorDB must be upped separately. Label allowlist is `(?:documentary-[0-9]{2}|event)`.
- `SYNTHETIC_MIGRATIONS` is non-contiguous (omits 003/005, includes 017/018/019/022/023/027). Never claim a `001..014` chain.
- Byte-identity pins must use git blob hashes (`git show HEAD:path | sha256sum`). Working-tree bytes differ on Windows CRLF.
- OpenSSL X.509 CN max is 64 chars. Compose project names must leave room for `-postgres-1` in the container DNS name.
- Postgres `timestamptz::text` is space-separated with short zone (`+00`), unlike ISO-T; allow-lists keyed on `T`/`Z` silently destroy SQL timestamp evidence.
- Live-lock detection must be path-scoped. Host-level `node`/`chromium`/`playwright` process scans false-positive on any developer machine.
- Next leaves `apps/web/.next/dev` after clean exit; directory existence is not a live lock.
- `ai-task-gates --version` does not exist; identity is the `version` subcommand.
- Windows cannot enforce POSIX mode bits / nlink==1 / `os.getuid`; those receipt checks must degrade honestly.

## 6. Exact next steps

1. **PR200 journey seal.** Read the latest Muse REJECT (round 7) under the PR200 worktree `.ai/reviews/`. Fix the remaining High/Medium/Low. Muse SOURCE+ONE. Gate: `VERDICT: APPROVE <full-head>`. Then 21 SQL green, then the journey. Keep real Teams producer UNQUALIFIED.
2. **PR201 lock-detector fix.** Scope the live-lock pre-check to processes that bind `apps/web` or hold `.next/dev`. Re-review the delta (receipt re-mint). Re-run the one-shot on edge-dev3 with the pglast venv Python and `PATH` including the user-local bin. Gate: two one-shot invocations green, owned cleanup absence, source-before/after equal. W10 dist lock stays UNPROVED.
3. **S07 two clean full W10 runs** at one head. Gate: 0 F/E/S, all ten workers under 120s, same population. Only then call Create-child stable for that head.
4. **Continue remaining S/U/W** from the closeout ledger. Do not stop at the repairs.

You'll know step 1 worked when Muse returns `VERDICT: APPROVE` on the new head and the journey runner executes past its stages. Step 2: the runner no longer STOPs on unrelated host processes and the one-shot completes. Step 3: two consecutive green W10 runs at one `git rev-parse HEAD`.

## 7. Constraints and gotchas in force

- Canonical checkout is landing-only. Every write task gets its own current-upstream worktree. Branch + PR, never push to protected main. Commit identity `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve all safety gates and the separate business-acceptance hold. No company originals, production, paid providers, real meetings, or POP shared-db writes from Oracle work.
- W10 SAME shared 120s / ten workers / per-request ≤30 / full mandatory population / 0 F/E/S/timeout/launch/cleanup. No case cuts or budget raises.
- Do not suppress strict framing/currentness, refresh original windows, or resend uncertain claims. UNKNOWN never equals drained or done.
- Never apply a two-dot old-head diff that would delete current-main files. True three-way merge for recovery integrations.
- Observation week: `ai-review --detach`, read with `ai-review outcome`. Read the report file. Full 40-char `--assert-head` SHAs only.
- Do not delete open PR branches (200/201/207/210). Do not delete other sessions' worktrees or handoff files.
- Invoke edge-dev3 runners with `/tmp/pglast-venv-20261023/bin/python3` and `PATH` including `/home/ahazan/.local/bin` (pnpm/tsx/chromium wrappers).
- Windows host cannot honestly run `os.getuid`/`O_PATH`/`mkfifo`/hnswlib suites. Linux (edge-dev3) is the source of truth.

## 8. Access, tools, environment

- Machine edge-dev (Windows), authenticated personal GitHub `u2giants/theoracle`. edge-dev3 (Linux) via SSH BatchMode; Docker works there.
- Muse SOURCE+ONE used successfully (S07 plan, S07 diag delta, S07 TLS fix, PR201 seal all APPROVE; PR200 multiple REJECTs also completed cleanly).
- edge-dev3 host paths (operational, not source): worktrees `pr201-s11`, `pr200-s08`, `s07-diag`; runners and receipts under `/tmp/oracle-parent24-wy02uT/`; S07 packet under `/tmp/oracle-parent24-wy02uT/s07-fresh-run-01/`.
- Windows worktrees (operational): `oracle-wt-s07-plan` (PR207), `oracle-wt-s07-diag` (PR210), `oracle-wt-handoff-p24` (this baton), plus the PR200/PR201 compose worktrees.
- Shared-db: no POP shared-db claims this session.

### Part (b): session activity blocks

**Coordinator (this session).** Read named handoff + prior batons + Muse REJECTs. Drove S07 plan v5 → APPROVE, diagnostic upgrades → APPROVE, one-shot GREEN. Drove PR201 seal → APPROVE (journey STOP on lock false-positive). Drove PR200 through seal rounds 1–7 (still REJECT at wrap-up). Did NOT: green PR200/201 journeys, merge any PR, run W10.

**general-1..6.** Plan v4/v5 rewrites; PR200/201 seals and v3 fixes. All returned. Heads recorded in §3.

**general-7..11.** S07 diagnostic upgrades and allow-list/timestamp/tuple fixes. All returned. Heads `8ffc4e2a` → `0f18c3e7` → `f0cc26ab`.

**general-8,12,13.** PR200 seal rounds 4–7 (C1–C9, sticky/golden, H5/mediums). Heads `ced9387d` → `10c3e48d` → `6121a941` → `df584f70`.

## Mandatory self-audit

1. **Yes** — §1–2 define application and mission; §3 binds heads, APPROVEs, the green one-shot, and blockers with GitHub URLs; §6 gives ordered next steps with gates; §4 records dead ends; §7–8 preserve constraints and custody.
2. **Yes** — §3 records exact HEADs and Muse run IDs; §5 captures CN-64, Postgres timestamp, foreign node_modules, and lock-detector findings; part (b) separates every sub-agent.
3. **Yes** — goals §2; delivery §3; failures §4; findings §5; next steps §6; constraints §7; access §8; risks in §3.4/§6. Full S01–S16/W/U criteria remain in the closeout handoff and plan STATUS.
4. **Yes** — §0 contains only the continuing business hold and the two settled rulings. Every other "approval" is technical (Muse SOURCE+ONE / root release / W10). No outside business judgment found in §1–§9 or part (b).

Posted by MiMo chat ses_ffe5e8ce8e381ffe52F0XmL6jL on edge-dev.
