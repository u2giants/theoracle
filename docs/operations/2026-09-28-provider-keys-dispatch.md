# Provider API keys for production — exact dispatch for review (revision 2)

Owner request (Albert, Claude chat, 2026-09-28), verbatim: "add the keys" (after
PR #48 added Meta Muse, Z.ai GLM and StepFun adapters). Earlier in the same chat,
verbatim: "All data can be shared with all Ai providers." This is the owner's
data-sharing scope for these providers; the smoke checks below send only
synthetic text. Revision 1 was refused (qwen plan review); this revision drops
every deploy of new code.

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
  and `... stepfun` at `origin/main` (`5d5d262` + docs), keys injected by
  `op read` into the command's environment only. Stop if either fails.
- Stop on any non-2xx write, a missing 1Password item, or any sign the target
  is not the named project. No retries with changed inputs under this approval.

## Actions

1. Record current state: Vercel production deployment
   `dpl_H7UxqKGZJvAXC2AzAtWDnWaeetyo` (`theoracle-f4hpnknfa`, built from
   `5d5d262`, main at PR #48 merge); Trigger prod version `20260909.1`.
2. Vercel: for each key, pipe the `op read` value into
   `vercel env add <NAME> production --sensitive --scope popcre --project theoracle`
   (stdin; value never on disk, argv or output).
3. Vercel: `vercel redeploy dpl_H7UxqKGZJvAXC2AzAtWDnWaeetyo --target production`
   — rebuilds the **same commit** so the running site reads the keys. Verify the
   new deployment is Ready and its source commit equals the recorded one.
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

Vercel: `vercel rollback dpl_H7UxqKGZJvAXC2AzAtWDnWaeetyo` and
`vercel env rm <NAME> production`. Trigger: delete the two variables. Defaults
do not change (asserted by `verify:adapter-request-shapes`), so no user-visible
behavior changes until an administrator selects a new route.
