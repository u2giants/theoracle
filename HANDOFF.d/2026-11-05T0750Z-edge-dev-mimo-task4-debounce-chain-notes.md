---
issue: 415
status: OPEN
owner: mimo/task4-debounce-chain
---

# Task 4 wrap-up notes — chain debounce (#415) deferred items and ops learnings

Written 2026-11-05 ~2:50 AM EST (America/New_York) by the MiMo task-4 nested
session (parent coordinator baton
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0140Z-edge-dev3-claude-close-nested-company-map.md
§6 task 4). Machine edge-dev. The task itself is COMPLETE (PR merged, deployed,
live proof on the issue); this file carries only what wrap-up deferred or
learned. `issue: 415` is closed — this file is a SUCCESSOR REVIEW candidate and
is retired once §6 items are absorbed.

## 0. Business decisions only the owner can make

None — nothing in this workstream needs the owner. Everything below is technical
and owned by AI sessions.

Settled, do NOT re-ask:
- 2026-11-05 task 4 done-when and deploy order came from the owner-approved
  close-nested baton (tasks 1–4 deploy the live brain one at a time). Proven
  live and posted on
  https://github.com/u2giants/theoracle/issues/415#issuecomment-6652504195 .

## 1. What this application is

The Oracle (`u2giants/theoracle`, PUBLIC repo) is an evidence-backed company
knowledge graph. The brain (`apps/brain`, FastAPI + one worker thread) runs on
Coolify app `oracle-brain` (https://oracle-brain.designflow.app), Postgres
schema `cmap` on the project's own Supabase project, FalkorDB graph `company`.
Web app on Vercel. Sources (documents, Teams interview answers) flow through
jobs in `cmap.job`: read_source → classify_extract → relations → resolve →
project → communities → recommend.

## 2. What we set out to do this session, and why

Issue https://github.com/u2giants/theoracle/issues/415 : every new source ran
the full resolve→project→communities chain immediately, so a burst of Teams
answers paid for several full communities passes (a full pass runs many
minutes) and kept closing the redeploy window. Goal: debounce/batch the chain
so a burst runs it once. Done-when: several sources ingested within a short
window produce one resolve and one communities run, shown in a test, and the
Map still updates within a stated bound; proven live with two sources arriving
close together.

## 3. Current state — what is true right now

COMPLETE and verified live (all times EST 2026-11-05):
- PR https://github.com/u2giants/theoracle/pull/444 merged (squash) as
  https://github.com/u2giants/theoracle/commit/faa3482ff2b00ea80bf40260950d73077ac69e39
  . Issue #415 closed.
- Live proof on the issue (link in §0): two transcript sources 5 s apart
  (2:17:09 / 2:17:14) produced ONE resolve (queued 2:17:49, hold pushed by the
  second relations at 2:18:39 to 2:23:39) and ONE communities run (done
  2:33:18); Map went graph_version 20 → 21 and `/communities` serves 435 L1
  communities at v21.
- Deployment: migration `009_chain_debounce.sql` applied to the prod cmap
  schema; brain image tag = the merge SHA above, Coolify deployment
  `kydfrm8lsy4pvdndypacwopv` finished; `/health` ok/db/graph all true.
- Tests: `apps/brain/tests/test_chain_debounce.py` (6 tests, incl. the
  done-when test) — full brain suite 206 passed on a dedicated edge-dev3 test
  pair.

Implementation (all on `main`):
- https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/009_chain_debounce.sql
  adds `cmap.job.run_after`.
- https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/worker.py
  claims only `run_after <= now()`.
- https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py
  `_enqueue_resolve` holds one resolve `DEBOUNCE_SECONDS` (300 s) past the last
  source, capped at `MAX_DELAY_SECONDS` (900 s) from the first source.
- https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/map.py
  `POST /map/rebuild` wakes the hold immediately.

Nothing of the task is half-done.

## 4. Everything we tried that did NOT work

1. Coolify env update `PATCH /applications/<uuid>/envs` with a LIST of
   `{key,value}` (and with full-field list) returns **422**. The working shape
   is a single OBJECT `{key,value,is_preview,is_multiline,is_literal}` (201).
   Source of the list form: an older handoff's "bulk" note — do not repeat.
2. The first deploy trigger was sent BEFORE the env PATCH succeeded, so Coolify
   queued a redeploy of the OLD image tag (deployment `0h7fmk88pxdsqttauxzsypza`)
   . Fixed by patching the env (object form) then `POST /applications/<uuid>/start`
   again (`kydfrm8lsy4pvdndypacwopv`). This matches the "mystery redeploy with
   old image tag" note from the prior session — likely the same cause there.
3. `python -m brain.migrate` against the prod pooler run inside a 2-minute MCP
   call timed out before the DDL landed (connection latency to the pooler
   spiked to tens of seconds). Re-run detached (spawn with inherited env,
   poll a local status file) — idempotent, so retrying is safe.
4. `POST /sources/transcript` dedupes identical bytes by sha256 and returns
   `{"id": existing, "duplicate": true}` with 200 — three "sources" with the
   same text created ONE source. Burst tests must vary the text.
5. Postgres has no `min(boolean)`; use `bool_and` for boolean aggregates.
6. `bin/ai-doc-safety` on the whole tree fails on PRE-EXISTING debt (legacy
   handoffs, DECISIONS.md link targets, `pnpm-lock.yaml` "finalizationregistry"
   token) — not caused by this change; do not chase them in a feature PR.

## 5. Root causes and key findings

- The chain choke point is `_enqueue_resolve` at the end of `handle_relations`
  (one call per source). Coalescing on `WHERE NOT EXISTS queued` alone never
  helped: the worker claims within 2 s, so the second source's relations found
  the first resolve already *running* and queued another. The fix must hold the
  job (future `run_after`) and push the hold on each new source.
- Stated bound (also in the PR and issue comment): the chain starts 5 min after
  the last source's relations complete (15 min from the first source of a batch
  at the latest); the Map reflects a burst after that hold plus one chain run.
- **Coolify `GET /applications/<uuid>/envs` returns every env value in CLEARTEXT,
  including DATABASE_URL.** Printing that response leaks secrets into the
  session transcript. Never print env values; print only keys/uuids. (One such
  echo happened this session; the value is a local-only exposure of an existing
  1Password secret, left unrotated per the standing no-rotation rule.)
- Plan drift for the coordinator's #240 drift process:
  https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md#L183
  quotes the old worker claim SQL (`state='queued' ... LIMIT 1`); it now also
  filters `run_after <= now()`, and the resolve→project→communities chain is
  debounced (see §3). The plan's step-6/7/8 chain prose implies one chain run
  per source; that is no longer literal. Not fixed here (wrap-up scope freeze);
  route through the existing plan-drift report.

## 6. Exact next steps

1. Absorb §5's plan-drift item into the next plan drift report on
   https://github.com/u2giants/theoracle/issues/240 (the coordinator's existing
   process). You'll know it worked when the report mentions the debounced chain
   and the `run_after` claim filter.
2. Remove my test containers on the test-services host (they are mine and no
   longer needed): `docker rm -f t4-pg t4-falkor`. You'll know it worked when
   `docker ps` shows neither name.
3. Retire this file (successor rule) in the commit that lands step 1 or 2 —
   issue #415 is already closed and the task outcome is verified; carry any
   still-open obligation forward first. You'll know it worked when `HANDOFF.d/`
   has no `task4-debounce` file and `ai-housekeeping` no longer lists it.

## 7. Constraints and gotchas in force

- Public repo: no LAN IPs, no project refs, no secrets anywhere. Times in EST.
- Never push directly to `main`; branch + PR + `gh pr merge --squash --admin`.
- Never redeploy the brain while `cmap.job` has `running`/`queued` rows
  (`select kind,state from cmap.job where state in ('running','queued')`).
- The brain does NOT migrate on startup: run `python -m brain.migrate` against
  the target DATABASE_URL before shipping code that needs a new schema.
- Coolify PATCH env = single object form (see §4.1). Deploy =
  `POST /applications/<uuid>/start`. Only one child deploys at a time (baton §6).
- OpenRouter `limit_remaining` (GET /api/v1/key) must stay above $5 (it was
  $19.29 at ~2:00 AM EST 2026-11-05).

## 8. Access and environment

- GitHub `gh` authenticated as `u2giants`; commit identity
  `Albert Hazan <u2giants@users.noreply.github.com>`.
- 1Password MCP (`op_run`), vault `vibe_coding`; secrets only as `op://` refs in
  env values: Supabase prod `qcuyabwseaptvuzvtjejffi2ou` field
  `oracle_session_pooler` (prod cmap queries work from this machine and the
  test-services host; the direct-URL field is IPv6-only), OpenRouter
  `62ieeyycs4ierflalbbbt5pq5i` field `OPENROUTER_API_KEY`, brain shared token
  `4lm6bpl7bc25lqne4meumwcd2a` field `BRAIN_SHARED_TOKEN`, Coolify deploy token
  `u3aqw63jqnkmnziip3gp5hwb5m` field `credential`.
- Brain admin API: `x-brain-token` + `x-user-id` (admin auth user id used:
  `751efc6f-b030-43cf-9f22-8e82ac389771`). Map read: `GET /communities?level=1`.
- Coolify API `http://hetz:8000/api/v1`, app uuid `uge6pfm4qapktivto4981mtg`.
- Test-services host (ssh `edge-dev3`): my leftover containers `t4-pg`
  (Postgres 56811, db `brain_t4`) and `t4-falkor` (FalkorDB 56812) — see §6.2.
- ai-devops bash tools run under Git for Windows bash (bare `bash` is the WSL
  stub); `ai-pr-wait` lives in the ai-devops checkout's `bin/`.

## 9. Open questions and risks

- Two transcript sources titled "Debounce proof 2026-11-05 (a)/(b)" (ids
  `83a71b89-79a5-4417-96ec-c92a59cdef50`, `a4ad84eb-cc01-4941-a3e4-d33be6526bc2`)
  now live in the prod corpus by design (the live proof). They add no business
  claims. If Albert wants them gone, deleting a source re-triggers the chain via
  `POST`-delete `project` — expected, not a bug.
- A continuous drip of sources faster than `DEBOUNCE_SECONDS` is held to the
  `MAX_DELAY_SECONDS` cap (15 min from the batch's first source), so the Map is
  never starved; the trade-off is one chain run per 15 minutes of nonstop
  ingest. Chosen deliberately (2026-11-05).
- `GET /envs` cleartext echo (§5) is a standing footgun for every future deploy
  session; consider a tooling guard later (not opened as an issue — coordinator's
  call).

## Self-audit

1. Brand-new developer can continue: yes — §3 proves the task landed, §6 has the
   three remaining actions with gates, §4/§5 carry every trap.
2. As effective as me: yes — §4 failures, §5 root causes, §8 access are complete.
3. Every detail: background (§1), goal (§2), state+evidence (§3), failures (§4),
   findings (§5), actions (§6), constraints (§7), access (§8), risks (§9).
4. Owner read of §0: §0 says explicitly nothing needs the owner; the sweep found
   no business decision hiding in §1–§9 (the "want the proof sources deleted?"
   line in §9 is optional cleanup owned by whoever acts on §9, not a gate).
