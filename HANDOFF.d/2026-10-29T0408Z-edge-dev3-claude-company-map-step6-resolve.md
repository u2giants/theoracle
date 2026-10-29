# Company Map Step 6 (entity resolution) — PR open, awaiting independent review

Written 2026-10-29 12:10 AM EDT by Claude (Opus 5.5) on edge-dev3. Issue: https://github.com/u2giants/theoracle/issues/247 (parent #240). PR: https://github.com/u2giants/theoracle/pull/271 (branch `brain/step06-entity-resolution`).

## 1. Goal
Implement Step 6 of https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md (merge the same thing named differently), exactly as written.

## 2. Done
- Code on the PR: `apps/brain/brain/resolve/resolve.py` (alias → exact → Person first-name/initials → cosine ≥0.92 → frontier judge for [0.80,0.92) → new entity; then counts + frontier description at ≥3 mentions once per count), `brain/sql/002_resolve.sql` (`cmap.resolve_decision` + `entity.described_at_count`), prompts `resolve_judge.md` / `entity_describe.md`, worker registration, relations job queues one `resolve`, smoke prints entities.
- Gate: `apps/brain/tests/test_resolve.py` (7 tests) — CI "brain tests" PASS on PR #271; local 52 passed, ruff clean.
- Live smoke (real ScaleDown + `anthropic/claude-sonnet-4.5`), partial at 12:08 AM EDT: 982 mentions, 0 unresolved, 477 entities, 21 joined across ≥2 sources (e.g. Person "Jessica (Licensing Manager)" 20 mentions / 3 sources; Department Licensing 3 sources; System Artwork Log 3 sources). Judge: 20 verdicts (3 same). 26 descriptions written; describe phase still running when session closed.

## 3. Not done
- Independent review per the prompt in issue #247 (Albert starts a fresh Opus/Fable session). Reviewer merges, ticks boxes, updates plan STATUS row 6.
- Plan STATUS row 6 not updated (reviewer does it on APPROVE).

## 4. Known issues / tried
- CI "Oracle offline suites" and "oracle2-offline" fail on PR #271 with `KeyError: 'uses'` in `test_ci_trust_boundary` — identical failure on merged PR #270; old-program suite, not this step.
- Live smoke Jessica canonical name came out "Jessica (Licensing Manager)" (no surname in the corpus); the step's done-when ("one Person Jessica, source_count ≥2") holds.
- `op` CLI on edge-dev3 is not signed in; use the 1Password MCP `op_run` with `op://vibe_coding/62ieeyycs4ierflalbbbt5pq5i/OPENROUTER_API_KEY` and `op://vibe_coding/epna47xmzcnbdc6eb3tjpx6phm/SCALEDOWN_API_KEY`. It times out at 10 min but the child keeps running; its stdout redirect to the session scratch dir did not land, so read results from the database instead.
- Local test Postgres: docker container `s6pg` (pgvector pg16, port 56790, db brain_test); remove with `docker rm -f s6pg` when finished.

## 5. Interpretation notes (also in PR body)
Ambiguous first name goes to judge regardless of cosine; longest names resolved first; `test_schema` table set includes `resolve_decision`; extra column `described_at_count`.

## 6. Next action
Albert: paste the review prompt from issue #247 into a fresh Claude Opus or Fable session.

## 7. Verify
`gh pr view 271 --json state` = MERGED; plan STATUS row 6 ✅ citing test_resolve.py + CI run.

## 8. Retention
Delete this file once #247 is closed and PR #271 merged.
