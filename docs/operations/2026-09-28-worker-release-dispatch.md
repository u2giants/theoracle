# Legacy worker production release — exact dispatch for review

Owner request (Albert, Claude chat, 2026-09-28), verbatim: "release the workers",
after being told the new AI providers reach background jobs only with the next
reviewed worker release.

## Target and artifact

- Trigger.dev `proj_wgpzsvhmsopqhvwqaycn`, environment `prod`.
- Currently deployed: version `20260909.1` from `28e8eb7` ("chore: add Phase 3
  task gates (#9)").
- Deploy exactly commit `a12e25e` (`origin/main` when this dispatch was
  written). The operator checks `git rev-parse HEAD` equals it in a clean
  worktree with no `.env.local`, and re-requests review if main moves in
  `apps/workers/**` or `packages/**`.

## What ships beyond 20260909.1 (worker bundle only)

- PR #48: Meta Muse / Z.ai / StepFun adapters and DeepSeek catalog routes;
  production default routes unchanged (asserted by
  `verify:adapter-request-shapes`). New providers register only when their key
  exists; Z.ai is on hold (no key in Trigger).
- PRs #12, #16, #17: responsibility-reader support-contract audit and
  cross-domain evidence reconciliation in `packages/ai` retrieval/prompts —
  already live on the Vercel chat app since those merges; this aligns workers.
- PR #45 (S02): `apps/workers/trigger.config.ts` excludes `oracle2-run.ts` and
  `oracle2-project.ts`, so no Oracle 2 task deploys here; `@trigger.dev/python`
  and `@oracle/brain-contracts` are added as dependencies, but the legacy config
  uses no Python extension. The Oracle 2 configs are not used by this deploy.
- Test/verify scripts under `apps/workers/src/__verify__` (not tasks).

## Preconditions and stop rules

- `ai-task-gates check --before deploy` passes; CI on `a12e25e` passed.
- `pnpm --filter @oracle/workers typecheck` and
  `pnpm --filter @oracle/ai run verify:adapter-request-shapes` pass locally.
- Stop on build failure, on any indexed task id not in 20260909.1's task list,
  or on any `oracle2-*` task appearing. No retry with changed code.

## Actions

1. Record 20260909.1's task list.
2. From `apps/workers`, with `TRIGGER_ACCESS_TOKEN` from 1Password "Trigger.dev
   Personal Access Token (management)" held in the command environment only:
   `pnpm run deploy` (= `npx trigger.dev@4.5.15 deploy`, config
   `trigger.config.ts`, project `proj_wgpzsvhmsopqhvwqaycn`, env prod).
3. Verify the new version is current and its task list equals step 1's.
4. Watch prod runs for 30 minutes; any new failure class versus the prior 24 h
   triggers rollback.
5. Record version and outcome on the parent issue.

## Rollback

`npx trigger.dev@4.5.15 promote 20260909.1` (or dashboard "Promote" on
20260909.1). Env vars are untouched by this release.
