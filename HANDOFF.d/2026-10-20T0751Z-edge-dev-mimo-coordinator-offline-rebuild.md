---
issue: 24
status: OPEN
owner: mimo/coordinator-offline-rebuild
---
<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob 058b88002f1c38070d139c57fafaa1b7a828f2fe at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->


# Coordinator offline rebuild — plan STATUS landed; structural rebuild continues

Session snapshot: October 20, 2026, 3:51 AM EDT. Parent [#24](https://github.com/u2giants/theoracle/issues/24), serial S03 [#27](https://github.com/u2giants/theoracle/issues/27), deferred operational review [#58](https://github.com/u2giants/theoracle/issues/58). All human times are America/New_York (EST). Coordinator: MiMo chat `ses_ffe5ea8fec60bffejYJNblx61O` on edge-dev. No background execution promised.

## 0. BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None open that block this workstream.** The owner already decided the important ones.

**Standing order (Albert, 2026-10-19 EDT, verbatim intent) — already published; do NOT re-ask and do NOT violate:**

- Do **not** ask Albert to test the system.
- Do **not** involve employees (no Ilona/Jessica grading, no employee messages, no process-owner reviews of half-built flows).
- Do **not** unpause company questions, reports, or grading.
- Finish the structural rebuild the right way first. Only then, and only when Albert separately says so, run real company work through it.

Published on [issue #27](https://github.com/u2giants/theoracle/issues/27) (body banner) and [issue #24](https://github.com/u2giants/theoracle/issues/24#issuecomment-6280845629). Also in project memory.

**Already settled — do NOT re-ask:**

- 1Password posture: dismiss with Escape/Cancel; type the token; never approve paste (2026-10-19).
- Do not renew expired tickets; a new one-hour window is a re-seal (new timestamps), not a renewal.
- Do not replay spent jobs, resume paused company work, or relax the 120-second ceiling.
- Never ask a human to approve technical actions (owner ruling 2026-09-28). Assigned AI reviewers gate those.
- "POP owns the rights" (Albert, 2026-10-13). No business question is pending on rights.

**Instruct any successor:** put any remaining business questions to Albert in ONE message before starting work. Do not test anything on company/employee time.

## 1. What this application is

[Oracle](https://github.com/u2giants/theoracle) is POP Creations' evidence-backed company knowledge system. Employees interact through chat and document uploads. Workers extract operational claims with quote-level evidence; deterministic validators gate promotion into approved claims; synthesis workers maintain traceable Brain sections. The outcome that matters is explainable business knowledge: every important answer or synthesis artifact must be traceable back to messages, document chunks, or approved claims.

- Repo: [u2giants/theoracle](https://github.com/u2giants/theoracle). Stack: TypeScript web/worker (Vercel/Trigger.dev) + Python documentary operating-model (`services/oracle-brain`).
- Graph: FalkorDB. Dedicated synthetic DBs on S03 Supabase `PRIVATE_REFERENCE_SHA256_620b6d5ddc335d4bd407f56c4e534cd8141fbcb6772483488a0180abbec651dd` (NOT `popcre/shared-db`).
- Broader product (consultant overhaul) is planned but **not fully rebuilt**. S01 offline / S02 synthetic are historical; S03 unaccepted; W01–W12 and S04–S16 gates open.

## 2. What we set out to do this session, and why

Record the session's landed offline work in the three plan STATUS tables and write the session handoff. The offline rebuild produced a burst of merged PRs (#130–#143, #163–#169) covering W-row offline acceptance receipts, S03–S13 building-block leaves, named adversarial tests, R7 suite registration, TLS/SDK close-only proof, and coherent-fixture restricted-answer/ACK. Those facts were on main but not reflected in the plan STATUS tables. This session closes that documentation gap.

## 3. Current state — what is true right now

| Piece | State | Evidence |
|---|---|---|
| **Plan STATUS updates** | **DONE (this PR)** | [plan_oracle_workflow_integrity.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_workflow_integrity.md) W table: W01/W02/W05/W07/W09 offline_accepted=true with links to offline-acceptance-receipt.md and #165; W03/W04/W06/W08/W10/W11/W12 offline progress from #165 noted, not offline_accepted |
| **Consultant overhaul STATUS** | **DONE (this PR)** | [plan_oracle_consultant_overhaul.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_consultant_overhaul.md) S03–S16 rows record building-block leaves and named offline tests; acceptance flags stay false; S14/S15/S16 closed to offline progress |
| **Replacement journey STATUS** | **DONE (this PR)** | [plan_oracle_replacement_documentary_journey.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_replacement_documentary_journey.md) R7 registration covers real surface (#164/#168/#169); TLS/SDK close-only + coherent fixture restricted-answer (#166); remaining gaps U1 e2e, U2–U6 browser, Q2b, R8 |
| **W01/W02/W05/W07/W09 offline accepted** | On main via #165 | [offline-acceptance-receipt.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/oracle2/workflow/offline-acceptance-receipt.md). Private/live/business flags remain false |
| **S03 named adversarial tests** | On main via #163 | §9 (11 tests) + §10 (14 tests) in test_replacement_documentary_journey.py and test_replacement_adversarial_journey_v1.py |
| **S03 R7 suite registration** | On main via #164 | 54 files registered; verify_phase S02–S14/S16 offline; 0 unregistered. Required-skip fix #169 |
| **S03 TLS/SDK close-only + coherent fixture** | On main via #166 | test_replacement_result_tls_sdk_close_v1.py (13 tests); labeled_suggestions restricted-answer; HMAC receipt/attempt-nonce restart |
| **S04–S13 building-block leaves** | On main via #135/#133/#141/#132/#143/#140/#142/#130 | See consultant STATUS rows. Named offline tests + evidence stubs via #167 |
| **W10 restricted-role grants + URI conninfo** | On main via #168 | _as_role() returns postgresql:// URI; test_checkpoint_scope seeds grants |
| **Company/employee work** | Still PAUSED | Standing order |
| **S03 / W01–W12 / S04–S16** | Unaccepted / open | Plan STATUS |
| **Git code this session** | Docs/STATUS only | This PR branch `mimo/status-coordinator-2026-10-20` |

## 4. Everything we tried that did NOT work

This session was documentation-only. No implementation dead ends. Historical dead ends from predecessor sessions that a successor must not repeat:

1. **Renewing an expired ticket.** Expired grants/certificates/job777/403 remain expired without renewal/replay. A new one-hour window is a re-seal (new timestamps only).
2. **Replaying spent jobs.** One Run click only per proof; no blind retry after unknown submission.
3. **Playwright as a proof path.** Forbidden for native acceptance proofs. CUA/CDP input events only.
4. **Pasting the native token.** 1Password paste-confirm. Type only.
5. **Raw SQL UPDATE on change-logged tables without restoring the sealed watermark.** Breaks gateway_view_result.
6. **Treating local/offline verification as delivery or acceptance.** Every private/live/business gate is separate.

## 5. Root causes and key findings

- **Offline acceptance is a distinct flag.** `offline_accepted: true` means offline/synthetic verification obligations are met with linked artifacts. Private, hosted, live, business, and elapsed acceptance flags remain false. Do not conflate them.
- **Building-block leaves are not stage acceptance.** Each S04–S13 leaf is a synthetic building block. The stage gate (business/live/preview) is separate and remains false. See the consultant STATUS rows for each leaf's explicit "Not accepted" remainder.
- **R7 registration ≠ R7 pass.** #164 registered all 54 suites so the verifier covers the real surface. The canonical 120-second timing gate still last completed at 123.12s and needs Linux + FalkorDB + TLS for a full parallel run.
- **Q2b blocks installation/live action, not source fixture work.** Actual target owner/caller/TLS proof is a separate admission prerequisite (source-processing plan §9.1). Source contracts and isolated invented-data fixtures can proceed without it.
- **The 120-second ceiling is unchanged.** All offline work honored it. No deadline increase.

## 6. Exact next steps

1. **Do not ask Albert to test. Do not involve employees. Do not unpause company work.** Gate: standing order on #24/#27.
2. Continue **implementation and acceptance of the rebuild** under parent [#24](https://github.com/u2giants/theoracle/issues/24) and the plan STATUS tables (W01–W12 / S03–S16). Gate: each stage's own offline/synthetic gates first; business acceptance only when Albert separately says so.
3. **U1 raw→SourceRef e2e:** complete raw original→all PNG image parts→same Budget/native wire→independent review→first SourceRef. Gate: named test passes and evidence stub is filled.
4. **U2–U6 browser e2e:** correction/control/cancel/native1..N and actual browser journey. Gate: browser spec passes without skip.
5. **Q2b actual target owner/caller/TLS proof:** separately admitted metadata-only catalog read proving actual pg_proc owner, SECURITY DEFINER flag, search_path, EXECUTE grants, role memberships and target identity. Gate: source-processing plan §9.1 satisfied. This blocks installation/live action only.
6. **R8 combined differing-engine SECURITY review:** exact final combined Oracle SECURITY review of current source before its code PR/merge. Gate: assigned differing-engine reviewer APPROVE on exact head.
7. **R7 timing gate:** full parallel W10 run under 120s on Linux + FalkorDB + TLS. Gate: canonical verifier passes with 0 skips/failures.
8. **S04–S16 implementations behind the named tests:** each building-block leaf needs its stage implementation (workflow/APIs/UI/preview) before business acceptance. Gate: stage evidence stub filled and named tests pass.
9. **W10 factory/design verdicts:** factory remains REVISE, design remains REJECT. Independent acceptance requires private census/evaluator/independent assessment. Gate: external review sandboxes return accepted verdicts.
10. **Business gates:** S15 actual week and S16 retention cannot be simulated. Staff/company questions/reports and discarded-claim grading remain paused until Albert separately says so.

You'll know step 1 held when no session comment asks Albert or Ilona/Jessica for a test or review.

## 7. Constraints and gotchas in force

- Standing order (§0). Company questions/reports, employee messages, grading stay PAUSED.
- Never renew/extend an expired permission row. New one-hour window = re-seal timestamps only.
- Never replay spent jobs. One Run click only per proof.
- Type the native token; never paste; never log/echo it.
- 1Password: Escape/Cancel only; never "OK to paste".
- Playwright is not a bypass for native acceptance proofs. CUA/CDP input only.
- Canonical test ceiling stays 120 seconds.
- `popcre/shared-db` untouched. S03 DB is not shared-db.
- Sign GitHub: `Posted by MiMo chat ses_ffe5ea8fec60bffejYJNblx61O on edge-dev`.
- Technical actions need assigned AI reviewer APPROVE via `ai-task-gates`, never human approval.
- After raw SQL on change-logged tables, restore sealed watermark.
- Never edit another session's HANDOFF.d file. Successor rule: delete a predecessor only when (1) its work is committed+pushed and verified on main, (2) every still-open obligation is carried forward, (3) nothing unique is lost.
- Invented/synthetic only. No company data, no employees, no production.

## 8. Access and environment

- **edge-dev** (Windows). Worktree used: `C:\repos\oracle-worktrees\status-handoff` on branch `mimo/status-coordinator-2026-10-20`.
- GitHub: `u2giants/theoracle`. Authenticated via `gh` CLI.
- Python tests: `cd services/oracle-brain && uv run --extra test pytest -q`. Local Postgres/FalkorDB URLs required for full suite; pure synthetic tests run without them.
- 1Password vault `vibe_coding`. Store secrets there; never in chat.
- Secrets referenced by location only. Never print sealed bundles, tokens, or credentials.

## 9. Open questions and risks

- **R7 timing gap (2026-10-20):** last complete all10-control run was 123.12s, exceeding the 120s ceiling. Full parallel run needs Linux + FalkorDB + TLS. Root decides any measured isolation or assertion-preserving performance change.
- **Q2b unknown target facts (2026-10-20):** actual pg_proc owner, SECURITY DEFINER flag, search_path, EXECUTE grants, role memberships and target identity are UNKNOWN. These block installation/live action. Do not substitute an owner/admin path.
- **Factory/design verdicts (2026-10-20):** W10 acceptance-factory remains REVISE and design remains REJECT per external review sandboxes. Independent private census/evaluator/assessment is open.
- **Building-block leaves are thin (2026-10-20):** each S04–S13 leaf covers a narrow synthetic slice. Stage implementations (workflows, APIs, UI, preview proofs) are absent. Do not treat a leaf as a stage.
- **Predecessor handoffs retained:** [native-v2 run proof](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-20T0103Z-edge-dev3-mimo-native-v2-run-proof.md) and [s03-s16 offline coordination](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-16T1558Z-edge-dev3-claude-s03-s16-offline-coordination.md) both stay. Successor-rule deletion criteria not met (obligations remain open in each).
- **Standing order must survive** any doc cleanup — it lives on #24, #27, and project memory.

## Self-audit (handoff-writer)

1. **Comprehensive for a newcomer?** Yes — §1 app, §2 goal, §3 state table, §4 dead ends, §5 findings, §6 next steps with gates, §7 constraints, §8 access, §9 risks.
2. **As effective as this session?** Yes — offline-accepted vs business-accepted distinction, building-block leaf limits, R7 registration vs timing, Q2b scope boundary.
3. **Every relevant detail?** Yes — all landed PR numbers with links, remaining gaps named (U1, U2–U6, Q2b, R8), standing order, constraints, predecessor retention rationale.
4. **Section 0 complete?** Yes — sweep found no new business decisions; standing order and settled items listed; no technical approvals in §0.
