---
issue: 24
status: OPEN
owner: claude/s03-s16-offline-coordination
---

# Oracle #24 offline source sweep — S03–S16 lanes landed, live proof still required

Session snapshot: October 16, 2026, 11:58 AM EDT. Parent [#24](https://github.com/u2giants/theoracle/issues/24), serial S03 [#27](https://github.com/u2giants/theoracle/issues/27), deferred operational review [#58](https://github.com/u2giants/theoracle/issues/58). All human times are America/New_York. Coordinator: Claude chat `ses_ffe5ebb2fc73fffeFM6mGmAJE2` on edge-dev3. Cap honored: at most 3 concurrent subagents. Pauses preserved. No live proof claimed. No PR/merge/deploy/install/production/DB action. No background execution promised.

## 0. Business decisions only Albert can make

**None — nothing in this workstream currently needs a business decision from Albert.**

Already settled, do not re-ask (from the predecessor baton §0 and plan STATUS):
- Albert rejected grading claims from discarded logic. The task is NEW holistic knowledge from actual originals with complementary workflow/process/handoff evidence, genuine contradiction and missing information (settled 2026-09-27).
- POP owns the source rights; that does not renew processing grants.
- Company questions/reports, employee messages and Ilona/Jessica grading remain **PAUSED**.
- Staff review is only an explicitly authorized final business step after every possible automated/source/runtime stage.
- Do not restore a stop-after-one-child rule (owner ruling October 07, 2026, 9:37 AM EDT: "Those have to be removed from everywhere, permanently.").
- No expired grants/certificates are renewed or replayed.

Technical blockers (OS authentication for toolkit install, Vercel 403 metadata GET, missing real-model/issuer authority) are AI-owned or exact external blockers — never asks for Albert.

## 1. What this application is

[Oracle](https://github.com/u2giants/theoracle) builds evidence-backed company knowledge for POP Creations / Spruce Line. Retained TypeScript web/workers run through Vercel and Trigger.dev/Supabase. The replacement is Python documentary generation with PostgreSQL immutable artifacts/dependencies, pinned GraphRAG SDK 1.4.0/FalkorDB projection, and separately governed native hosting. Host/OS belongs to Ansible; app deployment belongs to its managed platform/Coolify. Source, local invented-provider fixtures, real-model understanding, installation, deployment, business acceptance and elapsed use are separate facts.

Read [AGENTS.md](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [consultant plan STATUS](https://github.com/u2giants/theoracle/blob/main/plan_oracle_consultant_overhaul.md), [workflow plan STATUS](https://github.com/u2giants/theoracle/blob/main/plan_oracle_workflow_integrity.md), and the [replacement plan STATUS](https://github.com/u2giants/theoracle/blob/main/plan_oracle_replacement_documentary_journey.md). The replacement plan is the sole detailed integration addendum; do not create another plan/issue/handoff to split unfinished work.

## 2. What this session set out to do and why

Albert asked to pull latest main, resume from the [replacement coordination baton](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-16T0101Z-edge-dev3-codex-replacement-coordination.md), and **coordinate subagents through all of #24 (max 3 concurrent), first verify untested cleanup, preserve pauses, require live proof.**

Technical objective: (1) prove or finish the untested result-cleanup WIP; (2) push offline source progress on every remaining S03–S16 child without merging, deploying, or claiming acceptance; (3) keep pauses and live-proof discipline.

Current main at session start/finish: [`b08be97`](https://github.com/u2giants/theoracle/commit/b08be978be547edfe929e07de75d351c8f444186).

## 3. Current state — verified facts, publication and the whole job

### Untested cleanup — VERIFIED then finished (successor step 3)

WIP head [`657ccc4`](https://github.com/u2giants/theoracle/commit/657ccc41898f18adb21c001fb0026ebcd031d91c) on `codex/oracle-qualified-read-boundary`: existing 7 cleanup tests **passed** at first verification. Eight required negatives were then added (slowbody, queuedexpiry, lateexception, constructor, revoked-during-close, hold, confirmation + post-close positive): **15/15 pass** at [`dd5827a`](https://github.com/u2giants/theoracle/commit/dd5827a) on [`verify/untested-result-cleanup`](https://github.com/u2giants/theoracle/tree/verify/untested-result-cleanup). Broader result suite 47 pass. TLS/SDK close-only component **still open** (needs real TLS binary + DB fixtures; Windows-blocked).

### Offline source landed this session (pushed branches, no PR/merge)

| Lane | Branch / head | Tests | Notes |
|---|---|---|---|
| Cleanup negatives | [`verify/untested-result-cleanup`](https://github.com/u2giants/theoracle/tree/verify/untested-result-cleanup) `dd5827a` | 15/15 | Step 3 negatives |
| Raw native provider | [`codex/oracle-step5-raw-native-pdf`](https://github.com/u2giants/theoracle/tree/codex/oracle-step5-raw-native-pdf) `757aaef` | 23 new / 137 focused | Quote Budget + all-view PNG controls |
| S04 revision/withdrawal | [`claude/s04-source-lifecycle`](https://github.com/u2giants/theoracle/tree/claude/s04-source-lifecycle) `60be12d` | 15/15 | Pure versioning + tombstones |
| V3 1..4096 + SQL014 | [`codex/step6-v3-population-sql014`](https://github.com/u2giants/theoracle/tree/codex/step6-v3-population-sql014) `405b019` | 79 pure; 26/26 paid-join | SQL014 still UNSHIPPABLE |
| U1–U6 offline | [`codex/step7-u1u6-offline-pure`](https://github.com/u2giants/theoracle/tree/codex/step7-u1u6-offline-pure) `92bfd94` | 25/25 | Policy draft **unreviewed, not authority** |
| Step4 Phase A+B | [`claude/step4-combined-integration`](https://github.com/u2giants/theoracle/tree/claude/step4-combined-integration) `1ce38d6` | AST 25/25 | 22-file recon complete; combined run NOT ready |
| S05 confirmation | [`claude/s05-confirmation-admission`](https://github.com/u2giants/theoracle/tree/claude/s05-confirmation-admission) `2bfcdaa` | 20/20 | |
| S06 interview/chat | [`claude/s06-interview-learning`](https://github.com/u2giants/theoracle/tree/claude/s06-interview-learning) `2ee8dd1` | 20/20 | |
| S07 invited meetings | [`claude/s07-invited-meeting`](https://github.com/u2giants/theoracle/tree/claude/s07-invited-meeting) `9890bbd` | 15/15 | |
| S08 participation | [`claude/s08-meeting-participation`](https://github.com/u2giants/theoracle/tree/claude/s08-meeting-participation) `35e9097` | 45/45 | |
| S09 connected answers | [`codex/oracle-s09-connected-answers`](https://github.com/u2giants/theoracle/tree/codex/oracle-s09-connected-answers) `924d644` | 30/30 | |
| S10 industry expertise | [`s10-industry-expertise`](https://github.com/u2giants/theoracle/tree/s10-industry-expertise) `e8f33a6` | 30/30 | **PR140 remains REJECT/unmergeable** |
| S11 recommendations | [`claude/s11-recommendation-feedback`](https://github.com/u2giants/theoracle/tree/claude/s11-recommendation-feedback) `c80b2a1` | 257/257 | |
| S12 product experience | [`claude/s12-product-experience`](https://github.com/u2giants/theoracle/tree/claude/s12-product-experience) `3f00c64` | 10/10 | Completeness gate refuses unaccepted upstream |
| S13 recovery | [`claude/s13-recovery-offline`](https://github.com/u2giants/theoracle/tree/claude/s13-recovery-offline) `abde036` | 11/11 | |
| S14 migration | [`claude/s14-historical-migration`](https://github.com/u2giants/theoracle/tree/claude/s14-historical-migration) `426dd8f` | 27/27 | `verify_phase.py S14` wired |
| S15 adoption | [`claude/s15-adoption-offline`](https://github.com/u2giants/theoracle/tree/claude/s15-adoption-offline) `914149f` | 14/14 | |
| S16 retirement | [`s16-retire-offline`](https://github.com/u2giants/theoracle/tree/s16-retire-offline) `5b30fc7` | 17/17 | `verify_phase.py S16` wired; never authorizes deletion |

**Nothing is merged to main. No acceptance. No live proof. No deployment.**

### Combined native run — NOT ready (successor step 4)

Phase A merged cleanup+raw on `claude/step4-combined-integration`. Phase B reconciled all 22 conflicting files one closed class at a time (18 took 96bb whole-file state; 4 kept S03 ours including `_ResultOwnedLoopV1` cleanup). 96bb fixture modules landed as 8 new files with holdNoBlob on `blobs.read`. Blockers: Linux suite (Windows lacks `fcntl`), fresh 001..014 install, collision/target/TLS proof, root exact combined approval, canonical **120s gate still FAILS** (historical 123.12s / 128.29s incomplete — no timing prediction is a pass).

### R0–R9 / U1–U6 / S03–S16 — still open for acceptance

Every W01–W12 and S03–S16 **acceptance** obligation remains open on #27/#58 under #24. Offline source is not acceptance. The baton's R0–R9 table and U1–U6 browser ledger still govern; this session added offline pieces only. Live checklist stays on the same existing issues (never a leftover-proof issue).

### External blockers preserved (do not retry)

- Toolkit install: OS authentication external block; installed manifest remains old; no GUI loop.
- Vercel metadata GET: terminal `HTTP 403`; action spent; no retry.
- Policy 740f9: DeepSeek REJECT retained; new draft at [`docs/implementation/oracle-closed-disposable-test-policy-draft-v2-unreviewed.md`](https://github.com/u2giants/theoracle/blob/codex/step7-u1u6-offline-pure/docs/implementation/oracle-closed-disposable-test-policy-draft-v2-unreviewed.md) is **unreviewed, not authority**.

## 4. Everything we tried that did NOT work

1. Full `uv sync` of oracle-brain on Windows fails building `hnswlib` (needs MSVC). Workaround: minimal venv + `PYTHONPATH` + stubs for `fcntl`/`graphrag_sdk` for pure tests only. Do not "fix" production for Windows.
2. Docker daemon not running; WSL has no distribution. Linux suite cannot run here.
3. Naive merge of 96bb fixture branch into 657 line conflicts on 22 files — required closed-class reconciliation (done in Phase B), not hunk blending.
4. Taking 96bb's `replacement_result_service_v1.py` would erase cleanup — forbidden overlay; kept S03 `_ResultOwnedLoopV1`.
5. holdNoBlob must patch `blobs.read`, not `blob.get` (the 128.29s failure used `.get`).
6. SQL migrations on Windows check out CRLF; PostgreSQL then stores CRLF `prosrc` and SHA-pinned body guards falsely report drift. Apply `.sql` **LF-normalized**.
7. Two subagents hit transient `APIError` mid-run (SQL014 fixtures, S09). Resumed via follow-up send rather than respawn; both completed.
8. `verify_phase.py` only accepted S02/S03 at session start; S14 and S16 are now wired. S04–S13/S15 offline phase gates still absent.

## 5. Root causes and key findings

- Cleanup WIP (`6f15a86`→`657ccc4`) is real deadline/settlement/current-tuple work; the 8 negatives now prove it. TLS/SDK close-only is the remaining step-3 gate.
- `codex/oracle-qualified-read-boundary` (657) is the correct base for raw-native; `purpose-native-fixtures-v2` (96bb) lacks raw host modules but is the correct fixture/SDK checkpoint.
- `sdk_projection.py` is byte-identical on e78 and 96bb — take exact 96bb copy.
- WIP SQL014 strict paid-row join is intentional: reading/review commits require prior `register_original_paid_response_v1` with matching `authorized_phase_commit_hash`; reader/reviewer need distinct `model_id`s.
- PR140 remains genuine REJECT; later local repair has no same-reviewer verdict.
- `knowledge/admission.py` already existed as unused `admit_document`; S05 confirmation rules live beside it.
- Pure DTO precedent: `StrictRecord` (`extra='forbid', strict=True, frozen=True`).
- `tests/conftest.py` imports `psycopg` at module level — pure tests still need psycopg installed or `--noconftest`.
- Windows `core.autocrlf` + SHA-pinned SQL prosrc = false drift (see §4.6).

## 6. Exact next steps and success gates

1. **Linux combined proof (step 4).** On edge-dev3/Linux, run the reconciled `claude/step4-combined-integration` suite: fresh 001..014, original 10 controls + protected_result_mtls + held_result_mtls_denied_before_private_bytes, within **120s**. Gate: terminal ALL controls in one admitted coherent run; resources retired or honestly UNKNOWN. No timing predictions.
2. **TLS/SDK close-only for cleanup (step 3 remainder).** Real TLS/SDK close-only component + retained 75 controls on exact head. Gate: root reads diff.
3. **Raw native SQL/observer/Budget component (step 5 remainder).** Local TLS/HTTP/SQLBudget; fees/unknown liability; all-view omission/substitution/remoteURL/textbase64/revoke/expiry. Gate: actual first SourceRef via late distinct reviewer — still source-only invented keys.
4. **SQL014 ship decision (step 6).** Independent source review of 405b019 lineage; no partial migration shipment. Gate: assigned reviewer verdict + fresh-target install proof.
5. **Browser U1–U6 (step 7).** Assigned review of the unreviewed policy draft BEFORE any policy code or blocked DB action. Gate: real upload→correction→new version→scoped confirmation→cited answer; no 503/metadata sold as ready.
6. **Combined SECURITY/normal PR (step 8).** Only after real current gates. Gate: exact merged head + independently admitted real public-invented model/account/coverage/Budget/pricing/terms/observer/issuer/custody/runtime target, then cold/warm/restart/withdraw on the SAME #27 live checklist.
7. **S04–S16 acceptance order (step 9).** Use the pushed offline branches without merging rejected drafts. Gate: every deliverable has genuine runtime/business/elapsed evidence (S15 real week, S16 retention). Never close parent after one child.
8. **Retire this baton only under the successor rule** after the next step lands and obligations are carried.

## 7. Constraints and gotchas

- Canonical checkout is landing-only. Edits only in isolated worktrees. No push-all/mirror (private review evidence in shared object DB).
- No destructive overwrite of foreign worktrees/branches. Counts are not deletion authority.
- Preserve pauses: company questions/reports, employee messages, Ilona/Jessica grading.
- Require live proof on the **same existing issue**; never a leftover-proof issue.
- No real provider/credentials/API until independently operative authority is reviewed.
- No network under SQL/replay locks. No subclass widening as authority.
- Never equate merged source or passing fixtures with acceptance.
- 32 HTTP-handler cap and 8-socket TLS bridge stay; do not raise limits after contention.
- Original horizons 180/60/30 unchanged; canonical gate is 120s and currently FAILS.
- Sign every GitHub post: `Posted by Claude chat ses_ffe5ebb2fc73fffeFM6mGmAJE2 on edge-dev3`.
- PR140 stays REJECT/unmergeable. Policy 740f9 stays REJECT. Policy draft v2 is unreviewed only.

## 8. Access, private custody, claims and resources

No credential values in this file. Use existing protected references and the secrets skill before any real value/file operation; serialize vault access. Predecessor private inventory `S03-20261016-closeout-private-index-v2` and its durable private evidence archive remain LOCAL ONLY in preserved owner worktree custody — root coordinator has the locator; no portable private cloud archive was proved. S03 retained one isolated PG fixture (idle, not retired). Historical foreign orphan readonly ACL remains UNKNOWN. No shared-db object claim/stage owned here. OS authentication is an external block; no known sudo vault item.

## 9. Open questions and risks

- Canonical **120s FAIL** is unexplained beyond known fixture cost; do not predict a pass (2026-10-16).
- Real-model competence/operative authority UNKNOWN (R9).
- Windows host cannot execute the full suite; all "pass" counts above are pure/fixture unless noted SQL on disposable PG.
- Two subagent APIErrors occurred (2026-10-16) and were resumed; treat mid-run agent death as recoverable via send.
- `verify_phase.py` still lacks S04–S13/S15 offline registrations.
- S15 cannot accept until S14 accepts; S16 depends on S15. Elapsed-week and live-smoke proofs cannot be simulated.
- Toolkit install remains partial; do not relabel old/spent authority.

---

## Part (b) — sub-agent lane ledger (coordinator used ≤3 concurrent)

| Lane | Asked to do | Did | Deliberately did not | Worktree/branch |
|---|---|---|---|---|
| Cleanup negatives | Finish step-3 negatives | 8 new tests; 15/15 | TLS/SDK close-only | `verify/untested-result-cleanup` `dd5827a` |
| V3/SQL014 | Step-6 propagation | V3 worker path + paid-join fixtures; 8 failures cleared | Migration ship; live journey | `codex/step6-v3-population-sql014` `405b019` |
| Raw native | Step-5 path | Provider/factory + quote Budget; 23 tests | Real API; SQL observer complete | `codex/oracle-step5-raw-native-pdf` `757aaef` |
| S04 | #28 offline piece | Revision/withdrawal 15/15 | Browser/live proof | `claude/s04-source-lifecycle` `60be12d` |
| U1–U6 | Step-7 offline | Lifecycle+DTOs 25/25; policy draft unreviewed | Policy code; DB action | `codex/step7-u1u6-offline-pure` `92bfd94` |
| Step4 map+Phase B | Combine source | Map + 22-file recon + fixtures | Combined run; 120s claim | `claude/step4-combined-integration` `1ce38d6` |
| S05 | #29 offline | Confirmation admission 20/20 | Live temporal acceptance | `claude/s05-confirmation-admission` `2bfcdaa` |
| S06 | #30 offline | Consent/outbound/evidence 20/20 | Employee messages | `claude/s06-interview-learning` `2ee8dd1` |
| S07 | #31 offline | Invitation/consent gate 15/15 | Meeting join | `claude/s07-invited-meeting` `9890bbd` |
| S08 | #32 offline | Receipts/idempotency 45/45 | Actual meeting | `claude/s08-meeting-participation` `35e9097` |
| S09 | #33 offline | Retrieval modes 30/30 | Company questions | `codex/oracle-s09-connected-answers` `924d644` |
| S10 | #34 offline | Rights/freshness/provenance 30/30 | Merge PR140 | `s10-industry-expertise` `e8f33a6` |
| S11 | #35 offline | Recommendation contract 257/257 | Real business report | `claude/s11-recommendation-feedback` `c80b2a1` |
| S12 | #36 offline | Completeness gate 10/10 | Full UI/visual proof | `claude/s12-product-experience` `3f00c64` |
| S13 | #37 offline | Recovery primitives 11/11 | Staging DR exercise | `claude/s13-recovery-offline` `abde036` |
| S14 | #38 offline | Migration contracts 27/27 | Shadow migration | `claude/s14-historical-migration` `426dd8f` |
| S15 | #39 offline | Cohort/cutover DTOs 14/14 | Production adoption | `claude/s15-adoption-offline` `914149f` |
| S16 | #40 offline | Retirement checklist 17/17 | Governed retirement | `s16-retire-offline` `5b30fc7` |

### Mandatory self-audit (this file)

1. **Newcomer continuity: YES** — §§1–3 define application, goal, published branches and open gates; §6 is ordered with gates.
2. **Equal effectiveness: YES** — §§4–5 preserve Windows/SQL/overlay/reject dead ends and findings; §3 records unfinished gates explicitly.
3. **All relevant execution detail: YES** — §3 table names every branch/head; §7 constraints; §8 private custody limitation; no credential values; no machine-local paths in URL fields (worktree paths appear only as local execution context and every durable ref is a GitHub URL).
4. **Owner-question sweep: YES** — §0 is None with settled list; no technical approval is asked of Albert anywhere in §§1–9 or part (b).

**Successor-retirement of the predecessor baton FAILS** (`2026-10-16T0101Z-edge-dev3-codex-replacement-coordination.md`): its source is on unmerged branches, not verified on `main`. It is kept. Its open obligations are carried in this file §§3,6,7,9.
