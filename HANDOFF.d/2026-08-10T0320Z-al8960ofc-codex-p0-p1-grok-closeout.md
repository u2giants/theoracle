# P0/P1 Grok review closeout

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

None. P2 can start without Albert. Already settled, do not re-ask:

- 2026-08-09: execute `plan_r2_source_span_inventory_reader.md` in P0 through P8 order.
- 2026-08-09: keep the scorer, evidence rules, budgets, merge/apply flags, and one-production-gate
  limit frozen.
- 2026-08-10: P0 and P1 passed. Grok 4.5 approved starting P2 with four non-blocking notes.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. TypeScript workers find duties and process facts, bind
them to exact source quotes, and prepare reviewable business knowledge. The repository is
`u2giants/theoracle` at `C:\repos\oracle`, branch `main`. The web app runs at
`https://oracle.designflow.app`; workers run in Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn`; data lives in Supabase project `eqccjfbyrywsqkxxpjvg`.

This work changes the responsibility reader from model-first to inventory-first. Pure rules live in
`apps/workers/src/lib/responsibility-reader.ts`; worker calls and saved results live in
`apps/workers/src/lib/source-workflow-read.ts`; schemas and prompts live in
`packages/ai/src/prompts/workflow-read.ts`.

## 2. What we set out to do this session, and why

Albert first asked to complete P1, then asked for an independent Grok 4.5 opinion on P0 and P1. P0
had already proved credible non-scorer recovery mechanisms for all 30 answer-key rows. P1 created a
stable source-bound duty inventory before model output. This closeout preserves Grok's review so P2
can use its findings without reading this chat or rerunning the paid review.

## 3. Current state, what is true right now

- P1 code commit `a9c1cb8283154d9a9bca0aa86b40f39e5b435a0e` and handoff commit
  `f12ded350a7e458834bd2508d8ddf00c5d124a76` are pushed to `main`.
- GitHub Actions runs `31351346476` and `31351509885` passed.
- P0 and P1 are complete. P2 is the fresh-session starting point in
  `plan_r2_source_span_inventory_reader.md`.
- Grok 4.5 session `019fe9a5-2324-7601-a7d1-f50f8dd31d8b` returned
  `APPROVED FOR P2 WITH NON-BLOCKING NOTES`. It found no blocking P0 or P1 defect.
- Grok agreed P0 honestly cleared its 27-row stop gate and P1 implements the required stable IDs,
  raw quote/offset binding, inherited owners, destination and multi-verb children, audit-only parents,
  ambiguous-parent retention, and production base-read seam.
- The review cost $0.5596628 for 945,685 reported tokens, including 819,456 cached tokens.
- No code, database, worker deployment, model setting, production fixture, merge flag, or apply flag
  changed during the Grok review. Only durable closeout documentation is changing now.

## 4. Everything we tried that did NOT work

1. Git Bash could not find `ai-grok-review` on its normal PATH. The installed wrapper is at
   `C:\Users\ahazan2\.cache\ai-devops-memory\bin\ai-grok-review`; calling that exact path worked.
2. The review finished, but the wrapper rejected Grok's newer terminal label `EndTurn` as unknown and
   refused to guess. This did not lose the review. The wrapper's own saved session and `transcript`
   command returned the complete answer. Do not rerun the paid review just because of this wrapper
   compatibility issue.
3. No review correction loop was needed. Grok approved P2 on the first full implementation-review
   turn, with non-blocking notes only.

## 5. Root causes and key findings

- Grok found one latent P1 contract hole in `assertResponsibilityInventorySeeds`: unrelated root
  seeds that both have `parentSeedId === null` can overlap without triggering the intended rejection.
  Current ordered source recognition makes this unlikely, so Grok did not block P2.
- The P1 verifier proves duplicate chunk rejection but does not directly inject missing binding, bad
  offsets/quote mismatch, or a true unrelated overlap. Add those direct integrity tests by P5.
- Destination children intentionally share the parent quote and offsets. P2 exclusive matching must
  distinguish them with `inventorySeedId` and `splitValue`, never quote/offset alone.
- Destination child `sourceSpan` still contains the full parent destination list. P2 deterministic
  completion must derive each child from `splitValue` and the source object head.
- Grok noted minor P0 wording issues for rows 7 through 9 and the durable-map verifier's production
  DB read, but agreed neither weakens the honest 30/30 architecture-mechanism gate.
- The stale plan banner was corrected during closeout to say P0/P1 complete and P2 next.

## 6. Exact next steps

1. Read `AGENTS.md`, `HANDOFF.md`, this file, and all of
   `plan_r2_source_span_inventory_reader.md`. Confirm P0/P1 are complete and P2 is open. You will know
   it worked when P2 is the only valid start.
2. Confirm local `main` equals `origin/main` and preserve unrelated untracked `.ai`, screenshot, and
   browser files. You will know it worked when no unrelated path is edited or staged.
3. Mark P2 in progress. Implement deterministic completion and exclusive proposal matching using
   exact seed identity. Destination siblings must use `inventorySeedId` plus `splitValue` despite
   shared evidence. You will know it worked when one proposal cannot claim multiple child seeds.
4. Tighten the overlap assertion so overlap is allowed only for an explicit parent/child link or
   siblings sharing the same non-null parent. You will know it worked when unrelated null-parent roots
   fail loudly and valid destination siblings still pass.
5. Add direct verifier cases for missing binding, invalid offsets, quote mismatch, and unrelated
   overlap. You will know it worked when each named failure throws and stable valid inventory remains
   byte-identical.
6. Complete P2 through P4 in plan order, run each gate, and stop at context cut B. You will know it
   worked when only complete records enter final elements and every incomplete seed remains audited.
7. Do not deploy or run the pinned production fixture before P7. You will know this constraint held
   when P2 through P6 contain local/review evidence only.

## 7. Constraints and gotchas in force

- Work only on `main`; commit as `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve unrelated untracked work and stage exact files only.
- Do not rerun the model bake-off, weaken quote or field rules, add fixture terms to runtime code,
  raise budgets, hard-code a model, or run an early production gate.
- Frozen reader limits are 40 calls, 500,000 input tokens, and $10. Post-pass limits are one quote
  repair, five omission retries, and one retry per chunk.
- Merge and apply remain false. No database change is authorized.
- The Grok verdict is approval to start P2, not completion of the plan's later P6 full implementation
  review.
- `HANDOFF.d/` contains seven open files after this closeout, above the five-file warning threshold.
  Never delete another session's file without proof that its workstream is complete.

## 8. Access and environment

- Checkout: `C:\repos\oracle`, repository `u2giants/theoracle`, branch `main`.
- GitHub CLI is authenticated; push and Actions checks succeeded.
- Grok review wrapper: `C:\Users\ahazan2\.cache\ai-devops-memory\bin\ai-grok-review`, with
  `AI_GROK_CALLER=codex`, run through Git Bash.
- Review session name: `r2-inventory-p0-p1-review`; Grok session ID is listed in section 3.
- Secrets live only in 1Password vault `vibe_coding`. No secret was read or created this session.
- Later P7 deployment uses `Trigger.dev Personal Access Token (management)` in that vault. Later
  protected DB checks use the current Oracle Supabase DB item and `oracle_session_pooler` field.
  Never print or save values.

## 9. Open questions and risks

- No owner question is open before P2.
- Risk: if P2 matches only by quote and offsets, destination siblings collapse or one proposal claims
  several duties. Use seed identity and destination value.
- Risk: if P2 completes destination children from the unmodified parent `sourceSpan`, every child may
  retain every destination. Use the locked child-specific rewrite.
- Risk: the overlap safety claim is stronger than the current null-parent check. Close it early in P2
  and verify it directly.
- Decision dated 2026-08-10: Grok's non-blocking notes do not require a P1 rewrite before P2, but they
  must be closed no later than P5.

## Handoff self-audit

1. Yes. Sections 1 through 3 define the app, goal, runtime, commits, CI, exact Grok verdict, cost, and
   unchanged production state for a street-new developer.
2. Yes. Sections 4 and 5 preserve both failed wrapper paths and every non-obvious review finding.
3. Yes. Sections 6 through 9 give ordered P2 work with a success gate for every step, all constraints,
   access locations without secret values, and dated risks and decisions.
4. Yes. A line-by-line owner-decision sweep found no unresolved owner choice in sections 1 through 9.
   Section 0 states that and lists all settled decisions that must not be re-asked.

Self-audit result: passed. All ten sections are present, the paid review is recoverable without this
chat, failures are preserved, and a fresh developer can continue P2 without asking a question.
