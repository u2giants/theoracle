# R2 production gate hard stop

Status: **OPEN. The sole authorized production gate scored 19/30. A new owner decision is required before further R2 reader work.**

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed business knowledge system. Employees
upload company documents and ask questions. Workers turn those sources into duties, processes,
rules, claims, and business-model records with exact source proof. The repo is
`C:\repos\oracle`, GitHub `u2giants/theoracle`, branch `main`. The web app is
`https://oracle.designflow.app`. Workers run in Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn`. Production data is in Supabase project
`eqccjfbyrywsqkxxpjvg`.

## 2. What we set out to do this session, and why

The R2 source-span inventory reader had passed an unchanged local support gate at 28/30. Albert
wants the application ready to go live after five months of work, so on 2026-08-11 he explicitly
authorized worker deployment and exactly one frozen production gate. The purpose was to learn
whether the real production model could turn the pinned responsibility document into at least 27 of
30 known duties without changing the fixture, matcher, score, budgets, model route, or safety locks.

## 3. Current state

- Code commit `62330bdb0b477abb373fa1d155b104cee45a8b66` and pre-release docs commit
  `9dcfd6072677b9a12e8a320f48e5c316d1099b6b` are pushed to `main`. Their GitHub Actions runs passed.
- Trigger worker `20260811.1` deployed successfully as deployment `725f1ru9`, with 25 tasks, worker
  id `worker_cmsox4rmu41v50klhk5g84pdy`, and content hash
  `f3d9149938c31bcb7a3d334ede276137`.
- Exactly one frozen gate ran as Trigger run `run_06fv3keiq77bp0gpum352rls01` against fixture SHA
  `398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`.
- Disposable document `cc005035-2251-4dbe-ba1a-8913ad3ea912` produced map
  `37a8fc62-23e4-46b7-8464-d1c784dc73cd`. The source-workflow job
  `df7e8cd3-988d-499d-a831-9c04390e4a94` completed with no error or retry. The map finalized
  `degraded` at `2026-08-11T17:19:37.040Z`.
- The unchanged `field-aware-v3` matcher scored the map **19/30 (63.3%)**, below the frozen 27/30
  gate. The `<=23` rule is a binding hard stop.
- The map held 93 responsibility records, 404 kept elements, and 74 dropped elements. Reader use was
  21/40 calls, 63,015/500,000 input tokens, 1/1 repair, and $0.350742/$10. Post-pass use was 1/1
  quote repair and 2/5 omission retries, with one retry in each of two chunks.
- The 11 misses were: submit concepts into licensor systems; download PPS photos; rename PPS files
  by SKU; review PPS photos against tech packs; submit PPS photos in licensor portals; fill out a
  Letter of Guarantee; request a contractual sample exemption; request factory audits before
  approval expiration; download style guides to the server; submit quarterly royalty reports; and
  provide assets to partners.
- Merge, apply, and serving stayed false. `business_objects`, `business_object_versions`, and
  `business_model_changes` remained zero. Nothing was promoted into the live business model.
- This handoff and the plan/eval updates are not yet committed or pushed at the time this file is
  created. The next agent must verify git state rather than assume they landed.

## 4. Everything we tried that did NOT work

1. The earlier production architecture and model bake-off did not solve responsibility recall.
   Prior maps scored 11 or 12 out of 30. Those failures led to the source-span inventory design.
2. The first local inventory result looked strong only because it used a hidden owner fallback that
   borrowed text outside the model-visible source span. Removing that invalid behavior dropped the
   honest local result to 16/30.
3. Two bounded source-grounded corrections raised honest local support to 26/30 and then 28/30.
   This was useful but not enough. It proved a source span could support an answer, not that the
   live model would write the answer correctly.
4. The sole production run produced 93 duties but only 19 matched the 30 expected duties. More
   output did not mean better recall. Several near-matches had thin or conflicting field wording.
   Examples: the PPS download object omitted `PPS`; PPS portal submission carried exception text
   that created a conflict; `provides` did not satisfy the expected `provide`; and concept
   submission covered only two of three required object terms.
5. A final read-only database audit first failed because a copied 1Password item id had two wrong
   characters. The correct current production item id is documented by title in section 8. The
   audit then passed. No production data or configuration changed.

## 5. Root causes and key findings

- The main gap is now between source visibility and live completion. The local verifier asks whether
  `responsibilityCompletionRequest(seed).sourceSpan` contains enough evidence for the expected
  answer. It does not make the production model generate that answer.
- The live model had enough total budget. It used about half the call limit, one eighth of the token
  limit, and far below the cost limit. Raising budgets is not justified by this evidence.
- The live output included many duties but still missed or misworded 11 known ones. The next
  diagnosis must trace each missed answer to its seed, completion request, model proposal, matching
  result, and final stored record. Do not infer that all 11 share one cause.
- The frozen matcher and answer key exposed real field-quality problems. Do not weaken them.
- Safety controls worked. Merge, apply, and serving stayed off, and all three protected table counts
  stayed zero.
- Durable evidence is in `evals/r2-responsibilities.md` and map
  `37a8fc62-23e4-46b7-8464-d1c784dc73cd`. The governing plan is
  `plan_r2_source_span_inventory_reader.md`.

## 6. Exact next steps

1. Confirm Albert's new choice before further reader work. Recommend authorizing only a read-only
   residual diagnosis. Success means the chat contains explicit approval and no code or run occurs.
2. If authorized, read the production map's `validation_json`, its 93 final responsibility records,
   and the frozen 30-row answer key. For each of the 11 misses, record the exact inventory seed,
   model-visible completion request, dispatched batch, returned proposal, deterministic matching
   decision, final record if any, and matcher rejection. Success means every miss has one evidenced
   failure point and no answer-key terms are inserted into runtime code.
3. Group the 11 findings only after the row-level trace is complete. Separate source inventory,
   dispatch, model omission, proposal matching, field canonicalization, quote validation, and frozen
   matcher causes. Success means each group cites row ids and stored production facts.
4. Present one bounded architecture recommendation to Albert. It must name the exact generic seam,
   tests, expected rows, regression risk, and a local-only stop gate. Success means Albert can approve
   or reject one clear change without authorizing production.
5. Do not implement until Albert separately authorizes that exact correction. If authorized, work
   locally first with unchanged fixture, matcher, threshold, budgets, model route, and safety flags.
   Success means all existing tests pass and the new test proves the generic failure mechanism.
6. Do not deploy or run another production gate under the current plan. Any future live test needs a
   new written plan and explicit owner authorization after independent review. Success means there is
   no second run for worker `20260811.1`.

## 7. Constraints and gotchas in force

- No second production gate or model bake-off.
- No production deployment, DB mutation, schema change, secret change, or direct live edit.
- No source-prefix owner lookup, earlier heading, nearby duty, answer-key alias, or fixture term may
  be borrowed into a completion request.
- Do not weaken `field-aware-v3`, change the 27/30 threshold, raise budgets, or change model routes.
- Keep business-model merge, apply, and serving off.
- Preserve unrelated untracked `.ai`, screenshot, and Playwright files in the working tree.
- Work on `main`. Before any commit, verify Albert's Git identity and stage exact paths only.
- There are nine open handoff files as of this closeout, above the limit of five. Do not delete or
  edit another session's handoff. Albert should schedule a separate handoff-retention cleanup.

## 8. Access and environment

- Machine: Windows 11 host `al8960ofc`; repo `C:\repos\oracle`; PowerShell; branch `main`.
- GitHub CLI is authenticated. Production and shared cloud remain read-only unless Albert names an
  exact allowed action in the current chat.
- Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`. Deployment evidence URL:
  `https://cloud.trigger.dev/projects/v3/proj_wgpzsvhmsopqhvwqaycn/deployments/725f1ru9`.
- Secrets live only in 1Password vault `vibe_coding`. The current DB item is titled
  `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)`. Use its
  `oracle_session_pooler` field. Never print or commit the value. Serialize all 1Password reads.
- Supabase project `eqccjfbyrywsqkxxpjvg` is the current Oracle production database.
- The frozen fixture is on the licensed private source path described in the governing plan. Do not
  copy its contents or licensed terms to an outside model or public repo.

## 9. Open questions and risks

- Owner decision required: authorize a read-only row-by-row diagnosis, or stop R2 work.
- The biggest risk is treating 28/30 local support as proof of live understanding. Production showed
  it is not.
- Another risk is tuning to 11 answer-key phrases. Any correction must be generic and source-bound.
- The document-ingestion parent job was still running downstream with no error when the map was
  scored. The source-workflow job and map were terminal, so this did not affect the frozen score.
- Decision dated 2026-08-11: the 19/30 result is honest and binding. No score exception was granted.

## Handoff self-audit

Passed all five checks. A new developer can identify the application, exact release and production
evidence, failed approaches, root cause boundary, safety state, required owner decision, and each
next step without prior chat context. Failed attempts and their reasons are included. Every next
step has a success test. All ids, systems, paths, and limits used here are explained.
