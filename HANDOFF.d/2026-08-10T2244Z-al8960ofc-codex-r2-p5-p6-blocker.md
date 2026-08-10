# HANDOFF — R2 P5/P6 verification blocker (2026-08-10 22:44 UTC, al8960ofc/codex)

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

### BLOCKING

None. The remaining work is technical and already authorized. A fresh coding session should fix the three review findings below without asking Albert another question.

### RECOVERABLE

None.

### NOT PART OF THIS WORK, AND NOBODY IS ON IT

None found in this closeout.

### Already settled — do NOT re-ask

- On 2026-08-10, Albert authorized finishing R2 P5 through P8. This includes local fixes, independent review, commit, push, CI, worker deployment, and the single frozen production gate, but every phase gate must pass first.
- Work stays on `main`. Do not create a branch.
- Do not run P7, deploy workers, or consume the one allowed production run until P6 returns approval.
- Merge and apply remain false even if the production score later passes.

## 1. What this application is

The Oracle is POP Creations / Spruce Line's evidence-backed company knowledge system. Employees use chat and uploaded documents. Workers read source material, extract business duties and facts, validate statements against exact source quotes, and build reviewable business maps.

The repository is `C:\repos\oracle`, a TypeScript monorepo using pnpm and Turbo. The web app runs on Vercel at `https://oracle.designflow.app`. Background jobs run on Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`. Data lives in Supabase project `eqccjfbyrywsqkxxpjvg`. This handoff concerns local R2 reader code only. No production or database change was made.

## 2. What we set out to do this session, and why

Albert asked a sub-agent to finish phases P5 through P8 of `plan_r2_source_span_inventory_reader.md`. R2 rebuilds responsibility reading around a fixed inventory of exact source spans. The business goal is to preserve complete, source-backed duties instead of treating small claim fragments as the whole picture.

P5 is the complete local test gate. P6 is an independent read-only review. P7 is commit, push, CI, deploy, and one production gate. P8 records the frozen score decision. Work stopped at P6 because the final review found that two tests do not prove the production behavior they claim to prove.

## 3. Current state — what is true right now

- P0 through P4 are complete and pushed. P4 is in commits `fce082d` and `7991edd` on `main`; GitHub CI run `31421423679` was green.
- The current P5/P6 work is uncommitted. It changes `apps/workers/package.json`, `apps/workers/src/__verify__/r2-pinned-inventory.ts`, `apps/workers/src/__verify__/r2-responsibility-reader.ts`, `apps/workers/src/lib/responsibility-reader.ts`, `apps/workers/src/lib/source-reader-budget.ts`, `apps/workers/src/lib/source-workflow-read.ts`, `packages/ai/src/prompts/workflow-read.ts`, and `plan_r2_source_span_inventory_reader.md`.
- All 14 commands in plan section 10 and `git diff --check` passed at closeout on 2026-08-10. The pinned verifier printed 27/30 supported rows from 144 source-bound seeds. Unsupported rows were 14, 26, and 29.
- That 27/30 result is not accepted. The verifier at `apps/workers/src/__verify__/r2-pinned-inventory.ts:51-63` can find an owner in earlier source text. Production completion receives only the seed's `sourceSpan`, so the score may be too high.
- The top-level test near `apps/workers/src/__verify__/r2-responsibility-reader.ts:3724` proves recovery branches execute. Its repair data is unrelated to its Service Desk fixture, and its retry targets a seed already found on the first pass.
- The final review is `.ai/reviews/20260810-183652-diff-review.md`. Verdict: `BLOCK`. The file is local and untracked, so every required change is copied into this handoff.
- P7 and P8 have not started. There was no commit, push, deployment, production run, model-setting change, database change, or secret use for this unfinished batch.
- The plan now says P5 commands pass but proof is blocked, and P6 is blocked.

## 4. Everything we tried that did NOT work

The sub-agent spent about two hours in repeated review and correction cycles. Important dead ends:

1. Loose token matching could use words from nearby duties. Later versions restricted matching to an assigned seed and excluded ambiguous multi-action seeds.
2. Requiring raw text to equal every normalized answer field was too strict because the frozen answer key paraphrases some source wording.
3. Adding heading context to production and the verifier was rejected. The frozen contract says completion sees the exact request span. Do not restore hidden context merely to raise the score.
4. The current owner-prefix compromise still fails. It searches text production cannot see. Remove it even if the score drops below 27.
5. Helper-level tests were rejected. Reviewers required a test that calls the real top-level `generateSourceWorkflowMap` and proves saved audit state.
6. The first top-level test let simple duties finish without forcing residual completion, retry discovery, and quote repair.
7. The current test forces those branches, but its repair plan uses unrelated Finance/Operations records and different chunk IDs. It proves a call occurred, not that the fixture's failed quote was repaired and saved.
8. The current forced retry returns a seed already in the first inventory. It does not prove a newly discovered duty receives late completion and a durable outcome.
9. Earlier reviews found flow defects that are now fixed: stale inventory validation, duplicate retry IDs, late discoveries skipping completion, lost audit mappings, wrong source order, overlapping duplicate seeds, multi-chunk retry scope, inherited owner loss, and partial quote acceptance. Preserve those fixes.
10. A GLM review failed when its agent requested unsupported action `todowrite`; the session was aborted without changes. Grok review also reached its skill cost ceiling. Use the installed Codex diff reviewer for the next P6 check.

## 5. Root causes and key findings

- A passing test is unreliable when it observes more context than production. The pinned verifier must judge only what `responsibilityCompletionRequest(seed)` exposes.
- The production contract is exact-span and source-bound. A model proposal cannot create inventory IDs or destination children outside the inventory.
- Every incomplete or unscheduled seed forces degraded status. Incomplete inventory is audit/work-queue state, never accepted evidence.
- Full-path proof must follow one coherent fixture through failure and recovery. Branch counters alone do not prove acceptance and persistence.
- The pinned source is `Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`. Its SHA is frozen in `apps/workers/src/__fixtures__/licensed-team-responsibilities-v1.json`.
- The final review found no authentication, secret, or data-leak issue. `git diff --check` passed.

## 6. Exact next steps

1. In `apps/workers/src/__verify__/r2-pinned-inventory.ts`, remove the `source.slice(0, sourceStart)` owner lookup and any now-unused argument. Owner support must come only from the seed/request span. Verification: the verifier contains no prefix or neighboring-text owner fallback.
2. Run `pnpm --filter @oracle/workers run verify:r2-pinned-inventory`. Record the honest rows. Do not add fixture-specific aliases, company terms, hidden heading context, or looser matching. Verification: the printed score uses only the exact request span.
3. Rewrite the top-level fixture near `apps/workers/src/__verify__/r2-responsibility-reader.ts:3724` so a duty from that same test document first fails quote validation, then receives a correct candidate-bound repair with the same document and chunk IDs, and appears in saved repair audit state. Verification: restoring the bad quote makes the final saved-state assertion fail.
4. Change the forced retry so it discovers a duty absent from the initial result. Make the new seed incomplete, run late completion, and assert its unique inventory ID, completion outcome, and final saved record. Verification: removing the retry result makes the saved late-completion assertion fail.
5. Run all 14 commands in plan section 10 and `git diff --check`. Verification: all exit zero and honest pinned support is at least 27/30. If below 27, stop. Never weaken the test.
6. Run one fresh read-only Codex diff review against every changed/new project file. Verification: verdict is `APPROVE`, not `APPROVE WITH CHANGES` or `BLOCK`.
7. After approval, verify git identity, stage only the eight R2 files plus deliberate docs, commit and push `main`, then wait for green GitHub CI. Never stage `.ai`, `.playwright-cli`, or screenshots.
8. Only after green CI, follow P7 exactly: deploy the worker through the documented Trigger.dev path, run the one allowed production gate once, and capture terminal audit evidence. Never rerun it for the same release.
9. Apply P8's frozen score rule, update durable records, commit, push, and verify CI. Delete this handoff only when P8 is truly complete.

## 7. Constraints and gotchas in force

- Work only on `main` unless Albert changes the rule.
- Preserve unrelated untracked `.ai` files, `.playwright-cli`, `detail-current.png`, and `rfq-before.png`. Never use `git add -A`.
- Use `apply_patch` for hand edits. Do not edit generated Drizzle migrations.
- No database change is authorized. If needed, stop and use the `u2giants/shared-db` branch-and-PR process first.
- Do not weaken exact quote evidence, field fidelity, frozen budgets, the 27/30 stop gate, or false merge/apply defaults.
- Keep the model configurable through `workflow_read`; do not hard-code a provider or model.
- Frozen limits are 40 read calls, 500,000 input tokens, $10 estimated cost, one quote repair, five omission retries, and one completion retry.
- Any incomplete or unscheduled seed forces degraded status.
- The answer-key fixture may appear only in verifier/eval code.
- P7 production actions remain forbidden while P6 is blocked.

## 8. Access and environment

- Working copy: `C:\repos\oracle` on Windows machine `al8960ofc`; branch `main`, tracking `origin/main`.
- Package manager: pnpm. Run commands from the repo root.
- Git identity was verified as `Albert Hazan <u2giants@users.noreply.github.com>`.
- Pinned source: `Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`.
- Trigger.dev project: `proj_wgpzsvhmsopqhvwqaycn`. Credentials live in 1Password vault `vibe_coding`; never print or commit them.
- Vercel project: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`. Supabase project: `eqccjfbyrywsqkxxpjvg`. Neither needs a change for this batch.

## 9. Open questions and risks

- The honest score after removing the owner fallback is unknown. Below 27/30 is a hard stop requiring a source-grounded design correction.
- The large uncommitted diff contains valid fixes from many reviews. Preserve them while fixing the flawed proof tests.
- Avoid another unbounded review loop. Make the three exact corrections, run the full suite once, then run one time-bounded final review and stop on its verdict.
- No owner decision is pending. Technical gates decide whether work proceeds.

## Mandatory self-audit

1. Yes. Sections 1–3 explain the product, goal, exact state, files, branch, and release status for a newcomer.
2. Yes. Sections 4–5 preserve failed approaches and non-obvious findings needed to continue as effectively as this session.
3. Yes. Section 4 records material failures and why they failed.
4. Yes. Section 6 gives ordered file-specific steps and a verification gate for each.
5. Yes. Sections 1, 5, 7, and 8 define the product, paths, services, IDs, limits, and secret location.
6. Yes. Sections 1–9 were swept line by line. No new owner ruling is needed; settled decisions are listed in section 0.

Final synthesis:

1. Yes. A brand-new developer can continue without missing a step; sections 1–9 provide the evidence.
2. Yes. The full practical knowledge and exact stop point are in sections 3–6.
3. Yes. Background, goals, state, failures, decisions, constraints, risks, actions, and checks are present.
4. Yes. The only owner-related facts are prior decisions, all listed under “Already settled” in section 0.
