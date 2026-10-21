---
issue: 27
status: OPEN
owner: mimo/offline-rebuild-implementation
---
<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob 5b1cc52928abcce6c7ac6ff5e50d22e1fbd4d360 at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->


# Offline rebuild implementation — U1–U6, S08/S09/S12 leaves, Q2b tooling, R8 hardening

Session snapshot: October 20, 2026, 9:10 PM EDT (2026-10-21T0110Z UTC). Parent [#24](https://github.com/u2giants/theoracle/issues/24), serial S03 [#27](https://github.com/u2giants/theoracle/issues/27). Coordinator: MiMo chat `ses_ffe5ea6ecab2affelFcTlhtEJB` on edge-dev (session env id was empty; signature used `unknown`). All human times America/New_York (EST).

## 0. BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None open that block this workstream.**

**Standing order (Albert, 2026-10-19 EDT) — already published; do NOT re-ask and do NOT violate:**

- Do **not** ask Albert to test the system.
- Do **not** involve employees (no Ilona/Jessica grading, no employee messages).
- Do **not** unpause company questions, reports, or grading.
- Finish the structural rebuild the right way first. Business acceptance only when Albert separately says so.

Published on [#27](https://github.com/u2giants/theoracle/issues/27) and [#24](https://github.com/u2giants/theoracle/issues/24#issuecomment-6280845629).

**Already settled — do NOT re-ask:**

- 1Password posture: dismiss with Escape/Cancel; type the token; never approve paste (2026-10-19).
- Do not renew expired tickets; a new one-hour window is a re-seal (new timestamps), not a renewal.
- Do not replay spent jobs, resume paused company work, or relax the 120-second ceiling.
- Never ask a human to approve technical actions (owner ruling 2026-09-28). Assigned AI reviewers gate those.
- "POP owns the rights" (Albert, 2026-10-13).

**Instruct any successor:** put any remaining business questions to Albert in ONE message before starting work. Do not test anything on company/employee time.

## 1. What this application is

[Oracle](https://github.com/u2giants/theoracle) is POP Creations' evidence-backed company knowledge system. Employees interact through chat and document uploads. Workers extract operational claims with quote-level evidence; deterministic validators gate promotion into approved claims; synthesis workers maintain traceable Brain sections. Every important answer must be traceable back to messages, document chunks, or approved claims.

- Repo: [u2giants/theoracle](https://github.com/u2giants/theoracle). Stack: TypeScript web/worker (Vercel/Trigger.dev) + Python documentary operating-model (`services/oracle-brain`).
- Graph: FalkorDB. Dedicated synthetic DBs on S03 Supabase `PRIVATE_REFERENCE_SHA256_620b6d5ddc335d4bd407f56c4e534cd8141fbcb6772483488a0180abbec651dd` (NOT `popcre/shared-db`).
- S03 unaccepted; W01–W12 and S04–S16 gates open. Offline building blocks are not stage acceptance.

## 2. What we set out to do this session, and why

Resume the Oracle structural rebuild (main @ [f809258](https://github.com/u2giants/theoracle/commit/f8092583b27c25586caf860b37d419bf88560821)) and finish remaining offline implementation behind the named tests: S03 U1 raw→SourceRef e2e, U2–U6 browser journey, Q2b target-proof tooling, R8 combined security review, and S08/S09/S12 implementation leaves. Verify with `verify_phase.py --mode offline` and keep the W10 120s ceiling unchanged. No employees, no company data, no renewals/replays.

## 3. Current state — what is true right now

| Piece | State | Evidence |
|---|---|---|
| **Integration branch** | Pushed, NOT PR'd, NOT merged | [`mimo/offline-rebuild-integration`](https://github.com/u2giants/theoracle/tree/mimo/offline-rebuild-integration) head `505247e` + defer commit `a18ce99` (workflow file reverted for push) |
| **U1 raw→SourceRef e2e** | DONE offline | SQL `finalize_original_reading_qualification_v1` INSERT-ONCE; `original_qualification_runtime.py`; `test_replacement_original_lifecycle.py` + `test_original_qualification_runtime.py`; evidence `docs/verification/oracle2/U1-raw-sourceref.md` |
| **U2 journey control** | DONE offline | `replacement_journey_v1.py`; SQL journey functions; `test_replacement_journey_control.py` (21) + `test_replacement_job_authority.py` (23); evidence `U2-journey-control.md` |
| **U3–U5 browser journey** | DONE offline | `replacement-workspace.tsx`, `/api/consultant/replacement/v1/*`, `replacement-journey.spec.ts` 7/7 Playwright + 38 TS contract; evidence `U3-U5-browser-journey.md` |
| **U6 registration** | PARTIAL | New suites in `verify_phase.py` S03 + `verify_workflow_integrity.py`; `oracle2-contracts.yml` replacement-contract step DEFERRED (token lacks `workflow` scope) |
| **S08+S12 leaves** | DONE offline | `meetings/{participation,delivery}.py`, `workflows/meeting_turn.py`, `knowledge/product_experience_gate_v1.py`; 23 tests; stubs updated |
| **S09 leaves** | DONE offline | `retrieval/{planner,packing,citations,global_summary,mcp_parity}.py`; 54 tests; stub updated |
| **Q2b tooling** | DONE offline; Q2b gate still OPEN | `q2b_target_catalog_v1.py` + 56 tests; `Q2b-target-catalog-proof.md`; actual target owner/caller/TLS still UNKNOWN |
| **R8 security review** | NOT APPROVED | ~15 Codex security-review rounds; many High/Medium fixed (auth, CSRF, promotion, seals, Ed25519 signer isolation, purpose allowlist). Last review on `4f0e92f` was REJECT; fixes landed in `505247e` but **no APPROVE on that head** |
| **Offline test totals** | GREEN on integration | U1/U2 66 pass 1 skip; S08 23; S09 54; Q2b 56; seal security 17; TS contract 38; `verify_phase.py S12 --mode offline` PASS (`live_accepted: false`) |
| **W10 120s / R7 timing** | OPEN | Needs Linux + FalkorDB + TLS; Windows cannot run (`fcntl`). Last complete all10-control run 123.12s still over ceiling |
| **Business/live acceptance** | CLOSED | Standing order |

**Unpushed-then-pushed note:** branch is on GitHub at `mimo/offline-rebuild-integration`. `.github/workflows/oracle2-contracts.yml` change (adding replacement-contract test step) was reverted in `a18ce99` because the OAuth token lacks `workflow` scope. Re-apply that 2-line step when a workflow-scoped credential exists.

## 4. Everything we tried that did NOT work

1. **Renewing an expired ticket / replaying spent jobs.** Forbidden. Never do this.
2. **Playwright as native-acceptance proof.** Forbidden for native proofs. CUA/CDP only for those.
3. **R8 as a one-shot review.** It was a loop: REJECT → fix → re-review (~15 rounds). Each round found deeper issues (auth, CSRF scheme, promotion authority, ancestor scopes, HMAC forgeability, closure introspection, signer isolation, purpose allowlist). Do not assume one pass is enough.
4. **HMAC / module-level mint tokens / closure-hidden secrets.** Same-process Python can extract `func.__closure__` and import `_MINT_TOKEN`. Real fix was Ed25519 + isolated signer + no mutable registries + purpose allowlist.
5. **Trusting caller-supplied role / `admitted` flags / duck-typed connections.** All forged. Authority must be a signature over the exact action payload from an isolated signer.
6. **Pushing a workflow file with a repo-only OAuth token.** Rejected: needs `workflow` scope. Device-flow refresh requires a human click — not done. Deferred the 2-line CI step instead.
7. **`uv sync` on Windows.** `hnswlib` needs MSVC. Minimal venv (pydantic, pytest, psycopg[binary], Pillow, pypdfium2 + editable oracle-brain `--no-deps`) is the offline path.
8. **verify_phase S03/S08/S09 without DB URLs.** Correctly refuses. Pure pytest was used. Do not invent DB URLs.

## 5. Root causes and key findings

- **Offline acceptance ≠ business acceptance.** Every evidence stub says Not accepted. Do not flip stage gates from leaf tests.
- **No SourceRef until independent qualification.** `source_reading_qualifications` needed INSERT-ONCE via `finalize_original_reading_qualification_v1`; materialize `operating_model_source_receipts` too or `qualifiedSourceRef` never builds.
- **Same-process Python cannot hide a signing key.** Closures, `__closure__`, `gc.get_objects()`, importable names are all reachable. Trust boundary is process/OS. Signer is `__main__`-only with scrubbed env; verify path holds only the public key.
- **Authority = Ed25519 signature over purpose-tagged payload.** No mutable registries. Purpose allowlist in `seal_wire.SEAL_PURPOSE_ALLOWLIST`.
- **Promotion to delivered needs `process-confirm` + qualification/review commit evidence**, not intake scope alone.
- **CSRF same-origin must include scheme** (`http` Origin must not pass for `https` request).
- **Windows skips:** `fcntl` hosting tests, FileBlobStore private-root mode bits. Linux-only cases are documented, not broken.
- **W10 120s run cannot be measured on this host.** Needs Linux + FalkorDB + TLS (`docs/implementation/next-session-120s-gate-linux.md`).

## 6. Exact next steps

1. **Do not ask Albert to test. Do not involve employees. Do not unpause company work.** Gate: standing order on #24/#27.
2. **R8 APPROVE on exact head.** Re-run `ai-codex-review security-review` on the integration head (or a successor commit). If REJECT, fix findings and re-review until APPROVE. Gate: differing-engine reviewer APPROVE recorded on #27. This blocks PR/merge (`ai-task-gates check --before ship` currently STOPs: deployment class needs assigned-ai-reviewer-approval).
3. **Open PR + merge after R8 APPROVE** for `mimo/offline-rebuild-integration` → `main`. Re-apply the 2-line `oracle2-contracts.yml` step when a workflow-scoped credential exists (or via a PR that only touches that file with proper scope). Gate: `gh pr view` MERGED; local-tests green in CI.
4. **W10 / R7 timing gate on Linux:** one admitted fresh coherent native fixture run with all controls terminal in ≤120s, plus `verify_workflow_integrity --stage W10` within the shared 120s deadline. See `docs/implementation/next-session-120s-gate-linux.md`. Do not relax the ceiling. Gate: receipt on #27 live-proof checklist (same issue — never a leftover-proof issue).
5. **Q2b actual target proof** remains OPEN until root selects a target and separately admits a bounded metadata-only catalog read. Tooling is ready (`q2b_target_catalog_v1.py`). Do not substitute an owner/admin path. Blocks installation/live action only.
6. **S08/S09/S12/U3–U5 stage implementations** (live APIs, UI previews, hosted browser) remain open behind the offline leaves. Business acceptance stays closed.
7. **W10 factory/design verdicts** remain REVISE/REJECT. Independent acceptance requires private census/evaluator/assessment.

You'll know step 2 held when the review report's Verdict line is `APPROVE` on the exact SHA you will merge.

## 7. Constraints and gotchas in force

- Standing order (§0). Company questions/reports, employee messages, grading stay PAUSED.
- Never renew/extend an expired permission row. New one-hour window = re-seal timestamps only.
- Never replay spent jobs. One Run click only per proof.
- Type the native token; never paste; never log/echo it.
- 1Password: Escape/Cancel only; never "OK to paste".
- Playwright is not a bypass for native acceptance proofs.
- Canonical test ceiling stays 120 seconds.
- `popcre/shared-db` untouched. S03 DB is not shared-db.
- Sign GitHub: `Posted by MiMo chat <id> on edge-dev` (session env id was empty this session → `unknown`).
- Technical actions need assigned AI reviewer APPROVE via `ai-task-gates`, never human approval.
- After raw SQL on change-logged tables, restore sealed watermark.
- Never edit another session's HANDOFF.d file. Successor rule: delete a predecessor only when (1) its work is committed+pushed and verified on main, (2) every still-open obligation is carried forward, (3) nothing unique is lost.
- Invented/synthetic only. No company data, no employees, no production.
- Seal key material: `ORACLE2_SEAL_PUBLIC_KEY` / `ORACLE2_SEAL_PRIVATE_KEY(_FILE)` / `ORACLE2_SEAL_SIGNER_KEY_FILE` are UNKNOWN until host wiring. Never commit secrets.

## 8. Access and environment

- **edge-dev** (Windows). Integration worktree used: `C:\repos\oracle-worktrees\impl-integrate` (path also resolves as `D:\repos\oracle-worktrees\impl-integrate`) on branch `mimo/offline-rebuild-integration`.
- Other session worktrees (leaf branches, now merged into integration): `impl-u1`, `impl-u2`, `impl-u35`, `impl-s08-s12`, `impl-s09`, `impl-q2b`, `offline-rebuild`. Keep or clean via `cleanup-worktree` only when safe.
- GitHub: `u2giants/theoracle` via `gh` (keyring, https). Token scopes: `gist`, `read:org`, `repo` — **no `workflow`**.
- Python offline tests: minimal venv (pytest, pydantic, psycopg[binary], Pillow, pypdfium2) + `PYTHONPATH=services/oracle-brain` or editable install `--no-deps`. `uv sync` fails on hnswlib/MSVC.
- TS tests: `npx pnpm@9.5.0` or `corepack pnpm`; `apps/web` `tsx --test lib/replacement-contract.test.ts`; Playwright chromium for `replacement-journey.spec.ts`.
- 1Password vault `vibe_coding`. Store secrets there; never in chat.

## 9. Open questions and risks

- **R8 not APPROVED (2026-10-20):** ship gate blocks merge. Last REJECT was on `4f0e92f`; `505247e` has the follow-up fixes but has not been re-reviewed. Risk: another REJECT round.
- **Workflow CI step deferred (2026-10-20):** `oracle2-contracts.yml` missing replacement-contract test registration until a workflow-scoped push is possible.
- **R7/W10 timing gap (2026-10-20):** 123.12s last complete all10-control run still exceeds 120s. Needs Linux + FalkorDB + TLS. Root decides any measured isolation or assertion-preserving performance change.
- **Q2b UNKNOWN target facts (2026-10-20):** actual pg_proc owner, SECURITY DEFINER, search_path, EXECUTE grants, role memberships, target identity remain UNKNOWN. Blocks installation/live action.
- **Factory/design verdicts (2026-10-20):** W10 acceptance-factory REVISE, design REJECT.
- **Building-block leaves are thin:** stage implementations (workflows, APIs, UI, preview proofs) remain absent or fixture-only. Do not treat a leaf as a stage.
- **Predecessor handoffs retained:** `2026-10-20T0751Z-edge-dev-mimo-coordinator-offline-rebuild.md` (documentation/STATUS landing) and `2026-10-20T0103Z-edge-dev3-mimo-native-v2-run-proof.md` still hold open obligations (U1–U6/Q2b/R8 were those obligations — largely advanced here, but R8/W10/Q2b-target remain open). Successor-rule deletion of the 0751Z baton is NOT done in this commit because its obligations are not all proven on main yet.
- **Standing order must survive** any doc cleanup — it lives on #24, #27, and project memory.

## Part (b) — sub-agent ledger (coordinator session)

This session dispatched explore + general sub-agents. None held `popcre/shared-db` claims. Summary per agent:

| Agent | Asked to do | Actually did | Branch / commit | Worktree | Deliberately not done |
|---|---|---|---|---|---|
| explore-1 | Map U1–U6 named tests | Full gap map (missing qualification INSERT, journey SQL, browser stub) | n/a (read-only) | offline-rebuild | — |
| explore-2 | Map S08/S09/S12 leaves | Hold-branch + test/stub map | n/a | offline-rebuild | — |
| explore-3 | Map Q2b/R8/W10 gates | Q2b §9.1 facts, R8 method, W10 Linux constraint | n/a | offline-rebuild | — |
| general-1 | S08+S12 leaves | Ported modules, 23 tests, stubs | `1bbb2fb` `mimo/s08-s12-leaves` | impl-s08-s12 | Live meeting/UI |
| general-2 | S09 leaves | 5 modules, 54 tests | `443d6c6` `mimo/s09-leaves` | impl-s09 | Live MCP server |
| general-3 | U1 raw→SourceRef | SQL finalize + runtime + 18 tests + registration | `e6db823` `mimo/u1-raw-sourceref` | impl-u1 | Browser/native |
| general-4 | Q2b catalog tooling | Reader + 52 tests; Q2b stays OPEN | `082a6fe` `mimo/q2b-catalog-proof` | impl-q2b | Actual target read |
| general-5 | U2 journey | (failed mid-run APIError) | — | impl-u2 | — |
| general-7 | Finish U2 | Completed U2, 62 tests | `da37290` `mimo/u2-journey-control` | impl-u2 | Live mTLS |
| general-6 | U3–U5 browser | UI/API/spec 7/7 + 11 contract | `98f11cc` `mimo/u3-u5-browser` | impl-u35 | Hosted screenshots |
| general-8 | Verify integration | 230 pass / 13 skip; no fix needed | clean | impl-integrate | — |
| general-9..28 | R8 finding fixes | Multiple security hardening commits through `505247e` | on integration branch | impl-integrate | Final APPROVE |

Failed agent: general-5 (APIError) and general-16 (APIError); work resumed by general-7 and general-17 respectively.

## Self-audit (handoff-writer)

1. **Comprehensive for a newcomer?** Yes — §1 app, §2 goal, §3 state table, §4 dead ends, §5 findings, §6 next steps with gates, §7 constraints, §8 access, §9 risks, part (b) agents.
2. **As effective as this session?** Yes — R8 loop lessons, seal/Ed25519 design, Windows venv, workflow-scope push failure, Q2b boundary all recorded.
3. **Every relevant detail?** Yes — commits, branches, test counts, deferred CI step, standing order, predecessor retention.
4. **Section 0 complete?** Yes — no new business decisions; standing order and settled items listed; no technical approvals in §0.

Four-question audit: (1) yes — §0–§9 + part (b) cover continuation; (2) yes — dead ends and seal design included; (3) yes — next steps have verification gates; (4) yes — §0 has only business items, technical gates stay in §6/§9.
