# T11 lessons sweep and follow-ups: handoff (2026-11-04, 6:39 PM EST)

Owner: Albert Hazan. Repo: https://github.com/u2giants/theoracle . Parent issue
https://github.com/u2giants/theoracle/issues/240 , step #255. Session: edge-dev3
Claude, started by the bake-off coordinator as task T11.

## 1. Goal

Read every 2026-11-03 stage lessons file, open an issue for each uncovered
follow-up, then (at Albert's request "resolve all") resolve them.

## 2. Done and verified on GitHub

- Sweep list posted: https://github.com/u2giants/theoracle/issues/240#issuecomment-6618601920
  and status: https://github.com/u2giants/theoracle/issues/240#issuecomment-6636017309
- Closed with evidence: #363 (second diagram; PRs #409 #411), #364 (145 alias
  pairs), #365 (relations output cap, PR #396), #366, #368 (PR #400), #369
  (Recall MCP: new key from Albert works), #399 (merge name compare, PR #403),
  #413 (vision seat), #418 (transparent images flattened to white, PR #420).
- New vision bake-off, 10 models x 7 diagrams:
  https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-04-stage-1-vision-round2.md
  Sonnet 5.5 0.991, Gemini 3.8 Flash 0.976, GPT-6 Luna 0.966, MiniMax M3.1
  Flash 0.957, Haiku 5.5 0.951. The coordinator decided to seat Sonnet 5.5.
  Seated through the page route (`PUT /models/vision`), and `GET /models` shows
  source "page". Job brief updated in PR #419.

## 3. Still open

1. **#367 answer-test rerun.** This waits on Ilona's final 20 questions. Review
   page: https://claude.ai/artifact/1dw8ZoafmchL3HZ9mW26KX (artifact slug
   05282281-8fc8-4d2f-a61e-4760a9bdb45e). It is private to Albert and must be
   shared with Ilona as Contributor; the artifacts tools cannot share it. Its
   buttons are untested, because no signed-in browser was available. Read her
   answers back with `db_list` collection `questions` (docs q01–q20 plus
   `new-<ts>`) and `db_get` `review/status` (`done`). Then rerun stage 7 on
   those questions (about $2) on a cloned DB, and close #367.
2. **#420 is merged but not deployed.** It must not deploy while the T6
   rebuild runs. T6 (session local_343186dd-1587-4e7d-9414-5dff6fc9ad5c) has
   been told; it deploys after its rebuild.
3. **#413-derived note:** Haiku dropped org-chart lines. This is moot now that
   Sonnet is seated.

## 4. Constraints

Never modify cmap_bake_* or cmap_s8_base; clone them with createdb -T. Keep
OpenRouter limit_remaining above $15 (it was $17.52 at 4:47 PM EST). Never
redeploy the brain while a rebuild runs. Sign GitHub posts with
$AI_GH_SIGNATURE. Quote all times in EST.

## 5. Verify done

#367 is closed, with a rerun report on the owner-final questions in the
bake-off folder.
