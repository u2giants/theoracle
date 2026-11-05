---
issue: 437
status: OPEN
owner: mimo/ses_ffe5e53cd4c93ffeoxM2HwUc87
---

# Handoff — community-size fix (#437): live proof and deployment follow-through

Machine: ah-desktop. Agent: MiMo. Session: `ses_ffe5e53cd4c93ffeoxM2HwUc87`.
Written 2026-11-05 11:41 AM EST (2026-11-05T1641Z).

## 0. Business decisions only the owner can make

1. **Entities with no evidence on the map.** 405 entities in the Oracle Company Map
   corpus have no mention rows left (their supporting document mentions were deleted
   when sources were deleted), so they carry no quotes and no sources. The fix folds
   them into the most similar community so every community is a real cluster
   (size 3–150). If the owner would rather hide such evidence-less entities from the
   map entirely until evidence returns, that is a product change (small: filter them
   out of the graph projection). **Recommendation: keep the fold as shipped** — the
   entities are real (361 of 387 exact names still appear verbatim in current
   document text) and hiding them loses real knowledge. Answer "keep" or "hide".
   Blocks: nothing today; only future map shape.

Nothing else in this workstream needs the owner. Deployment sequencing is with the
step-14 coordinator (an AI session), not the owner.

**Already settled — do NOT re-ask:** the fix direction (a fold pass in the community
merge so every L0/L1 group is 3–150 entities) was the task's own done-when
(coordinator handoff §6.7, 2026-11-05). Reviews never block a merge (owner ruling
2026-10-29).

## 1. What this application is

The Oracle is an evidence-backed enterprise knowledge graph for POP Creations /
Spruce Line. Employees upload documents; workers extract entities and typed
relations with quote-level evidence; the Company Map clusters entities into
communities (level 0 = areas, level 1 = parts of the company, level 2 = the whole
company) and a frontier model writes one report per community, every finding
traceable to a source.

- Repo: https://github.com/u2giants/theoracle (PUBLIC — never commit secrets, LAN
  IPs, or Supabase project references).
- App: `apps/brain` (Python FastAPI + worker). Brain live at
  https://oracle-brain.designflow.app (`/health` needs no auth).
- Postgres schema `cmap` on the Supabase project "theoracle"; FalkorDB holds the
  projected graph. Deployment is Coolify service `oracle-brain` on the Hetz VPS.

## 2. What we set out to do this session, and why

Task from the step-14 coordinator (issue https://github.com/u2giants/theoracle/issues/255,
program #240), verbatim scope: fix
https://github.com/u2giants/theoracle/issues/437 — 607 communities with ≤2 entities
at L0/L1 despite the earlier #410 fix (PRs #412/#414). Done-when: "#437 shows a fix
whose L0/L1 groups are all ≥3 or ≤150 entities" — proven with a real query and
counts in a comment on #437.

## 3. Current state — what is true right now

**Delivered (done-when met):**
- Fix merged: https://github.com/u2giants/theoracle/pull/451 (squash commit
  `5783e7ecdfb6dac94c2536595225e1e66d385a6f`, merged 2026-11-05 11:16 AM EST).
  Branch `mimo/task67-community-size-fix` (merged, can be deleted).
- Proof comment on #437 with the measured distribution, query and counts:
  https://github.com/u2giants/theoracle/issues/437#issuecomment-6663524575
- Live-proof checklist left on #437 (the stored-rows confirmation):
  https://github.com/u2giants/theoracle/issues/437#issuecomment-6663588332
  — `- [ ] live proof` is still unticked there.

**Measured evidence (fixed code from main run read-only over live production data,
1787 entities / 1884 edges, 2026-11-05 11:15 AM EST):** L0 = 34 groups, sizes 3–94,
zero outside [3,150]; L1 = 26 groups, sizes 3–149, zero outside [3,150]. Full
size histograms are in the proof comment.

**Not yet true (the gap this handoff carries):**
- The deployed brain image does NOT yet contain the fix. `BRAIN_IMAGE_TAG` in the
  Coolify env was pinned to a pre-fix image sha (pin last updated 2026-11-05
  07:13 UTC). This session corrected it to `5783e7ecdfb6dac94c2536595225e1e66d385a6f`
  at 2026-11-05 11:34:35 AM EST (env PATCH only — no deploy). The next deploy pulls
  the fixed image.
- The stored community rows still show the old grouping: at `graph_version` 25
  (query on 2026-11-05 11:25 AM EST) `cmap.community` held 439 L0 groups of which
  405 had ≤2 entities (L1 429 / 405 small). Those rows are the old code's output
  plus reused older reports — one re-cluster after the deploy replaces them at a
  new `graph_version`.
- The step-14 coordinator (session `ses_ffe5e53cd4c93ffeoxM2HwUc87:build`) was
  sequencing a deploy of PR #449 and instructed all children to hold off deploys
  and long prod jobs until its all-clear (message 2026-11-05 11:32 AM EST). Its
  deploy `ehbllrkc668qmqr0sepmaxbt` started while `BRAIN_IMAGE_TAG` was still the
  stale pin, so it too will have pulled the old image unless it patched first —
  check with the coordinator before assuming anything is live.

**Commit/push/deploy status:** code committed, pushed, PR opened, CI green
(brain tests, company map browser test, brain image, build), squash-merged to
`main`. Deploy: env pin corrected; deploy itself owned by the coordinator.

## 4. Everything we tried that did NOT work

1. **First deploy pulled the stale image.** Deployed at 11:21 AM EST (deployment
   `byfdobm7myihldtjhhhfd99k`, commit `5783e7ec` checked out and built) and queued
   a project→communities re-cluster — which finished in 69 seconds having changed
   nothing: `BRAIN_IMAGE_TAG` was pinned to `faa3482ff2b00ea80bf40260950d73077ac69e39`
   (a pre-fix image), so the container ran the OLD code and the report-reuse logic
   re-tagged old rows instead of clustering anew. Lesson: **always read
   `BRAIN_IMAGE_TAG` (GET `/api/v1/applications/uge6pfm4qapktivto4981mtg/envs`) and
   PATCH it to the intended image sha BEFORE triggering a deploy** — the compose
   file at https://github.com/u2giants/theoracle/blob/5783e7ecdfb6dac94c2536595225e1e66d385a6f/apps/brain/deploy/compose.coolify.yaml
   interpolates `ghcr.io/u2giants/theoracle-brain:${BRAIN_IMAGE_TAG:-latest}`.
2. **`ai-task-gates check --before deployment`** → `unknown action: deployment`.
   The action name is `deploy` (valid actions: review, code-only-review, pr-wait,
   ship, deploy, database, database-read, infrastructure, production,
   shared-db-promotion, application-workflow). And `deploy` is not a gate for the
   `code` class: redeclare with `ai-task-gates start --class deployment` (the work
   outgrew the class), then `check --before deploy` passes.
3. **`gh pr create` with a long body** failed twice with GraphQL `Something went
   wrong` / 502 (GitHub flaky ~11:12 AM EST). Created the PR with a short body and
   posted the full text as a PR comment instead:
   https://github.com/u2giants/theoracle/pull/451#issuecomment-6662964630
4. **PowerShell quoting through ssh** mangled inline scripts (`sed`/`python3 -c`
   one-liners, `&&` is not PowerShell 5.1, `tail`/`Select-Object` mixups). Fix:
   write scripts to a local temp file, `scp` them, then `bash` them — exactly the
   warning in the coordinator handoff.
5. **Partial repo copy to the test host** (only `apps/brain`) made 4 unrelated
   tests fail (`test_deploy.py`, `test_resolve.py`) because they read repo-root
   files (`docs/verification/...`, `.github/workflows/...`). Copy the whole tree
   (excluding `.git`/`node_modules`/`.venv`) and the full suite passes 209/209.
6. **A 2-entity test fixture cluster could no longer stand alone** — the fix's
   guarantee makes size-2 groups impossible, so `test_communities.py`'s second
   cluster grew from a pair to a trio (vendor/customer/factory). The old assertion
   ("the pair stays its own community") had been asserting the defect.
7. **`GET /api/v1/applications/{uuid}/envs` returns plaintext secret values**
   (DATABASE_URL, service-role key, API keys) in `real_value` even though the app
   sets `redact_all_env_values_in_logs`. They landed in this session's local
   transcript via one diagnostic call. Values were not repeated anywhere and are
   not rotated (exposure is local-only per standing rule). **Parse this endpoint
   narrowly** (filter to the one key you need) — never print the raw response.

## 5. Root causes and key findings

- **The whole 607 is evidence-less entities, not a merge-logic bug.**
  `cmap.mention` has `ON DELETE CASCADE` from `cmap.chunk` (which cascades from
  `cmap.source`), but `cmap.entity` has no such link — so `DELETE /sources/{id}`
  (https://github.com/u2giants/theoracle/blob/5783e7ecdfb6dac94c2536595225e1e66d385a6f/apps/brain/brain/api/sources.py#L445-L467)
  deletes mentions and leaves the entities behind. 405 such orphans exist in
  production right now (all still have stale `mention_count`/`source_count` > 0
  and `entity_alias` rows, so re-ingesting their documents re-links them).
  Entities with zero mention rows have **no edges** (relations hang off mentions)
  and **no sources** (`_entity_sources` joins mentions), so neither the
  edge-neighbour nor the source-sharing merge can reach them — they stayed
  singletons. A simulation of the merge loop over live data folds every entity
  that has any link (1366 entities into 135 groups, none under 3); the only stuck
  smalls are exactly the no-mention entities. L1 inherits smalls one-for-one
  (Leiden over L0 groups).
- **The fix** is a fold pass after the merge loop —
  https://github.com/u2giants/theoracle/blob/5783e7ecdfb6dac94c2536595225e1e66d385a6f/apps/brain/brain/graph/communities.py#L180-L356
  (`_fold_leftovers`): leftovers merge into the most similar community (edge
  weight, shared sources, then embedding similarity, preferring targets under
  `MAX_MERGED_COMMUNITY` = 60), and any community over `MAX_COMMUNITY` = 150
  (line 40) is peeled into bounded pieces. `_level0_membership` (lines 82–178)
  calls it at the end. L1 needs no new code: every L1 group holds at least one L0
  community and the existing packing caps it at 150. `_entity_vectors`
  (lines 358–366) loads the embeddings the fold ranks by.
- **`_existing_reports` re-tags old rows** (it keys on `(level, entity_set)` across
  ALL graph versions and bumps `graph_version` on reuse). That is why a re-run of
  unchanged code finishes in a minute and why old singleton rows show up under a
  new `graph_version` — read `created_at` to tell reused rows from new ones.
- **`graph_version` is bumped by the `project` job** (`run_project` →
  `_record_version`), and `handle_project` enqueues `communities`. Queue one
  `project` job to re-cluster end to end. A `communities` job alone re-tags rows
  with the CURRENT max version and pollutes the map view.
- **Verified test/infra details:** full brain suite 209/209 green on the test host
  with `pgvector/pgvector:pg16` + `falkordb/falkordb:v4.20.7` containers
  (created as `task67-pg`/`task67-falkor`, removed after use). `uv` is at
  `~/.local/bin/uv` on the test host; pip is PEP 668-locked
  (`python3 -m pip install --target /tmp/pylibs ...`, then `PYTHONPATH=/tmp/pylibs`).

## 6. Exact next steps

1. **Confirm live image with the coordinator.** Ask the step-14 coordinator
   whether its deploy `ehbllrkc668qmqr0sepmaxbt` (started ~11:32 AM EST 2026-11-05)
   landed before or after the `BRAIN_IMAGE_TAG` correction (11:34:35 AM EST), and
   get its all-clear for prod jobs. If it pulled the old image, one redeploy is
   needed (env is already correct). You'll know it worked when
   `GET /api/v1/applications/uge6pfm4qapktivto4981mtg` shows a deployment whose
   `commit` is `5783e7ecdfb6dac94c2536595225e1e66d385a6f` and status `finished`.
2. **Queue the re-cluster.** With `cmap.job` showing no rows in
   (`running`,`queued`), insert one `project` job (`INSERT INTO cmap.job (kind,
   payload) VALUES ('project', '{}'::jsonb)` via psycopg from the test host, pooler
   URL piped on stdin from 1Password — see §8). It chains `communities`
   automatically. Expect minutes-to-tens-of-minutes: the fold produces ~34 L0 +
   ~26 L1 + 1 L2 groups whose entity sets are new, so the frontier writes ~61 fresh
   reports. You'll know it worked when the `communities` job state is `done` and
   `cmap.graph_version` has a new max.
3. **Verify the stored rows** (this is the `- [ ] live proof` box on #437):
   ```sql
   SELECT level, count(*), min(cardinality(entity_ids)), max(cardinality(entity_ids)),
          count(*) FILTER (WHERE cardinality(entity_ids) < 3) AS below_3,
          count(*) FILTER (WHERE cardinality(entity_ids) > 150) AS above_150
   FROM cmap.community WHERE graph_version = <new max> GROUP BY level ORDER BY level;
   ```
   You'll know it worked when L0 and L1 both show `below_3 = 0`, `above_150 = 0`,
   and min ≥ 3 (expected: L0 ≈ 34 groups sizes 3–94, L1 ≈ 26 groups sizes 3–149).
4. **Post the result on #437** (comment with the query and counts, signed
   `Posted by MiMo chat <session id> on <machine>`), tick the `- [ ] live proof`
   box in
   https://github.com/u2giants/theoracle/issues/437#issuecomment-6663588332,
   and close #437. You'll know it worked when the issue is closed with the
   distribution visible.
5. **Retire this handoff** in the same commit that finishes the above, under the
   successor rule (all obligations above carried forward and proven).

Follow-ups NOT started (out of this task's scope, do not do them in passing):
- `delete_source` should also delete entities left with no mentions (the smoke
  cleanup already does exactly this —
  https://github.com/u2giants/theoracle/blob/5783e7ecdfb6dac94c2536595225e1e66d385a6f/apps/brain/brain/smoke.py#L60-L70).
  That is what created the 405 orphans. A new issue + PR is the right shape.
- The 405 orphans' `mention_count`/`source_count` are stale (claim mentions that
  do not exist); `_refresh_counts` only updates entities a run touches.

## 7. Constraints and gotchas in force

- **Public repo** (`u2giants/theoracle`): no secrets, no LAN IPs, no Supabase
  project references in any commit, issue or PR. This file obeys that — secrets
  live only in 1Password, referenced by vault/item/field.
- **Never push to `main`.** Branch + PR + `gh pr merge --squash --admin` after
  checks pass. CI-required: `brain tests`, `company map browser test`,
  `brain image`, `build`, `verify`. The `fix / prepare` and `review / review`
  checks are advisory only (owner ruling 2026-10-29: reviews never block).
- **Sign every GitHub post** with `Posted by MiMo chat <session id> on <machine>`.
- **Times in EST (America/New_York)** in anything human-facing.
- **Deploy discipline:** `ai-task-gates start --class deployment` then
  `ai-task-gates check --before deploy` before any deploy; never redeploy while
  `cmap.job` has rows in (`running`,`queued`); env PATCH (single-object
  `{key,value,is_preview,is_multiline,is_literal}`) must land BEFORE the deploy;
  deploy trigger is `POST http://hetz:8000/api/v1/deploy?uuid=uge6pfm4qapktivto4981mtg`
  with the Coolify token in `Authorization: Bearer`. The coordinator may hold
  deploy sequencing — obey its all-clear notices.
- **Canonical checkout is landing-only**; do the work in your own worktree.
- **Commit identity** must be `Albert Hazan <u2giants@users.noreply.github.com>`
  (verify with `git var GIT_COMMITTER_IDENT` before the first commit).

## 8. Access and environment

- `gh` authenticated as `u2giants` on this machine (ah-desktop). Git over HTTPS.
- 1Password MCP (vault `vibe_coding`) is connected. Known items (values never
  written down):
  - Prod pooler URL: item `qcuyabwseaptvuzvtjejffi2ou`, field `oracle_session_pooler`
    (the `password` field of that item is an IPv6-only direct URL — unusable).
    Pipe it on stdin to psycopg from the test host; never put it in argv.
  - Coolify deploy key (release sessions only, Coolify token id 41): item
    `u3aqw63jqnkmnziip3gp5hwb5m`, field `credential`. Never copy it to shared
    machines; call `http://hetz:8000` from ah-desktop with the token injected via
    env (1Password `op_run`), not in the command line.
  - Brain API token: item `4lm6bpl7bc25lqne4meumwcd2a`, field `BRAIN_SHARED_TOKEN`
    (not needed for this task; `/health` needs no auth).
- Test host: `ssh edge-dev3`. Own test containers only (`task67-*` names), remove
  after use; never reuse `brain2-test-pg` / `brain2-test-falkordb`. psycopg:
  `python3 -m pip install --target /tmp/pylibs 'psycopg[binary]'` then
  `PYTHONPATH=/tmp/pylibs python3 …`. `uv` is installed for the test host's user —
  add that user's local bin directory to `PATH` before calling it.
- Coolify API: `http://hetz:8000/api/v1/...` (reachable from ah-desktop and
  edge-dev3; 401 without the token). **`GET .../envs` returns plaintext secret
  values — parse narrowly and never print the raw body** (see §4.7).
- Prod DB is schema `cmap` on the Supabase project "theoracle" (the project ref
  must never appear in the repo).

## 9. Open questions and risks

- **Deploy sequencing (2026-11-05 11:41 AM EST):** the coordinator's deploy
  `ehbllrkc668qmqr0sepmaxbt` may have pulled the stale pin (it started before the
  11:34:35 AM EST correction). If so, the live brain is still the old code even
  though `BRAIN_IMAGE_TAG` is now correct — one redeploy fixes it. Confirm before
  claiming anything is live. Risk if unknown: a session could close #437 against
  old-code rows.
- **Report-reuse gotcha:** `run_communities` reuses any stored report whose
  `(level, entity set)` matches, and re-tags its `graph_version`. A re-cluster
  over the SAME grouping therefore proves nothing (it re-tags old rows in under a
  minute). The fold changes the entity sets, so a real re-cluster writes new rows
  — but read `created_at` to distinguish reused from new when verifying.
- **The corpus is moving** (entity count grew 1771 → 1787 during this session
  while the coordinator's ingest ran). The exact counts in a future re-cluster may
  differ slightly from §3; the bound [3, 150] is what must hold.
- **Orphan-entity hygiene** (§6 follow-ups) is unowned; without it every source
  deletion creates more evidence-less entities. The fold absorbs them, so it is
  not urgent, but the entity table keeps drifting from its mention evidence.
