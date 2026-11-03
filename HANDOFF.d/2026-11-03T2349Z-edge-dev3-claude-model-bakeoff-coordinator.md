---
issue: 255
status: OPEN
owner: claude/coordinator-model-bakeoff-2026-11-03 (edge-dev3)
---

# Company Map: nine-stage bake-off done, winners seated — coordinator baton

Written 2026-11-03, 6:50 PM EST, edge-dev3, Claude. Program parent:
https://github.com/u2giants/theoracle/issues/240 ; step 14:
https://github.com/u2giants/theoracle/issues/255 . Spec:
https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md .
Predecessor (dead ends, access, Appendix A with the 20 questions; keep it):
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-02T2057Z-edge-dev-mimo-model-overhaul-bakeoff-round2.md .

**The successor is a coordinator only.** It starts one nested session per task
in §6, verifies each result, and does no task work itself.

## 0. ⚠️ Business decisions only the owner can make

Put all of these to Albert in ONE message before starting. None blocks starting
the §6 tasks.

1. **Albert and Ilona edit the 20 draft eval questions** (predecessor Appendix
   A). Recommendation: this week. Blocks: the only real quality score, step-14
   acceptance.
2. **30-minute review of the first Map, marking wrong items.** Recommendation:
   after tasks T1–T5 and the rebuild (T6), so they review the better Map.
   Blocks: closing #255.
3. **One colleague says "hi" to the Teams bot.** Recommendation: any colleague.
   Blocks nothing; proves tenant auto-registration.

Already settled, do NOT re-ask:
- 2026-11-03 "Claude Sonnet 4.5 is an old model, i don't want to use that
  anymore." Winners seated per "prepopulate the site with the model that won
  for each".
- 2026-11-03 (stage 3 session) "then keep z-ai/glm-5.3-flash for descriptions".
- 2026-11-03 (stage 9 session) grader prompt revision approved ("yes").
- 2026-11-03 model pool page: nine stages, top three, score, OpenRouter price,
  tooltip, selectable.
- Predecessor §0 list ($25/day cap kept; tenant identity; no permission system
  beyond login + `is_admin`; reviews advisory).

## 1. What this application is

The Oracle is POP Creations' evidence-backed company adviser. The Company Map
reads company documents, diagrams and transcripts and shows how work flows.
`apps/brain` (Python FastAPI + worker) runs on Coolify as `oracle-brain`
(https://oracle-brain.designflow.app); `apps/web` (Next.js, Vercel) is
https://oracle.designflow.app ; Postgres schema `cmap` on Supabase; FalkorDB
graph `company`. The repo is PUBLIC.

## 2. What we set out to do

Finish the cheap-heavy-model bake-off. Albert widened it: test named current
models on all nine stages in nested sessions, record results in repo docs,
give a visual report with pricing, rebuild the model pool page, and seat the
winners. He then asked for wrap-up and one coordinator handoff.

## 3. Current state

Done and verified:
- Results for all nine stages:
  https://github.com/u2giants/theoracle/tree/main/docs/verification/company-map/bake-off
  (`2026-11-03-stage-*` .md/.json, plus lessons files).
- Visual report: https://claude.ai/artifact/2B8FjijhruXMDFXGaA2z1h (private).
- Per-stage seats merged, PR https://github.com/u2giants/theoracle/pull/357 :
  `cmap.model_seat`, `brain/seats.py`, `PUT /models/{stage}`, `reembed` job,
  page component `stage-candidates.ts` + `company-map-stages.tsx`.
- Save-button fix merged, PR https://github.com/u2giants/theoracle/pull/361
  (the proxy had no PUT).
- Migration 005 applied to prod. Brain image tag
  `c28ff450579be6f293de2f5e682472d1f8371b10`; `/health` all true.
- Live seats per `GET /models`, all source=page: vision and answer
  claude-haiku-5.5; embed voyageai/voyage-4-lite; flat z-ai/glm-5.3-flash;
  relations meta/muse-spark-1.3-contributor; resolve, reports, recommend, grade
  openai/gpt-6-luna. Coolify env also has BRAIN_FLAT_MODEL=z-ai/glm-5.3-flash
  and BRAIN_EVAL_MODEL=openai/gpt-6-luna. BRAIN_FRONTIER_MODEL is still
  sonnet-4.5 as the unused fallback.
- Prod re-index to Voyage finished: 97 chunks, 2045 mentions, 977 entities.

NOT done or NOT verified:
- **Stored Map content is unchanged:** it was built by the old models. New
  seats apply only on future runs (T6).
- **The flowchart still has bad content:** old gpt-4.1 returned 0 arrows and 23
  invented labels (source `Pop_Creations_Flow_12112025`).
- The live page has not been viewed signed-in and "Use this" has not been clicked
  in production after #361 (T1).
- A seeded eval on prod after seating (predecessor gate) has not run. Scores
  are not comparable with earlier ones because the grader prompt and grader
  changed (PR #335).
- Job brief not updated with results.

## 4. What did not work

1. Round-two swap runner omitted resolve: entities 0, invalid scores. Fixed.
2. Both real-corpus finalists then scored 0 on the five seed questions: those
   questions describe the fixture corpus, so they cannot rank real-corpus runs.
3. FalkorDB shared test instance dropped a connection under parallel use; give
   each parallel session its own container.
4. A background GLM communities run vanished without a log; never relied on.
5. `ai-doc-safety` hung under parallel runs (#345); several sessions merged on
   hand-checks. One full scan later passed.
6. Hand-written `sleep` + PR read and `gh run watch` are blocked here; use
   `ai-pr-wait <pr> --repo u2giants/theoracle`, or run an until-loop with
   run_in_background.
7. Nested sessions ended turns on "waiting" with nothing to wake them; message
   them to resume. Brief them to use a background waiter.
8. Stage 7 overspent ($4.56 vs $2.50). Nine parallel sessions need the cap
   checked by each one.
9. Brain tests monkeypatch `resolve._post_chat(messages, settings)`, so the
   stage seat is carried by a settings copy in `_Frontier`, not a new argument.

## 5. Root causes and findings

- Model choice cannot fix resolve quality: all candidates gave the same results
  on 23+18 hand-built pairs because the fixed rules decide (#353).
- All invalid community reports were truncation at the 4,000-token cap (#347);
  the company report was cut for 4 of 6 candidates including the winner.
- Communities embedding cost is O(n²) in open questions (#344).
- Winners are not always top scorers: GLM-5.3 tied Muse on links at 5× cost;
  DeepSeek edged GLM on flat at 12× cost; GLM edged Haiku on answers but every
  first call came back empty.
- Answering was tested in local mode on draft questions only.
- Recommended-model data on the page is hard-coded, which the #359 reviewer
  flagged against plan §11 (env-only ids). Albert explicitly asked for this
  list; candidates are data, live seats stay in the database.

## 6. Exact next steps — one nested session per task

Rules for every child: own worktree; own DB clone and own FalkorDB container
for tests; never run pytest against a DB another session is using; never
redeploy while a job runs; branch + PR + `gh pr merge --squash --admin`; check
OpenRouter `limit_remaining` and stop under $5. Report with a background waiter,
never a bare "waiting". Sequence T1–T5 before T6; T7–T11 may run in parallel,
but T2, T3, T4 and T5 touch overlapping brain files, so run those one at a time.

- **T1 Verify the page.** Signed-in browser: nine stages, three models each,
  tooltip shows, each stage's winner marked "In use"; switch a non-embedding
  stage away and back. Gate: `GET /models` follows, ends on winners.
- **T2 #359 remaining findings.** https://github.com/u2giants/theoracle/issues/359
  seat + reembed in one transaction; reembed entity text; do not cache seat
  read failures; reembed batching/resume. Gate: tests added, issue closed.
- **T3 #347 output cap.** https://github.com/u2giants/theoracle/issues/347 Gate:
  rerun of the issue's reports, none truncated.
- **T4 #344 embedding cost.** https://github.com/u2giants/theoracle/issues/344
  Gate: embedding calls grow linearly in a test.
- **T5 #353 resolve rules.** https://github.com/u2giants/theoracle/issues/353
  Gate: the issue's done-when on a `cmap_bake_5` clone.
- **T6 Rebuild prod with the winners.** After T2–T5 are deployed: re-read the
  flowchart first, then re-extract and rebuild the Map (`POST /map/rebuild`).
  Plan around the $25/day cap; start right after midnight UTC. Gate: flowchart
  has arrows and no invented labels; `/map` populated; seeded eval stored with
  the new models in its manifest.
- **T7 #345 safety check.** https://github.com/u2giants/theoracle/issues/345
  Tool lives in popcre/ai-devops; see also
  https://github.com/popcre/ai-devops/issues/2324 . Gate: finishes on edge-dev3,
  can scan only a PR's files.
- **T8 #358 review finding on BRAIN_FLAT_MODEL.**
  https://github.com/u2giants/theoracle/issues/358 and #339. Gate: each finding
  fixed or closed with evidence.
- **T9 Update the job brief.**
  https://github.com/u2giants/theoracle/blob/main/docs/company-map/model-stage-job-brief.md
  results table §5 and seats text (no longer Sonnet incumbent/frozen grader);
  add a per-stage note to the micro-evals file. Also sync `stage-briefs.ts`.
  Gate: doc safety passes.
- **T10 Teams interview build-out.** Plan:
  https://github.com/u2giants/theoracle/blob/main/docs/company-map/teams-interview-buildout-plan.md
  Phase 1, then onward. Gate: per plan.
- **T11 Lessons sweep.** Read every `2026-11-03-stage-*-lessons/learnings` file
  in the bake-off folder and open an issue for any follow-up not covered above.
  Gate: list posted on #240.
- **T12 Owner items and close.** After §0 answers: enter questions on the eval
  page, record the verbatim Map verdict in plan STATUS row 14, close #255, post
  the drift report on #240. Gate: #255 closed.

## 7. Constraints

Predecessor §7 applies. Public repo: no LAN IPs, project refs, or secrets. Never
push to main. Times in EST. Task gates: `ai-task-gates start --class production
--base <fresh main>`, then `check --before database --acknowledge "<Albert's
words>"`; the brain does not migrate on startup, run `python -m brain.migrate`.

## 8. Access

Predecessor §8 applies (1Password item ids, Coolify app
`uge6pfm4qapktivto4981mtg`, admin user id). edge-dev3 is the test-services host
(Postgres 56789, FalkorDB 56791, `cmap_bake_1..6`). psql is not installed on the
host: use `docker exec brain2-test-pg psql` or Python via `uv run`. Coolify env
create uses POST; PATCH on a missing key returns 404.

## 9. Open questions and risks

- OpenRouter had $7.92 of today's cap left at 6:49 PM EST.
- Muse is slow (about 38 s per passage) and GLM flat about 96 s per chunk: a
  large rebuild will take long. Single worker: a reembed blocks other jobs.
- `voyageai/voyage-4-lite` works on OpenRouter but its listing shows as
  `mongodb/voyage-4-lite`; if the old id is retired, switch to that one.
- Six review-finding issues predate this session; leave them to the fixer.
- The built-in browser is not signed in to the site, so the page was never seen signed-in: T1 owns it (the tenant sign-in may need Albert's Chrome session).

## Part (b) — nested sessions

All finished; none has live work. Each merged results to the bake-off folder.
- s1 vision (PR 330, 346): Haiku wins; flagged the flowchart. Did not switch.
- s2 embeddings (PR 328, 348): Voyage wins; no schema change needed.
- s3 flat (PR 331, 334, 338, 349, 360): GLM wins; richer ScaleDown labels shipped.
- s4 relations (PR 333, 341, 352): Muse wins; ScaleDown cannot match it.
- s5 resolve (PR 343): Luna wins; opened #353.
- s6 reports (PR 332): Luna wins; opened #347.
- s7 answer (PR 336, 351): Haiku stays; local mode only; overspent.
- s8 recommend (PR 342, 356): Luna wins; opened #344 and #345.
- s9 grader (PR 335, 350): Luna wins; grade prompt revised.

## Self-audit

1. Newcomer can continue: yes, §1, §3, §6 with predecessor §8.
2. As effective as me: yes, §4, §5, §9.
3. Every detail: §3 states verified vs not; §6 has gates.
4. Owner sees all decisions in §0 only: swept §1–§9 and part (b); the three
   items are the only business asks.
