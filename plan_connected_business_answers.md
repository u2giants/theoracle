# Connected business answers — first refactor slice

## STATUS (2026-09-20)

| Step | State | Evidence |
|---|---|---|
| Diagnose | Done | `bugs.md`, audited upstream `63cdcaa` |
| Evidence assembly and retrieval | Released | PR 16; production revision `824c1ff`; exact included-claim audit passed |
| First live acceptance | Partial | Three isolated production questions proved retrieval but exposed false gaps and omitted exceptions/responsibilities; evidence is recorded on issue [15](https://github.com/u2giants/theoracle/issues/15) |
| Evidence reconciliation and canonical rendering | Implemented, locally verified | Every retrieved claim is classified; relevant claims must appear; gaps are bounded; server renders approved summaries; 80-claim ceiling; bilingual evidence fails closed; web typecheck/lint and business-answer suite pass |
| Independent semantic gate | Implemented, locally verified | Different-provider review, one repair maximum, then fail closed; each call has its own context pack |
| Second release and live acceptance | In progress | Normal PR/CI/Vercel release followed by a new isolated production replay; issue 15 stays open until PASS |

Fresh sessions start with this STATUS and [the handoff](HANDOFF.d/2026-09-20T1411Z-916-codex-connected-answers.md).

## 1. Ultimate goal

An employee can understand a connected business journey from approved knowledge:
who acts, what approval is needed, what exceptions apply, and what happens downstream.
The first scope is a licensed-product question spanning process, responsibilities, and
meeting-derived facts. If a step conflicts with this goal, the goal wins — stop and flag it.

## 2. Application

Oracle is POP Creations / Spruce Line's evidence-backed company knowledge application.
`u2giants/theoracle` is a pnpm TypeScript monorepo: Next.js web on Vercel at
https://oracle.designflow.app, Trigger.dev workers, Supabase storage/auth/database.
This slice runs in employee chat; workers and schema are unchanged.

## 3. Trigger

Albert requested a fresh whole-codebase diagnosis, then authorized: “do whatever you
think is the best next step to refactor this application to do what we need.” The
audit found disconnected source structures and answer contexts. Current upstream is
`63cdcaa`; the old shared checkout still has unrelated unfinished July edits. Do not use them.

## 4. Scope

Deliver context-aware retrieval, explicit cross-domain preservation, bounded approved
relationship support expansion, source-ID citations, and a production-used orchestration
fixture. NOT included: database changes, automated business-model application, raw-source
serving, approval bypass, all missing shape readers, ingestion corrections, Brain fixes,
or Jev work owned by issue 14. This slice is necessary groundwork, not completion of the
entire macro-first redesign. It does not assert live comprehension from canned tests.

## 5. Current code

At baseline chat retrieves latest-message-only top eight claims (`route.ts:183–205`),
then prints legacy relationship support IDs without their summaries (`:257`). Retrieval
excludes licensing/creative domains on PLM queries (`retrieval-plan.ts:899–915`).
The published responsibility gate now passes 23/25 under the approved v2 contract;
older canonical-plan failure banners are historical. No release of this slice yet.

## 6. Root cause

Faithful extraction and usable business answers are different contracts. Retrieval can
discard requested departments, follow-ups lose their subject, and relationships lose
their premises when rendered. See H1/H3/H7 in `bugs.md`. The existing shared business model
is shadow-only; this release uses reviewed claims/legacy relationships without enabling it.

## 7. Rejected approaches

- Resuming July code: superseded by September upstream.
- Increasing model size or reader retries first: does not repair missing answer evidence.
- Serving raw/unapproved sources or enabling shadow proposals: crosses the review boundary.
- Calling a fixture an end-to-end live proof: fixture proves orchestration only.
- Loading the full Brain/company corpus: unbounded, wasteful, and not targeted to the question.

## 8. Decisions

Locked 2026-09-20: preserve authorization/approval filters; existing OracleAIClient and
route selection; bounded searches (default one overall plus two domain passes), bounded
evidence (18,000 characters); no invented quotes; relationship text admitted with all
its supporting facts or omitted; logs and context metadata record actual inclusion.
Follow-up context uses recent user questions, never prior assistant assertions as facts.
All budget overrides are validated. New question topic resets context.

Interpretation is allowed only as explicitly labeled reasoning from supplied premises.
Citation membership checking does not prove semantic entailment; human/live evaluation does.

## 9. Ordered implementation

1. Fix heuristic exclusions in `retrieval-plan.ts` and domain-boundary tests, including
   sibling entity exclusions. Preserve narrow noise filtering. Gate: existing and added
   domain-boundary cases pass.
2. Add pure evidence builder and follow-up query helper in `business-answer-context.ts`.
   Preserve full supporting summaries, deterministic budget accounting, untrusted-data
   boundaries, and observable omissions. Gate: helper contract tests pass.
3. Add `business-answer-retrieval.ts` orchestrator using injected existing approved search
   and relationship helpers. Bounded domain passes inherit every plan filter. Gate:
   journey fixture proves owner, approval, handoff, and exception premises arrive together.
4. Wire chat, consistent included-claim metadata, and citation membership guard. Bump
   Oracle prompt and record decision. Gate: web/AI typecheck, production web build, route
   wiring fixture, and existing retrieval/attachment checks pass.
5. Complete self-audit then independent review. Register tests in CI. Commit owned files,
   branch PR, green checks, reviewer-approved normal merge/deployment. Gate: CI and deployed
   revision agree. Never use admin bypass for this code release.
6. With exact dispatch approved by independent reviewer, use an authorized test employee
   and channel to ask one licensed-product journey question and one follow-up. Inspect
   context pack and answer for supported ownership, gates, exceptions, consequences,
   citations and honest gaps. Record evidence under issue 15. No new ingestion or changes
   to approvals are part of this proof. If approved data/session access is absent, keep
   issue 15 owned and document the exact blocker; do not claim the whole outcome complete.

Steps 1 and 2 can run independently in isolated worktrees. Main owns 3–6. Natural boundary:
after verified release and the single live proof, reassess the next macro-first slice.

### Adversarial cases

| External input | Hostile/failure case | Test |
|---|---|---|
| User question | PLM wording erases explicitly requested licensing | domain-boundary + journey tests |
| User history | Prior assistant invents a policy | context helper follow-up tests |
| User history | Warehouse topic inherits licensing | held-out journey case |
| Approved summary | Instructions masquerade as facts | context helper JSON/data-boundary case |
| Relationships | Supporting facts exceed budget | atomic admission test |
| Model output | Invented claim citation | journey citation-integrity case |
| Search | Failure or zero approved facts | rejected-search/empty-context journey cases |

## 10. Tests

Verified locally 2026-09-20: helper 40 assertions (0 skipped/ignored), journey and
compiled support-filter SQL, retrieval domain boundaries, entity-aware retrieval,
AI/web typechecks, complete existing Vercel guard suite, production Next.js build.
The build used CI placeholders and no production credentials. Reviewer independently
reran helper/journey/domain suites and approved the exact web-only release.

Relationship premises now reuse all hard retrieval filters and approved translations;
positive domain seed scope alone may broaden. Any failed premise omits the relationship.
Direct round-robin seeds reserve up to half the text budget before relationships.

Live dispatch approval is conditional: prove production target and existing authenticated
active employee; one isolated DM test channel/membership, at most three user rows inserted
explicitly `extraction_status='skipped'`, no `/api/messages` or lull triggers; at most three
authenticated `/api/chat` calls. Capture row/context IDs and prove no pending test rows.
No claims/settings/schema writes or cleanup deletion. Ordinary message posting is rejected
for this test because it would feed fixture text into extraction.

Run `corepack pnpm --filter @oracle/web verify:business-answer`,
`corepack pnpm --filter @oracle/ai verify:retrieval-plan-domain-boundaries`,
AI/web typechecks, and the existing retrieval parity, entity-aware, Chinese retrieval,
and chat attachment guards. Run web production build with CI-safe placeholder env values.
Tests must report missing evidence honestly and never count mock generation as model quality.

## 11. Constraints

Worktree isolation; own files only; no canonical checkout edits; Albert committer identity;
branch and PR; task gate before review/ship/deploy. CI/package edits raise task class to
deployment. No schema or worker deployment required. Shared model flags remain unchanged.
Only the opener closes issue 15. Preserve other handoffs and the root pointer.

## 12. Access/environment

Machine 916-alien; worktree `D:\repos\oracle-holistic-audit-20260920`, branch
`codex/connected-business-answers-20260920`. `gh` authenticated as u2giants. Dependencies installed
locally with frozen lockfile. Production login/provider/DB access not yet exercised for this
slice; secrets, if needed, only through 1Password `vibe_coding` after reading its skill.
Never copy the canonical checkout's stale `.env.local`.

## 13. Done, rollback, and risks

Done for this slice requires reviewed code, passing tests/build, commit/push/CI, normal merge,
verified Vercel revision, and recorded live answer proof. Issue 15 remains open until that
proof. Broader ingestion/model gaps remain in `bugs.md` and the canonical redesign plan.
Rollback is a reviewed revert through GitHub; no data migration exists. Risks: additional
retrieval latency, heuristic context mistakes, approved-but-incomplete relationships, and
model citations that exist but do not support their associated statements. Measure those
in live proof; prompt instructions alone do not establish correctness.

## Plan self-audit

All 13 sections present. A newcomer has business goal (§1), baseline and failures (§5–7),
locked boundaries (§8/11), named implementation and adversarial gates (§9/10), access (§12),
and honest live acceptance/rollback (§13). The handoff is linked above; no hidden owner
choice is required for local implementation. Deployment approval belongs to independent
review under the standing owner rule. Self-audit passed for this bounded slice, not for a
claim that the entire application redesign is specified or complete.
