# Provider API keys for Trigger production — exact dispatch for review

Owner request (Albert, Claude chat, 2026-09-28): "add the keys" (after PR #48
added Meta Muse, Z.ai GLM and StepFun adapters and DeepSeek routes). Owner
statement in the same chat: "All data can be shared with all Ai providers."

## Target

Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn` (legacy Oracle workers),
environment `prod` only. Vercel is out of scope (no Vercel API token exists).

## Actions

1. Upsert, via `POST https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod`
   with the PAT from 1Password "Trigger.dev Personal Access Token (management)"
   (read by `op` into a mode-600 scratch file, deleted after; never printed):
   - `META_MUSE_API_KEY` ← 1Password "Meta ai Muse Spark API Key"
   - `ZAI_API_KEY` ← 1Password "GLM z.ai API"
   - `STEPFUN_API_KEY` ← 1Password "stepfun step5 ai api key" (field `credential`)
   `DEEPSEEK_API_KEY` already exists in prod and is not touched. No `*_BASE_URL`
   is set (adapters default to the vendors' general endpoints).
2. Verify by listing env var **names** only (`GET .../envvars/prod`).
3. Redeploy the prod worker from current `origin/main` with the repo's release
   path `pnpm --filter @oracle/workers run deploy` (per docs/configuration.md,
   a fresh boot reads new env). The main commit contains only additive provider
   code (PR #48, `5d5d262`) beyond what is deployed; default routes unchanged
   (asserted by `verify:adapter-request-shapes`).
4. Record the deploy version on the parent coordination issue.

## Risk and rollback

New keys are unused until an administrator selects a new route; defaults do not
change. Rollback: delete the three variables and redeploy the prior version.
Z.ai calls fail until its account has pay-as-you-go balance (known, owner-held).
