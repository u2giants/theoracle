# Provider API keys for production — exact dispatch for review (revision 2)

Owner request (Albert, Claude chat, 2026-09-28), verbatim: "add the keys" (after
PR #48 added Meta Muse, Z.ai GLM and StepFun adapters). Earlier in the same chat,
verbatim: "All data can be shared with all Ai providers." This is the owner's
data-sharing scope for these providers; the smoke checks below send only
synthetic text. Revisions 1 and 2 were refused (qwen plan reviews); revision 2 dropped every
deploy of new code, revision 3 fixes proof-of-value and stale-deployment gaps.

## Scope

- Keys: `META_MUSE_API_KEY` (1Password "Meta ai Muse Spark API Key") and
  `STEPFUN_API_KEY` (1Password "stepfun step5 ai api key", field `credential`).
- **Excluded:** `ZAI_API_KEY` — the stored Z.ai key returns 429 "Insufficient
  balance" on the general endpoint; it is added in a later dispatch after the
  owner tops up the account. `DEEPSEEK_API_KEY` already exists in both targets.
  No `*_BASE_URL` is set.
- Targets: Vercel project `popcre/theoracle` Production, and Trigger.dev
  `proj_wgpzsvhmsopqhvwqaycn` `prod`. Nothing else.

## Preconditions and stop rules

- `ai-task-gates check --before production` passes.
- Both 1Password values are live-proven first, from this machine, with
  `pnpm --filter @oracle/ai exec tsx src/__verify__/r-providers-smoke.ts meta_muse`
  and `... stepfun`, keys injected by `op read` into the command's environment
  only, run from the worktree `/home/ahazan/repos/oracle-add-providers`, which
  must contain **no** `.env.local` (the runner loads `.env.local` with
  `override: true`); the operator checks `test ! -e .env.local` first, so the
  tested values are exactly the 1Password values written to production. Stop if
  either fails.
- Vercel CLI pinned as `npx vercel@60.1.3`, authenticated as the owner's
  account; `vercel whoami` and `vercel project inspect theoracle --scope popcre`
  must show project id `prj_rP6Jlima7iK1paffEPhLqxlswGsC` before any write.
- Stop on any non-2xx write, a missing 1Password item, or any sign the target
  is not the named project. No retries with changed inputs under this approval.

## Actions

1. At execution time (not authoring time), resolve the **current** Vercel
   production deployment (`vercel ls theoracle --prod`, newest Ready) and its
   source commit; require that commit to equal `origin/main` HEAD at that moment,
   else stop and wait for main's auto-deploy to finish. Record that deployment
   id as `PROD_BEFORE`. Trigger prod version is `20260909.1`.
2. Vercel: for each key, pipe the `op read` value into
   `vercel env add <NAME> production --sensitive --scope popcre --project theoracle`
   (stdin; value never on disk, argv or output).
3. Vercel: immediately re-check that `PROD_BEFORE` is still the newest
   production deployment (stop if not), then `vercel redeploy PROD_BEFORE
   --target production` — rebuilds the **same commit** so the running site reads
   the keys. Verify the new deployment is Ready and its source commit equals
   `PROD_BEFORE`'s.
4. Trigger: for each key, `POST https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod`
   body `{"name": "<NAME>", "value": "<value>", "isSecret": true}`, with the PAT
   from 1Password "Trigger.dev Personal Access Token (management)"; PAT and value
   are held in shell variables from `op read`, never written to disk or printed.
   Expect 200. **No worker redeploy**: the deployed worker (`20260909.1`) predates
   the new adapters, so the keys take effect at the next normal worker release,
   which must go through its own reviewed deploy.
5. Verify env var **names** in both targets; record the new Vercel deployment id
   and this outcome on the parent issue.

## Rollback

Vercel: `vercel rollback PROD_BEFORE` (or dashboard Instant Rollback) and
`vercel env rm <NAME> production`. Trigger: delete the two variables. Defaults
do not change (asserted by `verify:adapter-request-shapes`), so no user-visible
behavior changes until an administrator selects a new route.
