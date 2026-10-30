---
issue: 255
status: OPEN
owner: claude/step14-hosting (edge-dev3)
---

# Company Map step 14 (hosting + first real run) and model split — baton

Written 2026-10-30, 10:42 AM EDT (1442Z), edge-dev3, Claude. Program: parent https://github.com/u2giants/theoracle/issues/240 ; step 14 issue https://github.com/u2giants/theoracle/issues/255 ; model split issue https://github.com/u2giants/theoracle/issues/294 . Spec: https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md (read STATUS first, then Step 14 and §8). This file does NOT retire any earlier baton (the step-9 baton https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-29T2340Z-edge-dev-mimo-company-map-step9-paused.md still holds the reviewer recipe and dead ends; retire it under the successor rule once step 14 closes).

## 0. ⚠️ Business decisions only the owner can make

Put all of these to Albert in ONE message before starting.

Blocking step 14 acceptance:
1. **Albert and Ilona write the 20 evaluation questions** (plan §8: one hour, once; each question must need three or more sources). They go in on the Map's eval page as admins. Recommendation: do it this week. Until then the real-corpus eval can only run on the five seed questions.
2. **Albert messages the bot from his own Teams** (step 12 manual proof, carried to step 14). Recommendation: one message ("hi") after the hosted Map is confirmed. Interviews to real employees stay OFF (`BRAIN_INTERVIEW_ENABLED=false`).
3. **Albert and Ilona spend 30 minutes marking wrong items on the first Map** (plan Step 14 item 8). Record their verbatim verdict in STATUS.
4. **Remaining corpus.** Only the 8 new Oracle 1 bucket files are in so far (26 objects: 8 imported, 18 were duplicates of already-ingested files). The "hundreds of documents, diagrams and transcripts" are not uploaded yet. Recommendation: Albert drops them into the upload page (Map → Sources) or names a folder the AI can copy into the import volume.

A wrong guess is recoverable (spend):
5. **OpenRouter $25/day cap.** Recommendation: keep it. The cheaper heavy-work model (below) cuts spend by roughly 10x, so the cap stops being a bottleneck.

Already settled — do NOT re-ask: model split and Haiku 5.5 as the only Claude model (Albert, 2026-10-30, quoted in §2); reviews are advisory and never block merges (owner ruling 2026-10-29); FalkorDB stays; no permission system beyond login + `is_admin`.

## 1. What this application is

The Oracle (https://github.com/u2giants/theoracle) is POP Creations' evidence-backed company adviser. The current program is the Company Map. It reads company documents, diagrams and employee transcripts and shows how work actually flows: where hand-offs break, plus answers that cite many sources. `apps/brain` is a Python FastAPI service plus a worker loop that does all AI and graph work. Postgres (Supabase project `theoracle`, project ref PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d, schema `cmap`) is the durable store; FalkorDB holds the graph `company`. `apps/web` is Next.js on Vercel (production https://oracle.designflow.app), which proxies `/api/brain/*` to the brain.

## 2. What we set out to do, and why

- Step 14 of the plan: host the brain on Coolify, wire Vercel, run the first full pipeline on the real corpus, and record the counts, the eval and the owner review.
- Mid-session owner direction (relayed by the coordinator), Albert verbatim: "the heavy role move to a cheaper model now. what model did you use so far? also, you should separate out the conversation model from the others as Claude is the best at conversations." Earlier he said that long-term the only Claude model in use is Haiku 5.5, for interaction with humans.

## 3. Current state (verified 10:42 AM EDT 2026-10-30)

Landed on main:
- PR https://github.com/u2giants/theoracle/pull/290 (merge `897efa4c`) adds the brain image workflow (`.github/workflows/brain-image.yml`, publishing `ghcr.io/u2giants/theoracle-brain:<sha>` and `:latest`, main only) and the Coolify compose https://github.com/u2giants/theoracle/blob/main/apps/brain/deploy/compose.coolify.yaml (brain plus pinned FalkorDB, `FALKORDB_DATA_PATH=/data`, `--save 60 1`, no public FalkorDB port), with tests `apps/brain/tests/test_deploy.py`. Claude Opus review: round 1 FIX, round 2 APPROVE (comments on #255).
- PR https://github.com/u2giants/theoracle/pull/293 (merge `6e00de2b`) adds `EXPOSE 8000`; Coolify's API strips the port from the domain. Review APPROVE.
- PR https://github.com/u2giants/theoracle/pull/295 (merge `1b4f350e`) adds `BRAIN_CHAT_MODEL` (answers) and `BRAIN_EVAL_MODEL` (grader), each falling back to `BRAIN_FRONTIER_MODEL`. It also adds the plan §8 row and the test `apps/brain/tests/test_model_split.py`. CI was green except the known non-required old suites (Oracle offline suites, oracle2-offline, Entire Gates).

Live:
- Coolify project "Oracle Company Map" (uuid `tpqm0y6dldtqizsrpig17wmd`) holds the docker-compose application `oracle-brain` (uuid `uge6pfm4qapktivto4981mtg`). It builds from GitHub main and runs image tag `6e00de2b…` (env `BRAIN_IMAGE_TAG`). `https://oracle-brain.designflow.app/health` returns `{"ok":true,"db":true,"graph":true}`. Cloudflare DNS: A record `oracle-brain` → 178.156.180.212, DNS only.
- Coolify env holds all §12 variables, with secrets from 1Password: `BRAIN_MAX_FRONTIER_CALLS_PER_JOB=3000`, `BRAIN_INTERVIEW_ENABLED=false`, `BRAIN_WEB_BASE_URL=https://oracle.designflow.app`, `SUPABASE_URL=https://PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d.supabase.co`. The service-role key was fetched through the Supabase management API using the "Supabase CLI Personal Access Token" item. It was NOT stored as a separate 1Password item.
- Live models (Coolify env): frontier `anthropic/claude-sonnet-4.5`, vision `openai/gpt-4.1`, embeddings `openai/text-embedding-3-large`. `BRAIN_CHAT_MODEL` and `BRAIN_EVAL_MODEL` are not set yet.
- Vercel production env now has `BRAIN_BASE_URL=https://oracle-brain.designflow.app` and `BRAIN_SHARED_TOKEN`. Production was redeployed (`dpl_EwjXKTgwkMCk5aA5HDX9WTDXDXQX`). `/map` redirects to login (307) and `/api/brain/health` answers 401 when logged out. A logged-in render has NOT been checked yet.
- `python -m brain.migrate` ran against prod Supabase ("cmap schema applied").
- Real-corpus run (started by `POST /sources/import-bucket` at about 2:50 AM EDT): 8 sources, 97 chunks, 289 extractions, 977 entities. Read, classify, relations, resolve and project are done. The `communities` job is STILL RUNNING: 310 community reports by 10:37 AM EDT, steady at about one every 2–4 minutes, no failed jobs. `recommend` is chained after it.

Not started: `docs/verification/company-map/first-run.md`, STATUS row 14, the switch to the cheap heavy model, the real-corpus eval, the Teams self-test, and the owner review.

## 4. Dead ends (do not repeat)

1. Coolify `PATCH docker_compose_domains` with `https://host:8000`: Coolify drops the port, and Traefik then answers 503 "no available server". The fix is `expose: ['8000']` + `EXPOSE 8000` (PR #293).
2. Copying `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from Vercel's decrypted env API: Vercel returned encrypted blobs (1,000+ chars). The import-bucket call then failed with "Request URL is missing an 'http://' protocol". Use the Supabase management API (`/v1/projects/PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d/api-keys?reveal=true`) instead.
3. Python `urllib` against coolify.designflow.app: Cloudflare error 1010 (bot signature). Send `User-Agent: curl/8.5.0`.
4. The `op` CLI on edge-dev3 is not signed in. Use the 1Password MCP `op_run` with `op://vibe_coding/<item-id>/<field>` refs. `op_run` times out after 10 minutes, so for long waits write the DB URL to a 0600 file under `$TMPDIR` and run in the background.
5. Cheap candidates `deepseek/deepseek-v4.1-flash` and `qwen/qwen3.8-flash` crash the relations stage with "frontier relations message content is not text". These reasoning models return empty `content`, most likely because reasoning consumed `max_tokens`. Their eval scores (0.47 and 0.40) were computed on an empty graph and are INVALID.
6. `anthropic/claude-haiku-5.5` as `BRAIN_CHAT_MODEL` returned empty message content on 2 of 5 eval answers ("frontier answer response has no message content", three retries). Fix that before setting it live.
7. The edge-dev3 test containers `brain2-test-pg` and `brain2-test-falkordb` stopped at some point (`Exited (0)`); `docker start` them. They share one FalkorDB graph name, so never run a candidate eval and pytest at the same time.

## 5. Key findings

- Fixture candidate eval, 2026-10-30, grader Sonnet 4.5: `google/gemini-3.1-flash-lite` (OpenRouter price $0.25/M input, $1.50/M output, versus Sonnet's $3/$15) ran the full fixture pipeline: resolve, project (444 nodes, 355 edges), and 299 community reports with 0 failed. Eval mean 0.47 against the Sonnet baseline of 0.40 (PR #282). It cost about $2.28 for the whole fixture pipeline, mostly the 332k community-report tokens. It is the only valid candidate so far and is no worse than the baseline.
- The real-corpus run on Sonnet spent about $18 of the $25 daily cap by 4:46 AM EDT, mostly community reports.
- Recommendation dedup and robustness defects are open as review finding https://github.com/u2giants/theoracle/issues/289 . It covers: number scrub misses days and units; embed failures abort the recommend job; `communities` enqueues `recommend` unconditionally, giving duplicate jobs; review-days validation.

## 6. Exact next steps

1. **Let the real-corpus `communities` job finish** (do not restart it or truncate; resume is built in). Probe `select count(*), max(created_at) from cmap.community` and `cmap.job` states. If no new report appears for 30 minutes, check the Coolify app logs (API `/applications/uge6pfm4qapktivto4981mtg/logs`) and the OpenRouter key balance (`/api/v1/key`). A 403 "Key limit exceeded" means wait for the 8:00 PM EDT reset; the job resumes on rerun. Done when: `communities` and `recommend` are `done`.
2. **Fix empty-content handling for reasoning models** (new PR under #294). In `brain/extract/relations.py` `_call_model`, `brain/resolve/resolve.py` `_Frontier.ask`, `brain/answer/answer.py`, `brain/eval/run.py` and the vision call: send OpenRouter `"reasoning": {"effort": "low", "exclude": true}` from an env flag (`BRAIN_REASONING_EFFORT`, default unset) or raise `max_tokens`, and retry once on empty content. Add a test with a recorded empty-content response. Done when: Haiku 5.5 answers all 5 seed questions, and DeepSeek V4.1 Flash and Qwen 3.8 Flash complete the relations stage on the fixtures.
3. **Rerun the candidate eval** after the 8:00 PM EDT reset: the three candidates plus Sonnet as the same-day baseline, using a fresh DB per candidate. A script recipe is in §8. Pick the cheapest whose mean ≥ the Sonnet run. Record per-candidate mean and dollars in #294 and in the plan §8 row. Until step 2 lands, the default pick is `google/gemini-3.1-flash-lite`.
4. **Switch live env**, only after step 1 finishes: in Coolify set `BRAIN_FRONTIER_MODEL=<chosen>`, `BRAIN_CHAT_MODEL=anthropic/claude-haiku-5.5` (only after step 2) and `BRAIN_EVAL_MODEL=anthropic/claude-sonnet-4.5` (fixed grader), set `BRAIN_IMAGE_TAG` to the latest main SHA, and redeploy (`POST /api/v1/deploy?uuid=uge6pfm4qapktivto4981mtg`). Done when: `/health` is true and the Coolify env shows the new ids.
5. **Prove the hosted Map:** log in as the Supabase test employee (1Password tags `oracle` / `test-login`) and open https://oracle.designflow.app/map. Screenshot the company report built from the real corpus. Done when: the page renders communities from the real sources.
6. **Fix #289's findings** in a PR (especially the unconditional `enqueue_job("recommend")` in `apps/brain/brain/graph/communities.py`, which produces duplicate recommendations).
7. **Write `docs/verification/company-map/first-run.md`** with source, chunk, entity, edge and community counts, the eval mean, cost, and the models used. Update STATUS row 14 to "🟨 hosted, awaiting owner review" with evidence (PR #290/#293/#295, health URL, counts). Merge on green CI.
8. After the owner items in §0 (the 20 questions, the Teams self-test and the 30-minute review): run `evaluate`, record their verdict verbatim in STATUS, tick #255, close it, and post a drift note on #240.
9. **End-of-plan drift check (required):** re-read plan Part 1 and every downstream phase, compare them with what is live, and post a drift report on #240 covering what diverged, what should change, and the open items.

## 7. Constraints

- Model ids live in env only, never in code. Secrets come only from 1Password vault `vibe_coding` and never appear in chat, logs or git.
- Do not enable Teams interviews to real employees. Do not raise the OpenRouter cap.
- Reviews are advisory (owner ruling 2026-10-29): merge on green CI. The red non-required checks (Oracle offline suites, oracle2-offline, Entire Gates) are pre-existing.
- Production changes are deployed from GitHub main via Coolify; never edit the server by hand.
- Never run pytest against a DB whose smoke counts you need (conftest truncates `cmap.*`).
- Sign GitHub posts with `$AI_GH_SIGNATURE`. Quote times in EDT.

## 8. Access

- Machine edge-dev3 (Linux, Docker). Worktree `theoracle-step14-hosting` next to the canonical checkout. `gh` is authenticated as u2giants.
- 1Password `vibe_coding` items: Coolify read/write token `u3aqw63jqnkmnziip3gp5hwb5m`/`credential` (API base https://coolify.designflow.app/api/v1); Cloudflare `eclkf24wddwek7qmfxxlwc36he`/`credential` (zone designflow.app `921eb133a3f7d5802780445b283f84ce`); Vercel PAT `3bgyzyrc7t7qi5ux47ibry44pi`/`credential` (project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`, team `team_FonXKKdriM1qMhxHlJNqzaFz`); Supabase PAT `3t2xoqk5luyz7ffgdhj24gvtpq`/`credential`; prod DB `qcuyabwseaptvuzvtjejffi2ou`/`oracle_session_pooler`; OpenRouter `62ieeyycs4ierflalbbbt5pq5i`/`OPENROUTER_API_KEY`; ScaleDown `epna47xmzcnbdc6eb3tjpx6phm`/`SCALEDOWN_API_KEY`; shared token `4lm6bpl7bc25lqne4meumwcd2a`/`BRAIN_SHARED_TOKEN`; Anthropic reviewer key `5uq6z66ibusmypkvnl276ta22e`/`credential`.
- Admin API calls to the brain need the header `x-brain-token` plus `x-user-id` = the auth user id of an active `is_admin` employee (look it up from `public.employee_identities`).
- Candidate eval recipe: for each model, create a fresh DB on `brain2-test-pg` (port 56789) and delete the graph `company` on `brain2-test-falkordb` (port 56791). Set `BRAIN_FRONTIER_MODEL=<candidate>`, `BRAIN_CHAT_MODEL`, `BRAIN_EVAL_MODEL=anthropic/claude-sonnet-4.5`, vision, embed and ScaleDown env. Run `uv run python -m brain.smoke --live`, then `uv run python -m brain.eval.run --seed`, and read the spend from the OpenRouter `/api/v1/key` `limit_remaining` before and after. Abort if less than $3 remains.

## 9. Open questions and risks

- Haiku 5.5 empty answers (dead end 6) block the conversation-model switch. Risk: users get "answer failed".
- The fixture eval has only 5 questions, so the gap between 0.47 and 0.40 is noise-level. The cheap pick is "no worse", not "better".
- The real corpus so far is only 8 sources. The Map will look thin until Albert supplies the rest (§0 item 4).
- FalkorDB data on Coolify persists on the volume `oracle-falkordb-data`. There is no off-server backup, but the graph can be rebuilt from Postgres (`/map/rebuild`).

Self-audit (handoff-writer gate): (1) A newcomer can continue: §1, §3 and §6 give the live state, ids and ordered steps with gates. (2) As well as I could: §4 and §5 hold every non-obvious finding from this session (Coolify port, Vercel blobs, Cloudflare user agent, reasoning-model empty content). (3) Complete: goals in §2, state in §3, failures in §4, decisions in §0 and §5, constraints in §7, access in §8, risks in §9. (4) Owner sweep: every "Albert" or "owner" mention in §2–§9 (eval questions, Teams self-test, 30-minute review, corpus upload, cap) appears in §0, and §0 holds no technical approval.
