# T6 — production Map rebuild with the bake-off winners (handoff)

Written 2026-11-04 8:15 PM EST by the Claude Code T6 session on edge-dev3
(started by the coordinator session whose baton is
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-03T2349Z-edge-dev3-claude-model-bakeoff-coordinator.md ).
Issue: https://github.com/u2giants/theoracle/issues/255 (step 14).

## 0. Owner decisions

- **Albert, 2026-11-04 8:14 PM EST, verbatim:** "i want the brain to use the
  Muse direct API key." This is the new task in §6 step 2. No other owner
  question is open from this session.

## 1. What this is

The brain (`apps/brain`, FastAPI + one worker, Coolify app `oracle-brain`)
builds the Company Map from sources. T6 was the job of re-running production on
the per-stage bake-off winners: re-read the flowchart, then re-extract all
sources and rebuild, then store a seeded eval.

## 2. Goal and done-when

Gate (from the coordinator): the flowchart has arrows and no invented labels;
`/map` is populated with relations > 0; a seeded eval is stored whose `models`
manifest names the new seats; report the image SHA, flowchart counts, entity and
relation counts, and the eval_run id.

## 3. Current state (verified 8:14 PM EST)

Done:
- **Image:** `BRAIN_IMAGE_TAG=4402117e49f8b3f6a11915e56edd93e226faa064`
  (includes #393, #412, #414 and #420), deployed 7:03 PM EST. `/health` showed
  ok/db/graph all true. Earlier deploys this session were 2f832367 at 4:26 PM EST
  and d3ff7ab1 at 4:37 PM EST.
- **Seats (`GET /models`):** vision anthropic/claude-sonnet-5.5 (coordinator,
  4:47 PM EST); embed voyageai/voyage-4-lite; flat z-ai/glm-5.3-flash;
  **relations z-ai/glm-5.3** (coordinator re-seat, 7:58 PM EST, after the Muse
  block, §4); resolve, reports, recommend and grade openai/gpt-6-luna; answer
  anthropic/claude-haiku-5.5.
- **Flowchart gate MET.** Source `b74375da-…` (`Pop_Creations_Flow_12112025`),
  re-read by sonnet-5.5 at about 7:05 PM EST: 75 arrows, 62 labels, 0 invented,
  and all 67 of the 67 reference arrows (reference: `reference` in
  https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-03-stage-1-vision.json ).
  The Haiku re-read at 4:38 PM EST had given 79/62/0 and 65 of 67. Before that,
  the stored version had 0 arrows.
- **Full re-read:** all 31 sources re-queued as `read_source` at 7:03 PM EST.
  This replaced every chunk, and with it every old extraction, by cascade.

In flight (NOT done):
- Relations on GLM-5.3: 10 done, 17 queued at 8:14 PM EST. relations=200 so
  far. Re-extract of 5 failed `classify_extract` jobs: 1 running, 4 queued.
  `resolve` is queued; the worker then chains `project` and `communities`.
- OpenRouter limit_remaining $23.51 of $25 (resets midnight UTC = 7 PM EST).
- Entities 1146 is a stale count until resolve finishes.
- **Seeded eval NOT run yet. No eval_run id.**

## 4. What did not work

1. **Muse on OpenRouter is blocked.** From 7:41 PM EST, every relations call to
   `meta/muse-spark-1.3-contributor` returned 403 `user_blocked`, "Your access
   has been restricted due to repeated policy violations". All 27 relations
   jobs failed, and relations dropped to 0 because the re-read had deleted the
   old ones. Fixed by re-seating GLM-5.3 and re-queuing the jobs.
   Issue https://github.com/u2giants/theoracle/issues/426 . The **direct Meta
   key works**: `ai-muse doctor --live` was READY at 8:13 PM EST.
2. GLM flat returned invalid JSON on 4–5 chunks in each pass. A plain re-queue
   succeeded (Deborah Salles's Teams source at 5:23 PM EST).
3. Each Teams answer triggers the full resolve→communities chain, which closes
   redeploy windows. Issue https://github.com/u2giants/theoracle/issues/415 .
4. The Coolify deploy endpoint needs POST (GET says "changed to a POST request").
5. 1Password `op` CLI is not signed in on edge-dev3; use the 1Password MCP
   `op_run` with `op://` env refs.
6. The page candidate list (`stage-candidates.ts`) is gone: #402 deleted the
   model-pool page, so there is no page list to drop Muse from.

## 5. Root causes

- The Muse block is at the provider, for the OpenRouter route only; the cause is
  unknown (#426). The brain reaches every model through `OPENROUTER_BASE_URL`
  ( https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm.py#L17 ),
  so it cannot use a direct provider key without code.

## 6. Exact next steps

1. **Finish T6.** Wait (with a background waiter) until no `cmap.job` other
   than `interview_tick` is queued or running, and no relations job has failed.
   Check limit_remaining. Then check: relations > 0 and `/map/company`
   populated. Queue the eval with `POST /eval/run` (admin headers). Wait for it,
   then read `cmap.eval_run` newest: its `models` must show relations
   z-ai/glm-5.3 and vision sonnet-5.5. Report the eval_run id and the
   entity/relation counts on #255. If communities hits the cap, re-run
   `POST /map/rebuild`: it resumes with report reuse, so never restart.
2. **Owner task: the brain uses the Muse direct API key** (Albert, verbatim in
   §0). Add a direct Meta route to the brain: a per-provider base URL and key
   chosen from the seat's model id (e.g. ids starting with `meta-model-api/`
   go to Meta's API with a new env key, `BRAIN_META_API_KEY`). Model ids stay in
   env or the seat, never hard-coded (plan §11). Key: 1Password item
   `czggiabkpo7dt7ojep4btdvq5i` ("Meta ai Muse Spark API Key"), vault
   vibe_coding. Set it in Coolify by POST to `/applications/<uuid>/envs`. Find
   the base URL and model id that `ai-muse` uses (it reports model
   `meta-model-api/muse-spark-1.3-contributor`). Add tests, PR, merge, deploy
   when idle, then re-seat relations to the direct Muse id and re-run
   relations. Gate: a relations job succeeds on direct Muse in prod.
3. Leave #415 and #426 to their own sessions unless assigned.

## 7. Constraints

Coordinator baton §7 applies. Public repo: no IPs, project refs or secrets.
Never redeploy while a job runs. Times in EST.

## 8. Access

Coordinator baton §8 and its predecessor's §8. Coolify app uuid
`uge6pfm4qapktivto4981mtg`, API via the hetz tailnet. Brain admin headers:
`x-brain-token` plus `x-user-id` (admin user id in the predecessor §8).

## 9. Risks

- Other models on the OpenRouter key have shown no policy errors so far; watch
  for 403 `user_blocked` on any stage.
- Incoming Teams messages keep adding sources while the rebuild runs. That is
  harmless, but it lengthens the queue.

## Self-audit

The goal, state, failures, causes and next steps all have verified counts, times
and URLs. The owner request is quoted verbatim. No machine-local paths and no
secrets. Passed.
