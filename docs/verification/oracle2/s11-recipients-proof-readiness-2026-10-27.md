# S11 Recommendation-Recipients Proof Readiness Plan (2026-10-27)

Composed source head: `c913526e` on branch `codex/parent24-s11-recipients-compose`.
Machine: edge-dev (Windows authoring) / edge-dev3 (Linux proofs).
Task class: `code`. No production, company originals, paid providers, real meetings.

## 1. Current 45 SQL+Next/multiemployee proof plan

### Scope

Two separate one-shot invocations on edge-dev3, same owner (Albert Hazan), no new grants:

| Invocation | Test suite | What it proves |
|---|---|---|
| A | `test_workspace_next_recipients_sql_v1.py` | Two invented employees (multiemployee), indexed recipient origin restriction, workspace Next/SQL integration |
| B | `test_recommendation_next_auth_browser_v1.py` | Actual Next process + Auth + employee SQL, recommendation-actions endpoint, browser journey |

### Budget

- `ONE_SHOT_WALL_S = 300` per invocation (test-setup-only; NOT the W10 120s budget).
- Do not claim W10 SAME fit from these invocations.
- Per-request ≤30s inside each invocation (existing limits unchanged).

### Fixtures

- Invented fixtures only: one fresh PG + FalkorDB graph stores + TLS fixtures + openssl + pnpm/tsx + Chromium.
- `localhost.localdomain` DNS resolution.
- Owned cleanup (compose-project absence proof + name/port post-run leak scan).
- No production/company effect.

### Runner

`scripts/oracle2/run-s11-next-multiemployee-proof-01.py` (sealed at PR201 head, carried forward).

Fail-closed gates:
- exact-head pin (`receipt.head == git rev-parse HEAD`)
- clean-tree check (`git status --porcelain` empty)
- receipt fields (`head`, `verdict=APPROVE`, `reviewer`, `reviewed_at`)
- STOP exit 2 on every pre/post-gate failure
- owned cleanup (compose-project absence + name/port leak scan)
- source-before/after equality (sha256 over all git-tracked files)
- JUnit totals (tests>0, failures==0, errors==0, skipped==0)
- timeout handler (`start_new_session=True` + `os.killpg`)
- resource preflight (DNS/::1, Chromium, pnpm/tsx, openssl, docker, git, ps, venv)
- stale-lock path-scoped live process holder check
- FalkorDB provisioning (`falkor-candidate`)
- label `event` (legal for `worker_postgres` allowlist)

### Execution sequence

1. Independent exact SOURCE + ONE resource-plan assessment via `ai-review --detach` / `ai-review outcome`.
2. True database gate (edge-dev3, owned synthetic namespace).
3. ONE fresh run (invocation A, then invocation B sequentially).

### Reader warnings (sibling streams this session)

- Muse, StepFun, GLM have all failed/refused publication this session (logged). NEVER retry those.
- Let the allocator pick an eligible different engine (DeepSeek is owner-named working).
- Keep review packets FOCUSED (18-file dumps timed out a provider, exit 124).
- ZERO writes to the worktree during review (source-identity-changed kills publication).
- `git config core.autocrlf false` in the worktree before review dispatch.
- Windows `git checkout <commit> -- <file>` corrupts binary-exact files — use `git show <commit>:<path> > <path>` via Git Bash.
- A review seal is head-exact: ANY source fix after a review requires a fresh review on the FINAL head.

## 2. One-admin setup-savings MEASUREMENT method

### What is measured

The static reduction from sequential install×4 + repin (5 admin contexts, 5 pins calls) to one-admin batch (1 admin context, 1 pins call) for 4 admissions + 4 authorities.

### Current state

| Path | admin contexts | pins calls | admissions | authorities | offline wall median |
|---|---|---|---|---|---|
| sequential install×4 + repin | 5 | 5 | 4 | 4 | 0.000120s |
| one-admin batch | 1 | 1 | 4 | 4 | 0.000107s |
| delta | **4** | **4** | 0 | 0 | 1.3e-05s |

### Measurement method (NOT yet executed on live DB)

1. Run `scripts/oracle2/measure-s11-setup-batch-01.py` on edge-dev3 against the owned synthetic namespace.
2. Record wall-time for both paths (sequential vs one-admin batch) with the same source/deps.
3. Compare medians across ≥5 repetitions.
4. Report the measured delta.

### Critical constraint

**Do NOT report a saving as realized until measured.** The static reduction (5→1 admin contexts) is real in code. The live-DB install wall-time saving remains unmeasured and is NOT a claimed benefit. No invented business saving metric is accepted as a realized benefit.

## 3. Shared Next dist-lock approach

### Problem

Three actual-Next test drivers spawn `next dev --turbopack` with `cwd: resolve('.')` (apps/web) and share one generated Next development output directory (`apps/web/.next/dev`):

1. `apps/web/tests/oracle2/recommendation-next-auth-proof.ts`
2. `apps/web/tests/oracle2/workspace-next-recipients-proof.ts`
3. `apps/web/tests/oracle2/model-review-next-auth-proof.ts`

Parallel mandatory S05/S11/S12 actual-Next drivers contend on the same `apps/web/.next/dev` development lock.

### Legitimate fix surface (no guard weakening)

Next officially supports a string `distDir` in `next.config.ts`. Legitimate isolation directions:

1. **Per-proof owned `distDir` under the test scratch** — test-only config seam consumed by the existing official `distDir` option. Each driver writes to its own `distDir` under the test scratch directory.
2. **Same-owner sequential integration** of the three drivers — run them sequentially within one worker, avoiding parallel contention.

### Explicitly rejected

- Blanket serialization beyond the shared 120s W10 budget.
- Fake mocks, skips, or larger W10 budgets.
- Timeouts raised, cases cut, or assertion weakening.
- Rebalancing that changes whole cases/modules (only unchanged whole cases/modules or permanent production/setup efficiency may be rebalanced).

### Current status

- **UNPROVED under W10.** Dist-lock under full W10 parallel remains a named remaining gate.
- Contention observation set includes `test_consolidation_next_auth_browser_v1.py` (third auth-browser driver) and `model-review-next-auth-proof.ts` (third spawn site).
- No source/config edit to Next config or the three drivers has been made.
- Guards unchanged.

### Implementation plan (when authorized)

1. Add `distDir` support to the three drivers' spawn sites (read from env var, default to `.next`).
2. Set unique `distDir` per proof invocation in the test scratch.
3. Run the contention observation set under W10 parallel to validate.
4. Record results; do not claim W10 fit until observed.

## 4. Remaining gates

1. Independent exact SOURCE + ONE resource-plan assessment (gate chain step 1).
2. True database gate on edge-dev3 (gate chain step 2).
3. ONE fresh run of invocations A+B (gate chain step 3).
4. Live-DB one-admin setup wall-time measurement.
5. Shared Next dist-lock legitimate isolation (documented, not implemented).
6. Full integrated W10 (120s / ten workers / per-request ≤30 / full population / 0 F/E/S/timeout/launch/cleanup) and whole-product post-main clean.

## 5. Root-ratified security behaviors (preserved verbatim in composition)

1. **valid_until restricts SAME original request-fence monotonic end** — `apps/web/proxy.ts:108,113` caps window to `originRestriction.validUntil`.
2. **One local ExitStack retains restrictive lease through both private bodies/every list item/final encode** — `services/oracle-brain/oracle_brain/hosting/recommendation_actions_v1.py:134` (`with ExitStack() as leases`), lease entered at `_lease` (line 63), retained through `_read` (76-95), `_list` (117-128), `_execute_v1` (136).
3. **Artifact storage consults current fence before each open/read and after read** — `recommendation_actions_v1.py:94` (`_runtime_recheck=self.settings.current`).
4. **Common SQL connector rejects absent/empty password before connect** — `protected_sql_connection_v1.py:34` (`not all(params.get(k) for k in ('host','port','dbname','user','password',...))`).
5. **Late write uncertainty stays UNKNOWN/no resend** — `recommendation_authority_v1.py` (`RecommendationOutcomeUnknown`: "Possible write/commit completed; read-only reconciliation, never resend").
