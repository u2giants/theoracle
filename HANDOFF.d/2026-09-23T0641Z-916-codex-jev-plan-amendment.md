---
issue: 14
status: OPEN
owner: codex/jev-plan-approval-status
---

# Jev plan safety-amendment successor handoff

Canonical plan: [`../plan_typesafe_jev_decision_layer.md`](../plan_typesafe_jev_decision_layer.md)

Predecessor context: [`2026-09-20T1411Z-916-codex-jev-integration-plan.md`](2026-09-20T1411Z-916-codex-jev-integration-plan.md). That file is unchanged by this session; this successor records the post-publication amendment.

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

Put these two decisions to Albert together before any company data is sent to TypeSafe. They do not block synthetic M0 foundation work.

1. **Vendor/data terms and data-class allowlist.** Recommendation: require TypeSafe enterprise zero-data-retention terms plus acceptable DPA, security, and subprocessor coverage, then explicitly allow or deny internal company, employee communication, licensed, HR/personnel, and customer-personal data. Unknown or mixed-unapproved data remains blocked.
2. **Evaluation spend.** Recommendation: approve a $5 starting cap and increase it only after Oracle's sealed evaluations prove value.

Already settled—do not re-ask: Jev remains a separate bounded-decision service, every use case begins shadow-only and fails open, model `jev-1.13.0` is pinned, and Jev never replaces generation, evidence, permissions, approvals, auth, locks, transactions, or deterministic controls.

The unrelated R2 reason-feedback/key-prefix owner questions remain with `HANDOFF.d/2026-08-27T1600Z-al8960ofc-claude-r2-reason-feedback-regressed.md`; this work must not absorb them.

## 1. What this application is

The Oracle is POP Creations / Spruce Line's evidence-backed business knowledge system. Employees use web and Teams chat; workers turn messages and documents into quote-supported claims; administrators review claims, contradictions, gaps, taxonomy, and synthesized Brain sections. Repository `u2giants/theoracle` is a TypeScript/pnpm monorepo deployed through Vercel, Trigger.dev, and Supabase; production web is `https://oracle.designflow.app`.

## 2. What this session set out to do, and why

Albert asked for the latest repository, a whole-codebase audit of where TypeSafe AI's low-cost Jev decisions could help, and a fresh-session-executable implementation plan. The substantive audit/plan merged in documentation-only PR #19. This successor session hardened the mandatory migration foundation after independent exact-head reviews found execution, privacy, task-gate, evidence, and production-authorization gaps.

The business outcome remains inexpensive semantic decisions without weakening Oracle's evidence, privacy, database, or production controls.

## 3. Current state—what is true right now

- The substantive plan was exact-head approved in run `20260923T015902-1579-11000` at `fab526bd92546acacb599a13c48824e9595b5a1e` and merged in PR #19 as main commit `c5dc22269305cb7a84463890e00f015df1670df7`.
- Issue #14 is open and assigned; it owns implementation. No Jev package, secret, schema, call, deployment, production behavior, or spend is enabled.
- Branch `codex/jev-plan-approval-status` in worktree `C:\Users\ahazan2\.codex\worktrees\jev-plan-final\oracle` contains the documentation-only M0 safety amendment. The amendment is not implementation authority unless its exact head receives APPROVE and the branch merges.
- The amendment splits M0 into independently buildable M0A–M0F outcomes. M0A first creates composite `migration-release`, the union of reviewer-safety, shared-db, deployment, code, and prose gates. M0F alone may perform the production write outcome.
- M0E's rehearsal is post-merge because only then does the exact merged SHA exist. It requires separate reviewer-signed production-read approval, schema-only capture by default, masked and ceiling-bound allowlisted fixtures, dependency-closed pgvector/auth-compatible restore, verified cleanup, and a signed 30-day GitHub artifact.
- M0F requires a distinct GitHub-attested independent-reviewer production-write authorization bound to the exact merged SHA, target, ordered actions, digests, allowlist, expiry, and single-use run ID before credentials or writes. The executor and migration-proof key cannot create that attestation.
- The predecessor handoff was restored byte-for-byte to `origin/main`. This new file is the only handoff authored by this amendment session.
- **HANDOFF THRESHOLD DEFECT:** `HANDOFF.d/` has seven files; excluding the standing legacy exception, six count toward the repository's threshold of five. Oldest-first counted files are `2026-08-06T1510Z-t16-codex-project-status-closeout.md`, `2026-08-27T1600Z-al8960ofc-claude-r2-reason-feedback-regressed.md`, `2026-09-20T1411Z-916-codex-connected-answers.md`, `2026-09-20T1411Z-916-codex-jev-integration-plan.md`, `2026-09-22T2033Z-916-codex-live-proof-interrupted.md`, and this successor. This session has no main/issue proof that the first five are superseded, so none may be deleted; each owning successor must apply the retirement rule.
- Exact-head review `20260923T064415-1022-22067` rejected commit `bb13113` because the production-enable field and durable authorization state were undefined, the five-class union was mislabeled as four, and the threshold defect was undisclosed. The repaired draft names and validates `profiles.production.migration`, adds durable authorization/action tables and one locked activation orchestrator, fixes the union count, and records the defect here. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T065414-2628-27527` rejected commit `0cfad23` because independent approval had no separate trust root, authorization stopped at bootstrap instead of covering later migrations, and an expired partially committed run could become stranded. The repaired draft uses default-branch GitHub OIDC artifact attestations from a credential-free independent-review workflow, requires one authorization per later merged release, and adds attested same-scope renewal/recovery with fake-clock and crash tests. None is accepted until the next exact-head review approves it.
- Reading this file on `main` means the amendment PR containing it merged; use the plan's Publication gate and the PR artifact for the authoritative review run/SHA. On the branch, approval/merge remains pending.

## 4. Everything tried that did not work

- Treating M0 as one large implementation outcome failed because it violated the one-outcome rule and left no independently green milestones.
- Splitting by a single “native” task class failed because real migration work spans rulebook, database, workflow, package, and prose paths. The fix is a tested composite union, not relabeling files.
- Letting M0B exercise real migrations failed because keyed proof did not exist until the later engine milestone. M0C now uses synthetic no-op state transitions and refuses every real apply until M0D.
- Running the 916 rehearsal before merge while binding it to a squash-merge SHA was impossible. It now runs after merge and first proves the merged tree is byte-identical to the reviewed PR head.
- Calling the rehearsal “non-production” because it only read data was wrong. Production capture now requires the full production gate and independent signed approval.
- An unrestricted production dump was too broad. The corrected contract defaults to schema-only and permits only policy-bound, masked, capped fixture queries.
- Filtering platform schemas without rebuilding dependencies made the restore incomplete. M0D now inventories transitive dependencies, installs pinned `vector`/`pgcrypto`, creates data-free `auth.uid()` compatibility behavior, and runs RLS/vector smoke tests.
- Making `seed.ts` import-only before changing package aliases would have broken merged intermediate heads. Existing commands remain functional and guarded until M0E atomically cuts aliases over.
- Assuming `ORACLE_RUN_VECTOR_INDEXES` existed only in `.env.example`, `turbo.json`, and migration 99 missed active macro/decision guidance and immutable migration 48. M0E now updates all active references and hash-pins only the two immutable migration comments.
- Editing the predecessor handoff violated the write-once rule. Those changes were reversed; this successor file carries the new state.
- Reusing the executor-held migration-proof key for reviewer approval could not prove independence. Production authority now comes only from the pinned default-branch approval workflow's GitHub/Sigstore attestation and live revocation checks.
- Treating M0F authorization as a permanent production grant would either over-authorize or block migrations 103–107. The enable field is only a kill switch; every exact merged schema release needs its own attested request and durable four-action run.

## 5. Root causes and key findings

- Jev is best for cheap bounded semantic decisions—Choice, Score, and Noul—not text generation. The first product candidate remains MCP capability search; later candidates include entity ranking, extraction prefiltering, claim-support holds, contradiction screening, Recall triage, retrieval reranking, and answer audit.
- Jev must never own authorization, exact validation, database integrity, approvals, security, or final prose. The plan uses a separate observed decision client and staged shadow evidence.
- Oracle's current raw migration path has ordering, recovery, drift, and proof risks that must be repaired before adding Jev tables. This is why M0 precedes vendor work and Step 1A.
- Production-read and production-write authority are different artifacts. M0E approval cannot authorize M0F.
- A filtered schema restore must close non-data dependencies, not merely create shadow roles.
- Active operator guidance and immutable historical comments need different treatment: update the former, checksum-pin the latter.

## 6. Exact next steps

1. From this branch, run `git diff --check`, verify only the plan plus this successor handoff differ from `origin/main`, and run the Markdown-link check. Success means no errors, no predecessor-handoff diff, and a clean staged scope.
2. Commit/push the corrections, run `ai-task-gates check --before review`, then run `ai-codex-review plan-review --base origin/main --assert-head <full-head-sha>`. Success is explicit APPROVE naming that exact SHA; any rejection must be repaired by class and re-reviewed.
3. After APPROVE, verify remote main has not moved; if it moved, rebase and repeat exact-head review. Then run the ship gate, open a documentation-only PR linked to issue #14, attach it to the Codex task, verify the PR contains only the plan and this successor handoff, and merge immediately with the documentation-only owner override. Success is a merged PR and confirmed main commit.
4. Post a signed issue #14 comment with the amendment PR, merge SHA, approval run/SHA, and “start M0A only”; keep the issue open. Success is an issue comment that contains no secret/data content and does not claim Jev is enabled.
5. A new current-upstream worktree executes **M0A only**: bootstrap the reviewer-safety policy, add/test composite `migration-release`, redeclare/check it before commit/review, and perform no database access. Success is M0A's own exact-head-approved merged PR and STATUS evidence; successors then take one of M0B–M0F each.

## 7. Constraints and gotchas in force

- Use a new current-upstream worktree for every implementation milestone; do not edit the shared local checkout.
- One unproven live outcome per session. Never bundle M0 milestones or a Jev schema step with M0.
- Every M0 milestone uses the full `migration-release` union; a narrow diff does not waive constituent gates.
- M0E production capture occurs only post-merge with independent read approval. M0F uses a separate post-merge write approval. Missing or ambiguous evidence stops before credentials or connection.
- Do not edit this predecessor or any other session's handoff. The session completing M0A may retire this file only after proving the amendment is on main and carrying every open obligation into the plan or its successor handoff.
- Never put secrets, raw company rows, copied message/document/claim bodies, or credentials into artifacts, logs, GitHub, or chat.
- Documentation-only PRs merge immediately after verifying every changed file is prose; issue #14 stays open for implementation.

## 8. Access and environment

- Machine: `916-alien`, Windows 11, PowerShell 7.
- Repository worktree: `C:\Users\ahazan2\.codex\worktrees\jev-plan-final\oracle`.
- Branch: `codex/jev-plan-approval-status`; remote: `github.com/u2giants/theoracle`.
- GitHub CLI and repository push access are working. The exact-head reviewer is available through `ai-codex-review`.
- Secrets belong in 1Password vault `vibe_coding`; only item names/protected pipes may be used. No secret is needed to publish this documentation amendment.
- Production Supabase project is `eqccjfbyrywsqkxxpjvg`; the retired project `vokucjpanhvqunimlvsp` must always be denied.

## 9. Open questions and risks

- Owner decisions: TypeSafe enterprise data terms/data-class allowlist and the recommended $5 cap. Both are consolidated in §0 and block only company-data pilots.
- Until the amendment merges with exact-head approval, implementers must follow the main version and may not use the branch draft as authority.
- The composite gate is intentionally strict. If the installed `ai-task-gates` runtime cannot accept a repository-defined composite, M0A is blocked; repair the public recovery toolkit rather than weakening or simulating the union.
- GitHub Actions artifact retention is 30 days. M0F must verify a current M0E artifact or rerun the separately approved M0E rehearsal; it may not accept prose or a local substitute.
- No subagents were dispatched for this amendment closeout. The predecessor handoff contains the original audit's subagent accounting.

## Self-audit

1. **Can a brand-new developer continue without this chat? Yes.** §§1–3 define the product, goal, exact branch, merged baseline, and unmerged amendment state; §6 gives ordered commands and success gates.
2. **Can they continue as effectively as this session? Yes.** §§4–5 preserve every rejected approach and the non-obvious safety conclusions; §7 preserves the operational constraints.
3. **Is flawless-execution detail present? Yes.** §§3, 6, 7, and 8 identify the exact files, branch, gates, review/merge route, production boundaries, secrets location, and verification outcomes.
4. **Does §0 contain every owner decision from §§1–9? Yes.** The only owner decisions are vendor/data terms and the $5 cap, both listed with recommendations and consequences. The unrelated R2 decisions are explicitly routed to their existing owner handoff.

Checklist result: all sections 0–9 exist; owner decisions are consolidated; current state, failures, findings, exact next steps, constraints, access, and risks are explicit; secrets are location-only; and the predecessor handoff remains untouched. A newcomer can resume at §6 without asking this session a question.
