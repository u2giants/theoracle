---
issue: 15
status: OPEN
owner: Codex chat 019f5f18-a461-7861-a0ec-be5ba1f7bb6c (original issue opener)
---

# Connected business answers: released code, interrupted live proof

## 0. Decisions only the owner can make

One time-specific owner action remains: after the successor presents the freshly reviewed exact
Q2/Q3 UI-send plan, Albert must confirm immediately before those messages are sent. This is a safety
confirmation, not a product-design choice, and an earlier confirmation cannot authorize a new window.

Already settled; do not re-ask:

- On 2026-09-20 Albert authorized the best next refactor and instructed the session not to stop
  until the comprehension problem was solved.
- Albert confirmed the exact three isolated production test messages used for the expired window;
  do not re-ask about their wording or purpose.
- Technical production authorization belongs to an independent reviewer under Albert's standing
  rule. Do not ask Albert to judge a technical production plan.
- The current session ended on Albert's explicit 2026-09-22 wrap-up request. Resume in a fresh
  session; do not continue production writes from this closed one.

If a new owner decision appears, present the whole list to Albert in one message before work.

## 1. What this application is

The Oracle is POP Creations / Spruce Line's evidence-backed company knowledge application.
Employees ask business questions and upload material; approved claims, reviewed relationships,
and quote-level evidence are supposed to produce explainable answers rather than generic model
guesses. The repository is `u2giants/theoracle`, a pnpm TypeScript monorepo. The employee web app
runs on Vercel at <https://oracle.designflow.app>; Trigger.dev runs workers; the application owns
Supabase project `eqccjfbyrywsqkxxpjvg`.

This workstream repairs the employee-chat answer path for connected business questions: who owns
each step, what approval/decision criteria apply, which exceptions alter the path, and what happens
downstream. Canonical status and rationale are in `plan_connected_business_answers.md`; architecture
is in `docs/architecture.md`; key behavior decisions are in `DECISIONS.md`.

## 2. What this session set out to do, and why

Production replay had already proved that retrieval could find approved facts, yet the final answer
discarded them, falsely said supplied criteria were missing, lost exceptions/responsibilities, and
could carry irrelevant context into a new topic. Issue [#15](https://github.com/u2giants/theoracle/issues/15)
tracks the outcome.

The technical objective was to make every substantive answer reconcile all retrieved claims before
publication, render canonical approved statements/citations on the server, separate documented
relationships from reviewed interpretation, bound honest gaps, run a different-provider semantic
review with at most one repair, and audit every model call. The user then asked for a real signed-in
production proof using three questions: licensed-product journey, China-team responsibilities, and
an unrelated damaged-carton question that tests topic reset.

## 3. Current state — verified 2026-09-22

### Code and release

- PR [#17](https://github.com/u2giants/theoracle/pull/17) merged to `main` on 2026-09-20 as
  `499d8b0dc3a726ea59dc93114cbb165e1f96f9d3` and auto-closed issue #15 through `Closes #15`.
- GitHub CI and the exact Vercel production deployment passed for `499d8b0`; the public footer was
  visually verified on that SHA. The implementation branch's reviewed pre-squash commit is
  `d02aea74ba65fb6d94d12b91b2337bd5feb7e9ff`.
- Released code includes `apps/web/lib/business-answer-reconciliation.ts`, corresponding verifier,
  the chat-route integration in `apps/web/app/api/chat/route.ts`, retrieval/context/policy changes,
  architecture and decision records, and `plan_connected_business_answers.md`.
- Local verification before release passed AI/web typechecks, web lint, retrieval filter parity,
  Chinese retrieval guard, 40 business-context assertions, journey/reconciliation suites, all
  Vercel contract guards, and the production Next.js build. Exact-commit independent review ended
  in APPROVE.

### Issue state

- PR #17 auto-closed issue #15 even though the live proof was incomplete. This wrap-up reopened it
  and posted the exact retained state at
  <https://github.com/u2giants/theoracle/issues/15#issuecomment-5783702016>.
- Issue #15 is the completion contract. It must remain open until Q2/Q3 are completed and all three
  answers receive an independent PASS. The successor posts the final evidence but must not close it;
  only the original issue-opening Codex chat named in this file may close it.

### Production proof state

- Production target was verified as `eqccjfbyrywsqkxxpjvg`; authenticated actor was Albert's active
  employee account. Test channel: `15d9ff01-2347-4b03-b308-f6fab0a9de71`, named
  `ISSUE-15 live proof 2026-09-20T18:47:04.773Z`.
- Inert direct seed Q1 user row: `d3d35276-5f81-49d1-92cb-8c69f3adce78`, `skipped`.
- Actual UI Q1 user row: `7f35f9a6-ebbc-47a9-b192-037d8ac38cfb`, `skipped`.
- Q1 assistant row: `b9611dfa-64bc-4670-b6fd-fec84c929254`, `skipped`, 5,913 characters.
- Q1 begins by stating the changed-reorder condition and a licensor-specific requirements exception,
  then cites approved claims. That looks directionally better, but nobody independently graded the
  complete answer. Do not call it PASS from this preview.
- Primary answer context pack `c2bcecfb-cd4a-4770-bf39-f452d94b0f3e` / run
  `88a31533-e77f-4e4c-b0d4-6f3eb50e1e35` used OpenAI `gpt-4.1-mini`, succeeded, and included 16
  approved claim IDs.
- Validation/repair context pack `b11447c5-6062-47b0-a28d-ecf751a4071c` / run
  `85751a4d-2f75-4149-abef-100285db3736` retained two attempts: Gemini 2.5 Flash failed with HTTP
  400 because the strict schema had too many states; Anthropic Claude Haiku 4.5 fallback succeeded.
  The recorded final provider differs from the route ID because fallback occurred. Preserve this
  evidence; it is a real adapter/schema compatibility risk, not a reason to suppress the audit.
- The separate fail-closed typing guard used disabled synthetic employee
  `a4ba6aa4-2434-4973-a811-00f269c90108`; its row remains but expired naturally on 2026-09-20.
  It is not an active guard now. No `lull-interjection` job row exists in the test window.
- Q2 and Q3 were never sent. No test row is pending or processing. The original three-call allowance
  was not exhausted, but its time-bounded guard/reviewer approval is stale and must not be reused.
- Retained scratch inspection/state files may still exist at
  `C:\tmp\oracle-issue15-proof-state.json`, `C:\tmp\oracle-prod-proof.mjs`,
  `C:\tmp\oracle-wrapup-status.mjs`, `C:\tmp\oracle-production-proof-plan.txt`,
  `C:\tmp\oracle-issue15-final-evidence.jsonl`, and
  `C:\tmp\oracle-issue15-live-evidence.jsonl`. Treat them as local evidence, not source of truth;
  re-query live rows before acting.

### Repository/workspace state

- This docs handoff branch is `codex/issue15-live-proof-handoff-20260922`, created from current
  `origin/main` `499d8b0` in worktree
  `C:\Users\ahazan2\.codex\worktrees\oracle-answer-reconciliation\oracle`.
- The earlier implementation branch `codex/answer-reconciliation-20260920` was squash-merged through
  PR #17; its remote was deleted. The worktree was deliberately reused for this docs-only closeout.
- Four recovery worktrees from this workstream were clean at wrap-up and were deliberately not
  removed because they belong to delegated sessions or preserve integration evidence:
  `D:\repos\oracle-business-audit-20260920`, `D:\repos\oracle-holistic-audit-20260920`,
  `D:\repos\oracle-ingestion-audit-20260920`, and `D:\repos\oracle-retrieval-audit-20260920`.
  A successor may audit/retire them with `cleanup-worktree`; never force-remove them.

## 4. Everything tried that did not work

1. **Bigger/alternate model first:** rejected because the failure was discarded evidence and false
   absence language, not raw model capacity. The released answer ledger fixes the contract instead.
2. **Reuse July unfinished code:** rejected because September upstream superseded it.
3. **Call `/api/chat` directly from browser automation:** the browser safety layer rejected
   `javascript:`/scripted POST execution. Its instruction explicitly prohibited bookmarklets,
   developer console, raw browser protocol, or indirect workarounds. Do not retry them.
4. **Use the normal UI without modeling side effects:** rejected by independent review because
   `/api/messages` briefly inserts `pending` and schedules `lull-interjection`.
5. **Guard with Albert's typing row:** rejected because the normal UI deletes Albert's exact typing
   key after send, creating a race. The approved solution used a separate disabled synthetic
   employee key that the browser could not delete.
6. **Early production-proof plan drafts:** independent reviewer correctly rejected them for an
   unbounded pending-extraction interval, ambiguous browser-delete ordering, unproven channel-row
   mutations, unproven 60-second debounce, and guard expiry. The final plan bounded the two-hour
   guard, 90-minute proof, extraction-cron window, triggers/FKs, and immutable snapshots.
7. **Global time-window audit query:** it falsely treated unrelated scheduled contradiction checks as
   test audit rows. Scope audit by the isolated channel/message/call window instead. The Q1 context
   packs have `included_message_ids=[]`, so direct message-ID membership alone also misses them;
   the retained run was correlated through the exact answer time window and task/run records.
8. **Primary Gemini validation/repair attempt:** live HTTP 400, `INVALID_ARGUMENT`, because the strict
   schema produced too many serving states. Anthropic fallback succeeded and was recorded. Do not
   erase the failed attempt or assume the configured route equals the actual provider.
9. **Release-gate command sequencing:** an earlier PR used PowerShell semicolons, so a merge command
   ran after `ai-task-gates` returned STOP for an incorrectly declared `deployment` class. The issue
   records the incident. It was corrected by separately declaring the actual `production` class and
   checking each exit before the next command; never use command chaining across a protected gate.

## 5. Root causes and key findings

- Retrieval faithfulness and answer faithfulness are separate contracts. The live partial run before
  PR #17 had approved criteria/exceptions in context but still called them missing.
- The released reconciliation ledger in `apps/web/lib/business-answer-reconciliation.ts` forces each
  retrieved claim into an answer/gap decision, while `apps/web/app/api/chat/route.ts` renders approved
  statements/citations canonically and permits only bounded reviewed interpretation.
- The different-provider gate is live, but the Q1 proof exercised fallback: OpenAI produced the answer;
  Gemini could not serve the strict repair schema; Anthropic repaired successfully. A future code task
  should audit that schema class, but wrap-up scope froze new fixes.
- Q1 proves the production code can return a long, cited answer with 16 approved claims and a separate
  repair call. It does **not** yet prove holistic quality because the full answer and context were not
  independently scored.
- Q2 is the follow-up continuity test: `How does that affect the China team, and which responsibilities
  belong to Licensing, Design, Sales, and China?`
- Q3 is the held-out topic-reset test: `New topic: how should warehouse staff handle damaged cartons?`
  It must not inherit licensing/file context or assert globally that no procedure exists merely because
  bounded retrieval found none.
- `plan_connected_business_answers.md` is canonical for this slice. Its 2026-09-22 STATUS table now
  distinguishes released code from the partial live outcome; do not redo implementation steps 1–5.

## 6. Exact next steps

1. Start a fresh isolated worktree from current `origin/main`, read `AGENTS.md`, this file, and the
   STATUS table in `plan_connected_business_answers.md`. Run
   `ai-task-gates start --class production --base origin/main` with the exact Q2/Q3 proof scope.
   **Success:** effective class is production and no source edit has started.
2. Re-query issue #15, production deployment SHA, channel/messages, guard row, model runs, attempts,
   and job runs. Treat every value above as stale until reverified. Confirm Q1 rows remain skipped,
   no new rows appeared, and production still runs a reviewed revision.
   **Success:** an immutable read-only baseline names exact current IDs/xmin values and deployed SHA.
3. Write a new exact bounded production plan for Q2/Q3 only. Do not retry Q1. The old guard expired;
   use a fresh fail-closed design, account for `/api/messages`, extraction cron, lull debounce, every
   allowed table/type, triggers/FKs, and no cleanup. Obtain an independent technical APPROVE tied to
   the exact plan. **Success:** reviewer says APPROVE with no unsafe ambiguity.
4. Immediately before the first browser Send, obtain Albert's required action-time confirmation for
   the exact two messages and isolated Oracle destination. Use the normal signed-in UI only; never
   script authenticated requests or extract tokens. **Success:** confirmation is the newest user
   instruction and the fail-closed guard is live/unexpired.
5. Send Q2 once, make its new user row `skipped` within the reviewed bound, let one automatic chat call
   finish, and reconcile all allowed rows before Q3. **Success:** exactly one Q2 user/assistant pair,
   no pending/processing row, no unexpected/lull side effect, every run/attempt/pack linked.
6. Independently inspect/grade Q1 and Q2 together for supplied criteria, exception conditions, named
   responsibilities, downstream handoff, distinction between documented relationships and reviewed
   interpretation, citation membership, and different-provider review. Stop on anything below PASS.
   **Success:** a reviewer returns explicit PASS with evidence IDs, not a prose impression.
7. Send Q3 once under the same still-valid exact plan and guard. Verify no licensing/file carryover,
   no fabricated warehouse procedure, and bounded wording for absent evidence. **Success:** exact one
   Q3 pair, all rows skipped, clean topic reset, reviewer PASS.
8. Wait for and reconcile all scheduled lull jobs while the guard remains valid. Post a signed final
   evidence comment to issue #15 and leave it open for the original issue-opening Codex chat.
   **Success:** final PASS/FAIL evidence is durable on the open issue, production evidence is retained,
   and the original opener has everything needed to make the closure decision.
9. The original issue-opening Codex chat alone may close #15 after verifying all three answers passed;
   that same owner then retires this handoff under the successor rule and updates/deletes the plan only
   if every step is truly complete.
10. Open a separate code issue only if the live Gemini strict-schema 400 needs repair after the acceptance
   outcome is settled. Do not bundle that implementation into the live-proof session.
   **Success:** any repair has its own single unproven outcome and does not contaminate proof evidence.

## 7. Constraints and gotchas in force

- Keep canonical checkouts landing-only. All edits use an isolated current-upstream worktree.
- Never push directly to protected `main`; branch, PR, required checks, merge, deployment verification.
- Before protected work, declare/check task gates and stop on nonzero exit. Never chain a protected
  gate and a following mutation with semicolons.
- Production/shared infrastructure is read-only by default. Exact technical production approval comes
  from an independent reviewer under Albert's standing rule.
- Browser safety prohibition is permanent for this path: no bookmarklet, developer console, raw CDP,
  scripted POST, indirect execution, or auth-token extraction.
- Normal UI send is an external representational action and needs confirmation immediately before it.
- Preserve approved-claim/translation/provenance filters, different-provider review, citation identity,
  and full attempt logging. Do not suppress failures to make the proof look green.
- No schema, setting, claim, relationship, source document, employee, or unrelated channel mutation.
  Do not delete retained test rows or expired guard without a newly reviewed exact cleanup plan.
- One unproven live outcome per session. The remaining outcome is issue #15 Q2/Q3 acceptance; do not
  combine the Gemini schema repair or broader macro-first redesign with it.
- Root `HANDOFF.md` is a static pointer. Never rewrite it or edit another session's handoff.
  `2026-09-20T1411Z-916-codex-connected-answers.md` remains because its own status is `OPEN` and it
  does not say its work was committed and pushed, so the first successor-retirement condition is not
  met. Its obligations are duplicated here intentionally; do not delete it until all three repository
  successor conditions are independently verified.

## 8. Access and environment

- Machine: `916-alien`, Windows 11, PowerShell 7.
- GitHub CLI was authenticated as `u2giants`; origin is `git@github.com:u2giants/theoracle.git`.
- Git committer identity verified: `Albert Hazan <u2giants@users.noreply.github.com>`.
- Chrome was signed into Oracle as Albert H. during Q1. A successor must verify the session is still
  authenticated; do not automate login/security prompts.
- Production app: <https://oracle.designflow.app>.
- Vercel project: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`.
- Supabase application project: `eqccjfbyrywsqkxxpjvg`. The configured Supabase MCP previously pointed
  at a different project and must not be used for this proof.
- Existing local environment file: `D:\repos\oracle\.env.local`. It was read programmatically without
  printing secret values. Secrets belong in 1Password vault `vibe_coding`; never put values in chat,
  commands, handoffs, issues, or commits.
- Trigger.dev project: `proj_wgpzsvhmsopqhvwqaycn`.
- Independent plan-review conversation used local session `20260920-143119-987156`; its result is
  historical because the guard expired and the proof was interrupted.

## 9. Open questions and risks

- **Live answer quality:** Q1 has not been independently graded. Its promising opening is not proof.
- **Incomplete sequence:** Q2/Q3 are absent, so follow-up continuity and topic reset remain unproven.
- **Audit correlation:** Q1 context packs record `included_message_ids=[]`; correlation relied on the
  exact call window and task/run evidence. Verify whether this is intended before calling auditability
  complete; do not invent a link.
- **Strict-schema compatibility:** Gemini's live 400 shows one eligible route cannot serve the repair
  schema. Fallback preserved capability, but cost/reliability and failover semantics need a separate
  code outcome if acceptance otherwise passes.
- **Stale access/state:** browser login, deployed SHA, issue comments, row xmins, local scratch files,
  and worktree list may have changed after 2026-09-22. Reverify cheaply before use.
- **Guard artifact:** expired guard row is retained intentionally. It is not protection, and its presence
  must not be mistaken for an unexpired guard.
- **Broader business understanding:** this slice repairs chat evidence reconciliation only. It does not
  finish deferred ingestion/Brain/business-model architecture work or enable shadow proposals.

## Delegated-agent records

### Agent: retrieval_audit / `D:\repos\oracle-retrieval-audit-20260920`

- **Asked to do:** audit cross-domain retrieval exclusions and preserve explicit licensing/creative
  intent in PLM/process questions.
- **Actually did:** clean commit `e899457a0bc31dedf3c95b8f2658efbd540172e7` on
  `codex/cross-domain-retrieval-20260920`, changing retrieval-plan domain boundaries and tests.
- **Found:** requested neighboring domains/entities were erased by heuristics.
- **PR / branch:** no agent PR; root integrated/superseded the result in PR #17.
- **Worktree:** clean recovery copy; not removed.
- **Deliberately did not do:** chat rendering, production writes, issue closure, or broader entity-aware
  retrieval redesign.

### Agent: business_model_audit / `D:\repos\oracle-business-audit-20260920`

- **Asked to do:** design/build bounded connected-business evidence assembly and follow-up context.
- **Actually did:** clean commit `734d5b23fcee48e1f15bd4fc9444fe760c53277b` on
  `codex/business-answer-context-20260920`, adding context helper and verifier.
- **Found:** relationships lost premises, budgets needed atomic admission, and follow-ups needed recent
  user questions without treating prior assistant text as fact.
- **PR / branch:** no agent PR; root integrated/superseded the result in PR #17.
- **Worktree:** clean recovery copy; not removed.
- **Deliberately did not do:** schema changes, shadow business-model serving, release, or production proof.

### Agent: ingestion_audit / `D:\repos\oracle-ingestion-audit-20260920`

- **Asked to do:** independent review of the first bounded live-dispatch plan and ingestion safety.
- **Actually did:** returned review findings/approval; no commit, branch, or production mutation.
- **Found:** test rows had to stay out of extraction and the initial plan needed explicit scope/time and
  seed coverage.
- **PR / branch:** detached clean recovery worktree at baseline `63cdcaa`; no PR.
- **Worktree:** clean recovery copy; not removed.
- **Deliberately did not do:** ingestion refactor, database changes, deployment, or test execution.

### Agent: reconciliation_design

- **Asked to do:** independently design an exhaustive evidence ledger and deterministic answer contract.
- **Actually did:** returned design analysis; root implemented the final design in
  `apps/web/lib/business-answer-reconciliation.ts` and PR #17. No surviving agent branch/commit was
  identified at wrap-up.
- **Found:** every retrieved claim needed explicit disposition and gaps had to be bounded against supplied
  evidence rather than model memory.
- **PR / branch:** none; integrated by root.
- **Worktree:** no separately identified live worktree at wrap-up.
- **Deliberately did not do:** release decisions, production writes, or issue closure.

### Agent: validation_design

- **Asked to do:** independently design semantic review/fail-closed behavior for reconciled answers.
- **Actually did:** returned design analysis; root implemented different-provider review, one repair
  maximum, and audit records in PR #17. No surviving agent branch/commit was identified at wrap-up.
- **Found:** citation membership alone cannot prove semantic entailment; review must use a different
  provider family and fail closed.
- **PR / branch:** none; integrated by root.
- **Worktree:** no separately identified live worktree at wrap-up.
- **Deliberately did not do:** deployment, browser proof, or production mutations.

## Mandatory self-audit

1. **Can a brand-new developer continue without chat context? Yes.** Sections 1–3 define the app,
   business outcome, release/issue/workspace state, exact production IDs, and what is still missing.
2. **Can the developer continue as effectively as this session? Yes.** Sections 4–5 retain every costly
   dead end, browser prohibition, reviewer rejection class, audit-correlation trap, and live fallback.
3. **Is flawless execution specified? Yes.** Section 6 gives ordered actions with a success gate for each;
   §§7–9 define authorization, access, constraints, stale facts, and risks; delegated-agent blocks keep
   branch/worktree ownership and deliberate omissions explicit.
4. **Does Section 0 contain every owner decision and action? Yes.** A line-by-line sweep of §§1–9 and
   all five agent blocks found no unresolved product decision and one pending time-specific owner
   confirmation. The settled message wording and the fresh action-time confirmation are both indexed
   in §0; technical production review remains assigned to the independent reviewer, not Albert.

All checklist items pass. This is an OPEN workstream because issue #15 remains open and Q2/Q3 plus
independent grading are unfinished.
