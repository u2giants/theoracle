---
issue: 4
status: BLOCKED
owner: codex/r2-bounded-correction
---

# R2 bounded correction is implemented; licensed gates and the one production run must execute on al8960ofc

## 0. Decisions only the owner can make

**Blocking security decision outside the R2 score:** On 2026-09-08 a read-only Windows process inventory unexpectedly printed the bearer tokens for `mcp.designflow.app` and `nas-mcp.designflow.app` into the Codex conversation. Treat both tokens as compromised. Albert must explicitly authorize rotation; recommendation: authorize rotation of both now, then update every configured reference and verify both MCP endpoints before retiring the old values. This does not block the offline R2 code, but it blocks claiming the credential incident remediated.

No R2 decision remains. Albert explicitly funded exactly one tightly bounded correction cycle on 2026-09-08. That settled one implementation, one live contract probe, one worker deployment, and exactly one fresh production run. Do not re-ask. It did not authorize a retry, a second production run, secret rotation, migration, weaker evidence rules, or broader production changes.

Already settled — do not re-ask: frozen answer key `licensed-team-responsibilities-v1`, matcher `field-aware-v3`, threshold 27/30, negative controls 16/24/26, route and budgets, disabled business-model merge/apply/serving, and preservation of every map.

## 1. What this application is

The Oracle turns POP Creations and Spruce Line documents into evidence-backed company knowledge. Employees ask questions and upload documents; workers extract source-bound claims and workflow maps; administrators review the results. Repository `u2giants/theoracle` is a TypeScript/pnpm monorepo. The web app is `https://oracle.designflow.app`, workers run in Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`, and production data/auth live in Supabase project `eqccjfbyrywsqkxxpjvg`.

R2 is the macro-first program's responsibility-reader quality gate. Production currently serves map `224ca68d-82c8-4954-ac65-59b02db00546` at 23/30. The required threshold is 27/30. R3-R10 remain blocked until R2 passes honestly.

## 2. What this session set out to do, and why

Albert funded one bounded cycle to recover the remaining duties without weakening the validator or scorer. The prior attempt added reason-code explanations to the global completion system prompt; it broke the model's one-record-per-seed contract, fell to 13/30, lost seven preserved rows, and was reverted. The fixed design keeps that global prompt byte-for-byte unchanged and carries a small correction brief only inside each rejected seed's dynamic request.

## 3. Current state — what is true now

Implementation commit `c6d4dd1` is pushed on branch `codex/r2-bounded-correction` and tracked by GitHub issue #4. It is not on `main`, not deployed, and no production map was triggered.

Changed code:

- `apps/workers/src/lib/responsibility-reader.ts`: attaches capped, deduplicated rejection reasons and source-bound guidance to one seed; maximum six reasons of 160 characters.
- `apps/workers/src/lib/source-workflow-read.ts`: supplies feedback only for `validation_rejected` outcomes to the existing late pass. Provider failures and accepted outcomes receive none. The global system prompt is unchanged.
- `apps/workers/src/__verify__/r2-responsibility-reader.ts`: locks normalization, per-seed guidance, packing, production wiring, frozen v1 system prompt, and the existing 19/30/negative-control boundary.
- `apps/workers/src/__verify__/r2-completion-contract-live.ts`: the eight-seed live probe now exercises the new feedback path rather than the unchanged first-attempt path.
- `plan_r2_completion_recovery_cycle.md`: records Albert's authorization, the code state, and the host block in G10-G12.

Passing on EDGE-DEV: worker/AI/engine typechecks; `verify:r2-responsibilities`; `verify:source-workflow-read`; `verify:r0-reader-validator`; document-ingestion fallback; lull dispatch; conversation windowing; AI R2/workflow-read; engine macro/macro-first/R1 cross-shape; and `git diff --check`. The focused verifier reproduced 19/30, kept negative controls 16/24/26 unmatched, and passed 16/16 final-record cases.

Not run because EDGE-DEV lacks the licensed `Z:` fixture: pinned inventory, production replay, and the live eight-seed contract probe. Deployment and the production run were therefore correctly not attempted. The required execution host is `al8960ofc`.

The 1Password field `openai_chatGPT_Oracle` on item `3onekcbg3dxnazpnt36d4yzfcq` was verified by shape to include its full `sk-proj-` prefix. Its stale note was corrected and tags were added without revealing or rotating the credential. Use `op://vibe_coding/3onekcbg3dxnazpnt36d4yzfcq/openai_chatGPT_Oracle` only through protected injection.

## 4. Everything tried that did not work

The first dependency install included `--no-progress`, which this pnpm version rejects. It was rerun successfully with `--silent --frozen-lockfile`; do not repeat the invalid flag.

The production phase cannot run on EDGE-DEV: hostname verification returned `edge-dev` and the exact licensed fixture path was absent. The production plan expressly forbids skipping this gate. Do not copy licensed data to this machine, deploy from here, or treat the non-licensed suite as equivalent proof.

A process inventory intended only to detect competing test runs printed full command lines, including two MCP bearer tokens. A subsequent path-only search showed MCP configuration and historical backups/session records across `.config` and `.codex`; no file was changed or deleted. Do not run broad command-line inventories that display arguments. Rotation is the only remediation; deletion or redaction of local history alone would not retire exposed credentials.

The 2026-08-27 global-prompt reason-code approach remains a binding dead end. It produced 192 `provider_failed` outcomes and 13/30. Do not restore commit `0a1c396` wholesale or edit `RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT`.

## 5. Root causes and key findings

The remaining R2 failures are not capacity failures. The 23/30 run had budget left; rejected candidates failed legitimate fidelity rules. An identical late retry is spent because it asks the same question. The useful difference is seed-local validator feedback while leaving the global contract intact.

Only `validation_rejected` outcomes should carry correction feedback. A provider failure is not an answer defect and must not be turned into content guidance. Multiple validator outcomes for one seed are combined, deduplicated, truncated, and token-estimated before packing.

The live contract probe must include feedback on all eight sampled seeds. Otherwise it would only prove the old first-attempt request still works and could miss a failure in the new path.

## 6. Exact next steps

1. On `al8960ofc`, create a clean current-upstream worktree for `origin/codex/r2-bounded-correction`; verify `hostname` and the exact fixture `Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`. Gate: hostname is `al8960ofc`, branch head is `c6d4dd1` or its reviewed successor, and the fixture exists.
2. Re-read `plan_r2_completion_recovery_cycle.md` G10-G12 and `plan_r2_fresh_production_gate.md` sections 8-11. Re-resolve GitHub main/head, current CI, production settings, document `cc005035-2251-4dbe-ba1a-8913ad3ea912`, and active map `224ca68d-82c8-4954-ac65-59b02db00546`. Gate: every frozen input matches; any drift stops the cycle.
3. Run all 16 commands in `plan_r2_fresh_production_gate.md` section 10. Inject `R2_REPLAY_DATABASE_URL` from 1Password item `qcuyabwseaptvuzvtjejffi2ou`, field `password`; never reveal it. Gate: pinned support remains 28/30 with rows 16/26 unsupported; replay remains 19 baseline / 21 corrected with empty regression lists; every command exits 0.
4. Run `pnpm --filter @oracle/workers verify:r2-completion-contract-live` with the licensed fixture, database URL, and Oracle OpenAI key injected from the two named 1Password items. Gate: eight requested, eight returned, zero contract failures. Any failure stops the cycle before deployment.
5. Review the exact branch diff and merge it to `main` only after steps 1-4 pass; verify CI for the exact head. Gate: `main`, CI, and reviewed code agree, with `RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT` unchanged.
6. Deploy the worker exactly once to Trigger.dev production and confirm `source-workflow-read` is registered from the exact merged code. Gate: record the version/deployment ID; any deploy failure stops without a trigger.
7. Trigger exactly one production task with payload `{documentId: "cc005035-2251-4dbe-ba1a-8913ad3ea912", force: true}`, a new cycle-specific idempotency key, and `maxAttempts: 1`. Gate: exactly one run ID and one new map; never retry a terminal failure or low score.
8. Score the new map with the unchanged answer key and `field-aware-v3`. Report matched/missed rows, all 19 prior-row preservation, rows 16/24/26, usage, and completion outcomes. Gate: 27/30 or better plus preservation and negative controls passes; anything else is an honest failed gate.
9. If the new map regresses, restore `224ca68d-82c8-4954-ac65-59b02db00546` as active using the already proven guarded one-active-map transaction. Never delete a map. Gate: the 23/30 map is again the sole active/degraded map.
10. Re-run the section-10 gates, update the completion plan and `evals/r2-responsibilities.md`, close issue #4 only if code/main/CI/deployment/run/map/score/docs all agree, and retire the predecessor R2 handoff only when the repository successor rule passes. Gate: one durable record tells the same truth everywhere.

## 7. Constraints and gotchas in force

Exactly one production run is authorized. No retry or second run. Keep the answer key, matcher, 27/30 threshold, negative controls, model route, budgets, concurrency, schema, and business-model flags unchanged. No migration. No source text, model response, production row, or secret may enter chat or logs. Do not delete maps. Stored-record count is not quality. A low score is a completed failed gate, not permission to tune and rerun.

Use an isolated current-upstream worktree. Stage only owned files. Before committing, `git var GIT_COMMITTER_IDENT` must show `Albert Hazan <u2giants@users.noreply.github.com>`. The production worker is deployed only after all licensed and live gates pass. Trigger.dev cannot promote an older deployment, so rollback code requires a forward deploy; map restoration is separate.

The token incident requires separate authorization. Do not disable the MCPs as a substitute for rotation, and do not print process arguments while diagnosing it.

## 8. Access and environment

This session ran on EDGE-DEV in `C:\repos\oracle-worktrees\r2-bounded-correction`. GitHub and 1Password were authenticated. The branch is pushed. EDGE-DEV has no licensed fixture and is not authorized for the production gate.

Run the remaining work on `al8960ofc`. 1Password vault is `vibe_coding`. Database URL: item `qcuyabwseaptvuzvtjejffi2ou`, field `password`. Oracle OpenAI key: item `3onekcbg3dxnazpnt36d4yzfcq`, field `openai_chatGPT_Oracle`. Trigger.dev project: `proj_wgpzsvhmsopqhvwqaycn`. Production Supabase project: `eqccjfbyrywsqkxxpjvg`. Never reveal any field value.

## 9. Open questions and risks

The measured R2 result is unknown until the one authorized production run. The seed-local correction may recover rows 5, 14, 15, or 23, may make no difference, or may regress; the frozen gates decide. The live probe reduces contract risk but does not prove answer quality.

The MCP bearer tokens exposed on 2026-09-08 remain compromised until rotated. Existing configuration, backups, and session history may contain copies. Do not claim containment as remediation. Albert's rotation authorization is the only outstanding owner decision and appears in section 0.

## Handoff self-audit

1. Yes. Sections 1-3 define the application, goal, exact pushed commit, deployment state, test evidence, and host blocker for a newcomer.
2. Yes. Sections 4-5 preserve the failed global-prompt approach, wrong-host dead end, dependency flag error, security incident, and the seed-local design rationale.
3. Yes. Sections 6-8 give ordered commands/routes, pass/fail gates, locked constraints, identifiers, environments, and secret references without values; section 9 states every uncertainty.
4. Yes. A line-by-line sweep of sections 1-9 found one owner decision: rotate the two compromised MCP bearer tokens. It is consolidated in section 0 with the recommendation and consequence. The R2 cycle authorization and all frozen decisions are explicitly marked settled and must not be re-asked.
