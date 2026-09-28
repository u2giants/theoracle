# Provider API keys for production — exact dispatch for review (revision 5)

Status: awaiting review. Tracking issue: #49. Nothing here runs before a
`VERDICT APPROVE` whose record names the reviewed commit of this file; the
operator executes only from that commit and re-requests review if it changes.

Owner request (Albert, Claude chat, 2026-09-28), verbatim: "add the keys".
Also verbatim: "All data can be shared with all Ai providers." and "let's put
z.ai on hold for now and use the others." The smoke proof below sends only
synthetic text. Revisions 1-4 were refused (qwen plan reviews); revision 5
addresses every finding of the revision-4 review.

## Scope

- Keys: `META_MUSE_API_KEY` (1Password `vibe_coding` item "Meta ai Muse Spark
  API Key") and `STEPFUN_API_KEY` (item "stepfun step5 ai api key", field
  `credential`). Z.ai excluded (owner hold). No `*_BASE_URL` in any target.
- Targets: Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` (`popcre/theoracle`)
  Production, and Trigger.dev `proj_wgpzsvhmsopqhvwqaycn` `prod`. Nothing else.
- No new code is deployed anywhere. The Vercel step rebuilds the commit already
  in production; Trigger gets variables only.
- **The Trigger half is inert until the next worker release.** Workers read env
  at boot and the deployed worker (`20260909.1`) predates the adapters, so the
  two Trigger variables are unread until the separately reviewed worker release
  (`docs/operations/2026-09-28-worker-release-dispatch.md`) ships. That is
  intended: this dispatch pre-stages them so that release needs no env change.
  The Vercel half takes effect at step 3.3.

## Operator rules

- Run each command separately and check its exit status before the next; no
  `&&`/`;` chaining across a gate or between writes.
- Secrets: `export NAME="$(op read 'op://vibe_coding/<item>/<field>')"` then
  `test -n "$NAME"`; values stay in the shell environment and stdin, never on
  disk, in argv, or printed. Every HTTP call with a secret is made by a short
  `python3 -c` program that reads the PAT and value from `os.environ` and sends
  them with `urllib.request` (secrets never appear in any process's argv);
  `curl` is not used for secret-bearing calls. Values piped to the Vercel CLI use
  `printf '%s' "$NAME" |` (no trailing newline).

## Step 0 — gates and approval record (before any write)

0. CI on the current `origin/main` head is green (`gh run list --branch main`;
   at authoring, head `a12e25e`: PR check, task gates and Oracle 2 contracts
   succeeded). Stop if not.

1. `ai-task-gates start --class production --base origin/main`, then
   `ai-task-gates check --before production`; stop on anything but pass.
2. Post on #49: reviewed commit of this file, the approving review record file
   name and its `VERDICT APPROVE` line.

## Step 1 — prove the exact values (fail-closed)

1. `git fetch origin`; create a fresh worktree from `origin/main`; require
   `git log origin/main` to contain `5d5d262` (PR #48 adapters). In it run
   `corepack pnpm install --frozen-lockfile` (no secrets involved).
2. In it: `test ! -e .env.local` and `test ! -e .env`; `unset META_MUSE_BASE_URL
   STEPFUN_BASE_URL`; export both keys as above.
3. Run `corepack pnpm --filter @oracle/ai exec tsx src/__verify__/r-providers-smoke.ts
   meta_muse`, then the same with `stepfun`. **Pass only if** each output contains
   `✓ <provider>.generateText` and `✓ <provider>.generateObject`, contains no
   `SKIP`, and exits 0. Otherwise stop before any write.
4. Run `corepack pnpm --filter @oracle/ai run verify:adapter-request-shapes` (asserts no
   production default route uses a new provider); must pass.

## Step 2 — record current state (execution time)

1. Vercel (CLI pinned `npx vercel@60.1.3`): `vercel whoami`; `vercel project
   inspect theoracle --scope popcre` must show `prj_rP6Jlima7iK1paffEPhLqxlswGsC`.
   `vercel ls theoracle --prod --scope popcre` gives the newest Ready deployment;
   `vercel inspect <it>` gives its source commit, which must equal freshly
   fetched `origin/main` HEAD, else stop. Record it as `PROD_BEFORE`.
2. `vercel env ls production --scope popcre --project theoracle`: both names must
   be absent (else stop and re-review). `vercel env add --help` must list
   `--sensitive`.
3. Trigger: current prod deployment (must still be `20260909.1`, which predates
   the adapters; else stop); `GET
   https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod`
   (names only): both names absent, `DEEPSEEK_API_KEY` present.

## Step 3 — writes

1. Trigger: for each key, `POST .../envvars/prod` with body
   `{"name": "<NAME>", "value": "<value>"}` (documented body, no extra fields),
   PAT from item "Trigger.dev Personal Access Token (management)" in the
   environment, sent as described under Operator rules. Expect 200. Then
   `GET .../envvars/prod/<NAME>` (documented Retrieve endpoint) and compare the
   SHA-256 of the returned value with the SHA-256 of the local value inside the
   same python program; print only "match"/"mismatch". Mismatch = failure.
2. Vercel: for each key, `printf '%s' "$NAME" | vercel env add <NAME> production
   --sensitive --scope popcre --project theoracle`. Sensitive values cannot be
   read back, so their correctness rests on step 1's smoke of the same
   environment variable plus this newline-free transport.
3. Vercel: re-check `PROD_BEFORE` is still the newest production deployment
   (stop if not), then `vercel redeploy PROD_BEFORE --target production`; wait
   for Ready; `vercel inspect` must show the same source commit. If the redeploy
   fails or errors, production keeps serving `PROD_BEFORE` (Vercel promotes only
   a Ready build); treat it as a failure under the rule below.

Partial failure: if any write, verification or the redeploy fails, delete every variable this run created
(`vercel env rm <NAME> production --yes`; Trigger `DELETE .../envvars/prod/<NAME>`, the documented Delete Env Var
endpoint https://trigger.dev/docs/management/envvars/delete), leave `PROD_BEFORE` serving, record on #49, and stop.

## Step 4 — verify and close out

1. Names present in both targets (`vercel env ls`, Trigger `GET`).
2. Post the new Vercel deployment id and outcome on #49.
3. Same PR as this file, after execution: add rows for both keys to
   `docs/agents/12-credentials-and-environment.md` and "set in Vercel Production
   and Trigger prod on 2026-09-28" notes to `docs/configuration.md`.

## Rollback

`vercel rollback PROD_BEFORE --scope popcre` (or dashboard Instant Rollback),
`vercel env rm <NAME> production --yes`, Trigger `DELETE .../envvars/prod/<NAME>`.
No default route changes (step 1.4), so user-visible behavior is unchanged until
an administrator selects a new route.
