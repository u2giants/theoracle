# Connected business answers — first refactor slice

## STATUS (2026-09-22)

| Step | State | Evidence |
|---|---|---|
| Diagnose | Done | `bugs.md`, audited upstream `63cdcaa` |
| Evidence assembly and retrieval | Released | PR 16; production revision `824c1ff`; exact included-claim audit passed |
| First live acceptance | Partial | Three isolated production questions proved retrieval but exposed false gaps and omitted exceptions/responsibilities; evidence is recorded on issue [15](https://github.com/u2giants/theoracle/issues/15) |
| Evidence reconciliation and canonical rendering | Released | PR [17](https://github.com/u2giants/theoracle/pull/17) merged as `499d8b0`; exact production deployment and CI passed. Every retrieved claim is classified; relevant claims must appear; gaps are bounded; server renders approved summaries; 80-claim ceiling; bilingual evidence fails closed. |
| Independent semantic gate | Released; one live fallback observed | Different-provider validation/repair and one-repair maximum are live. In the retained Q1 run, Gemini rejected the strict schema as too complex, then Anthropic fallback succeeded; preserve the attempt trail when diagnosing. |
| Second live acceptance | Partial / OPEN | Q1 completed in isolated channel `15d9ff01-2347-4b03-b308-f6fab0a9de71`; Q2/Q3 were not sent and Q1 was not independently graded. Issue [15](https://github.com/u2giants/theoracle/issues/15) was reopened after PR 17 auto-closed it. Do not claim PASS or retry Q1. |

Fresh sessions start with this STATUS and [the current handoff](HANDOFF.d/2026-09-22T2033Z-916-codex-live-proof-interrupted.md).

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
audit found disconnected source structures and answer contexts. The initial audit baseline was
`63cdcaa`; the released implementation and current source of truth are identified in STATUS above.

## 4. Scope

Deliver context-aware retrieval, explicit cross-domain preservation, bounded approved
relationship support expansion, source-ID citations, and a production-used orchestration
fixture. NOT included: database changes, automated business-model application, raw-source
serving, approval bypass, all missing shape readers, ingestion corrections, Brain fixes,
or Jev work owned by issue 14. This slice is necessary groundwork, not completion of the
entire macro-first redesign. It does not assert live comprehension from canned tests.

## 5. Released code

The baseline defects were latest-message-only retrieval, missing relationship premises, and
cross-domain exclusions. PR 16 released bounded context-aware retrieval and complete relationship
support. PR 17 released evidence reconciliation, canonical rendering, and independent semantic
validation/repair. The published responsibility gate passes 23/25 under the approved v2 contract;
older canonical-plan failure banners are historical. STATUS and the current handoff govern the
remaining live proof.

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

## 9. Released implementation and remaining proof

Steps 1–5 are released through PRs 16 and 17:

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
6. Finish the three-question second live acceptance defined in the current handoff. Q1 is complete
   and must not be repeated. After a fresh exact bounded review authorizes the expired production
   window, send Q2 and Q3 only, inspect their context packs and model-run trails, and obtain an
   independent PASS/FAIL grade for all three retained answers. Record evidence under issue 15. No
   new ingestion or approval changes are part of this proof. If access is absent, keep issue 15
   owned and document the exact blocker; do not claim the outcome complete.

The fresh successor owns step 6. After verified three-answer acceptance, reassess the next
macro-first slice.

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

The first direct-call live-dispatch plan is historical and must not be reused: browser safety
correctly blocked scripted authenticated POSTs. An independently reviewed replacement used the
normal UI plus a separate disabled-test-employee typing guard and an immediate status-only update
to keep test messages out of extraction. Q1 completed with every test row `skipped`, the guard
expired naturally, and no lull job ran. Q2/Q3 remain open. Because the old two-hour guard and its
production window have expired, a successor must obtain a fresh exact bounded review before any
new production write. Do not retry Q1, delete retained evidence, or treat the earlier approval as
blanket authority.

Run `corepack pnpm --filter @oracle/web verify:business-answer`,
`corepack pnpm --filter @oracle/ai verify:retrieval-plan-domain-boundaries`,
AI/web typechecks, and the existing retrieval parity, entity-aware, Chinese retrieval,
and chat attachment guards. Run web production build with CI-safe placeholder env values.
Tests must report missing evidence honestly and never count mock generation as model quality.

## 11. Constraints

Worktree isolation; own files only; no canonical checkout edits; Albert committer identity;
branch and PR; task gate before review/ship/deploy. CI/package edits raise task class to
deployment. No schema or worker deployment required. Shared model flags remain unchanged.
The successor that completes and independently grades Q2/Q3 posts the final evidence but leaves issue
15 open. Only the original issue-opening Codex chat may close it. Preserve other handoffs and the root
pointer.

## 12. Access/environment

Machine 916-alien; successor worktree and branch must be created fresh from current `origin/main`.
`gh` is authenticated as u2giants. Production login, provider, and read-only database access were
exercised for Q1 on 2026-09-22; no new write is authorized without the fresh bounded review named
above. Secrets, if needed, must remain in protected local configuration or be obtained through
1Password `vibe_coding` after reading its skill. Never expose or commit them.

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
