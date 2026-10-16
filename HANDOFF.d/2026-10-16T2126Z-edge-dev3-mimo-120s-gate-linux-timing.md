---
issue: 27
status: OPEN
owner: mimo/edge-dev3-120s-gate-linux-timing
---

# Oracle #24 step 4 — Linux 120s native fixture gate: confirmation path sped up, gate NOT claimed

Session snapshot: October 16, 2026, 5:26 PM EDT. Parent [#24](https://github.com/u2giants/theoracle/issues/24), serial S03 [#27](https://github.com/u2giants/theoracle/issues/27). All human times are America/New_York. Agent: MiMo chat `ses_ffe5eba5726bdffeIHFZ2IQNEP` on edge-dev3 (Linux). Work executed on edge-dev3 in an isolated worktree of `claude/step4-combined-integration`. Pauses preserved. No live proof claimed. No PR/merge/deploy/install/production/DB structural action. No background execution promised. No sub-agents dispatched.

## 0. Business decisions only Albert can make

**None — nothing in this workstream needs a business decision from Albert.**

Already settled, do not re-ask (from predecessor batons and plan STATUS):

- Albert rejected grading claims from discarded logic. The task is NEW holistic knowledge from actual originals (settled 2026-09-27).
- Company questions/reports, employee messages and Ilona/Jessica grading remain **PAUSED**.
- Staff review is only an explicitly authorized final business step after every possible automated/source/runtime stage.
- Do not restore a stop-after-one-child rule (owner ruling October 07, 2026, 9:37 AM EDT: "Those have to be removed from everywhere, permanently.").
- No expired grants/certificates are renewed or replayed.
- Canonical gate remains 120 seconds. Do not relax the number.

Technical blockers and remaining proof gaps are AI-owned or exact external blockers — never asks for Albert.

## 1. What this application is

[Oracle](https://github.com/u2giants/theoracle) builds evidence-backed company knowledge for POP Creations / Spruce Line. Retained TypeScript web/workers run through Vercel and Trigger.dev/Supabase. The replacement is Python documentary generation with PostgreSQL immutable artifacts/dependencies, pinned GraphRAG SDK 1.4.0/FalkorDB projection, and separately governed native hosting. Host/OS belongs to Ansible; app deployment belongs to its managed platform/Coolify.

This session's narrow slice: the **native coherent fixture suite** under `services/oracle-brain/tests/test_purpose_coherent_native_journey.py` — one admitted invented-provider journey with three rich originals, census → three extractions → assembly → assessment → qualified model → summary+paid embedding → graph ACK → protected executor answer → result mTLS → missing-wire denials → withdrawal. The canonical product gate is that this suite finishes with every control terminal in **≤120 seconds**.

Read [AGENTS.md](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [consultant plan STATUS](https://github.com/u2giants/theoracle/blob/main/plan_oracle_consultant_overhaul.md), [workflow plan STATUS](https://github.com/u2giants/theoracle/blob/main/plan_oracle_workflow_integrity.md), and the [replacement plan STATUS](https://github.com/u2giants/theoracle/blob/main/plan_oracle_replacement_documentary_journey.md). Do not create another plan/issue/handoff to split unfinished work.

## 2. What this session set out to do and why

Albert asked to resume `u2giants/theoracle` on main and perform **only the Linux timing work** from [`docs/implementation/next-session-120s-gate-linux.md`](https://github.com/u2giants/theoracle/blob/main/docs/implementation/next-session-120s-gate-linux.md):

1. Profile the ACK/completion path (paid embedding wire, graph ACK, compiler reload) and name the dominant cost with evidence.
2. Speed that stage without weakening currentness, cost, identity, or the 180/60/30 horizons.
3. Fresh 001..014 target; keep every original 10 control plus `protected_result_mtls_*` and `held_result_mtls_denied_before_private_bytes` (`blobs.read`, not `blob.get`).
4. ONE admitted run under 120s with all resources retired or honestly UNKNOWN.

Worktree from [claude/step4-combined-integration](https://github.com/u2giants/theoracle/tree/claude/step4-combined-integration) (head `1ce38d6` at session start). Local commits only until the gate passes; then normal PR — never push to protected main. Pauses preserved. No live proof outside the same issues.

## 3. Current state — verified facts, publication and the whole job

### Environment used

- Linux host edge-dev3 (not Windows). The suite needs `fcntl` and the full dependency tree.
- Isolated worktree at session-owned path on edge-dev3, branch `claude/step4-combined-integration`.
- Reused the still-running purpose synthetic PostgreSQL fixture container and the `oracle2-synthetic-documentary-journey` FalkorDB compose project (TLS). Fresh migrations `001_foundation.sql` … `014_replacement_source_custody.sql` applied LF-normalized.
- `uv sync --project services/oracle-brain --frozen --extra test` succeeded on edge-dev3.

### What now works (verified)

The coherent native suite **runs end-to-end and passes**: `10 passed` with every control terminal, including original 10 + `protected_result_mtls_*` + `held_result_mtls_denied_before_private_bytes`.

Two Phase-B interface gaps were blocking any run and are fixed in commit `e389b126`:

1. `purpose_population(..., source_texts=…)` / `processing(..., reading=…, original_sha256=…)` — the coherent journey and `RICH_SOURCE_TEXTS` required the 96bb fixture API that was not on this head.
2. `processing_writer` / `processing_reader_scope` / `retire_processing_reader` in [`dev/oracle2/test_readonly_graph_fixture.py`](https://github.com/u2giants/theoracle/blob/claude/step4-combined-integration/dev/oracle2/test_readonly_graph_fixture.py) — landed as the pure 96bb superset (step4 file had no unique lines).

### Timing results (evidence)

| Run | pytest wall | Last stage | Notes |
|---|---|---|---|
| Baseline complete (all controls) | 139.66s | withdrawal 138.2s | before speedups |
| **Best observed** | **120.46s** | withdrawal 118.99s | at the line |
| Typical after speedups | 121.4–124s | withdrawal ~119.9s | reliable band |

**Canonical 120-second gate: NOT claimed.** Typical wall is ~1.5–4s over. No timing prediction is a pass.

Stage-timing JSON (written under pytest `--basetemp` as `stage-timings.json`) from a representative complete run after speedups:

- `census_committed` ~3.9s → `three_extractions_committed` ~42s → `qualified_model_committed` ~60s
- `compiler_summary_committed_without_second_projection` ~76s (parallel with `native_embedding_committed` ~70s)
- `protected_projector_settings_loaded` ~89s → `protected_graph_ack_committed` ~97s (**ACK itself ~8–12s after settings**)
- three-lane join `protected_graph_ack_and_compiler_restart` ~114s
- `raw_read_direct_compile_and_summary_refused_missing_paid_proof` ~120s → `withdrawal_denies_cached_graph_summary_and_answer` ~120s

### Dominant cost (named with evidence)

**Not the graph write.** cProfile of `project_paid_projector_event_v3` shows `sdk_projection.build` ≈ 6.5s while `current_window` / `authority_window_v3` / `_validate_qualified_current` / `_verify_final_assembly_lineage` / `authority_adapter._check` dominate the ACK window. The overrun is **confirmation revalidation**: repeated full lineage verifies, observer challenge exchanges, source-horizon proofs, and role/ACL catalogue checks — invoked many times per attempt.

### Commit status

- Local commit **`e389b126`** on `claude/step4-combined-integration` (ahead of `origin/claude/step4-combined-integration` `1ce38d6`). **Not pushed, no PR** (gate not passed; original instruction was local commits until gate).
- Intended GitHub URL once pushed: https://github.com/u2giants/theoracle/commit/e389b126 and https://github.com/u2giants/theoracle/tree/claude/step4-combined-integration
- Timing receipt posted on [#27](https://github.com/u2giants/theoracle/issues/27#issuecomment-6221967247). Live-proof checklist item remains unchecked on that same issue.

### Files changed in `e389b126` (7 files)

- `dev/oracle2/test_readonly_graph_fixture.py` — 96bb `processing_writer` / reader scope / retire (suite would not import without this).
- `services/oracle-brain/tests/test_purpose_source_authority.py` and `test_source_processing_qualification.py` — `source_texts` / `reading` / `original_sha256` population API.
- `services/oracle-brain/oracle_brain/operating_model/authority_adapter.py` — `_check` role/ACL facts in one current-catalogue round-trip (same assertions); `shared_connection()` for nested identity/seal checks.
- `services/oracle-brain/oracle_brain/hosting/paid_projector_v3.py` — one attempt window threaded through build/custody; `still_current()` for in-attempt guard callbacks; lighter construction-end expiry/appointment check. Full observer/source proof remains at attempt start and LAST before graph work.
- `services/oracle-brain/oracle_brain/hosting/purpose_journey_v2.py` — `_source_horizon(connection=…)`; shared connection across before/after horizons and custody_window_v3; `assert_source_current` after successful dispatch (pre-dispatch `authorize` unchanged; exception-path `authorize` unchanged).
- `services/oracle-brain/tests/purpose_journey_fixture_delivery.py` — opt-in `ORACLE2_TEST_ACK_PROFILE` cProfile hooks around project/reload (default off).

### S03–S16 / R0–R9 acceptance — still open

Every W01–W12 and S03–S16 **acceptance** obligation remains open on #27/#58 under #24. Offline source and this timing work are not acceptance. Live checklist stays on the same existing issues.

### External blockers preserved (do not retry)

- Toolkit install: OS authentication external block.
- Vercel metadata GET: superseded by PAT in 1Password (see predecessor baton §8) but this session did not need it.
- Policy 740f9 remains REJECT; policy draft v2 remains unreviewed, not authority.

## 4. Everything we tried that did NOT work

1. **Windows host cannot run the suite** (`fcntl`, full tree). Work was moved to edge-dev3 via SSH. WSL has no distro; Docker Desktop missing on the Windows machine.
2. **Phase B left the combined suite unrunnable** — `purpose_population` lacked `source_texts`; `processing_writer` missing from graph fixture. Fixed by porting the pure 96bb/fixture-branch APIs. Do not treat this as product change.
3. **Overlap missing-wire denials with the three-lane positives** (thread around `after_positive`): the denials finished earlier but DB contention made the three-lane slower; net wall worse (127s). Reverted. Do not re-try concurrent DB-heavy negatives against the same fixture PG without measuring.
4. **Fold function-signature catalogue LATERAL into the combined `_check` SELECT**: SQL slower and briefly broke (`InvalidSchemaName` on `b`/`srcbind` alias in `jsonb_agg`). Restored the standalone signature query.
5. **`SourceRoleBinding.check_rows` + binding subquery in the same SELECT**: alias/timestamp issues; reverted to `check(conn)` as a second statement.
6. **Shared connection around `_validated_summary_parent_v3`**: wall got worse (132s). Reverted.
7. **Unchanged full re-runs do not land under 120s.** Variance on edge-dev3 is several seconds (load avg ~2.6). Best 120.46s was real but not repeatable on demand. Do not predict a pass; do not retry an unchanged full.

## 5. Root causes and key findings

- **The ACK/completion overrun is confirmation cost, not graph I/O.** `sdk_projection.build` is a minority of the ACK window. `current_window` historically ran a full `custody_window_v3` (itself 2× `authority_window_v3`, each with observer + 2× `_source_horizon`) and was invoked several times per attempt plus on every projector guard callback.
- **`CurrentPaidProjectorGuardV3.__call__` / `valid_until` each called `current_window()`** — a full storm per guard tick during projection build. Now `still_current()` (config/appointment file hashes + expiry) with full proof retained at attempt start and before graph work.
- **`_check` was ~10 SQL statements per call** and ran twice per `identity()` plus many times per lineage verify. Batching role facts into one current-catalogue statement is the same checks, fewer round-trips. Catalogue function-signature batching was already done earlier ("catalogue batching already helped once").
- **Nested `psycopg.connect` per callback** was a large share of wall time (hundreds of connects in one summary path). `ProcessingSourceResolver.shared_connection()` reuses one connection for nested identity/seal checks; each call still `_check`s.
- **`_verify_final_assembly_lineage` double source-identity sweep** (start + "changed during serving checks") and 3× `current_extraction_seal` are intentional TOCTOU. Keep them.
- **Horizons 180/60/30 unchanged.** No cache that skips a real check. No new authority.
- **Windows `core.autocrlf` + SHA-pinned SQL prosrc = false drift** — apply `.sql` LF-normalized (inherited gotcha).
- **`tests/conftest.py` imports `psycopg` at module level** — pure tests still need psycopg or `--noconftest`.
- Stage timing file is written under pytest `tmp_path` as `stage-timings.json`; ACK profiles only if `ORACLE2_TEST_ACK_PROFILE=1`.

## 6. Exact next steps and success gates

1. **Push `e389b126` (and the handoff commit) on `claude/step4-combined-integration`.** No PR until the 120s gate is honestly met or the owner asks for a PR of the speed work alone. Gate: `git status` clean; `origin/claude/step4-combined-integration` contains `e389b126`.
2. **Find another ~2–4s without weakening currentness/cost/identity/horizons.** Promising remaining cuts (measure before and after; no unchanged re-runs):
   - Further reduce `current_window` call count in the ACK path (count invocations per attempt; thread or narrow remaining duplicates that are not the intentional LAST-before-graph proof).
   - Make `_verify_final_assembly_lineage` / `valid_until` share one connection via the already-added `shared_connection` (guard `__call__` is wired; check every other call site).
   - Examine `sdk_projection.load`/`verify` and executor `load_and_answer` (~14s three-lane) for redundant lineage storms.
   - Only if profiling says so: the approved three-lane C/D/E concurrent fixture at `96bb55f` patterns already partially present (`run_readonly_delivery_fixture_tasks`); keep 32-handler cap and 8-socket TLS bridge; do not take 96bb's result service.
3. **One clean admitted run:** fresh 001..014, original 10 controls + `protected_result_mtls_*` + `held_result_mtls_denied_before_private_bytes` (`blobs.read`), terminal ALL, wall ≤120s, resources retired or honestly UNKNOWN. Gate: pytest reports `10 passed` in ≤120s on the exact head; record SHA + wall in a comment on [#27](https://github.com/u2giants/theoracle/issues/27) (same issue — never a leftover-proof issue).
4. **If the stage cannot be made fast enough without weakening a check, say so with numbers** — that is a real result (already partially done in [#27 comment](https://github.com/u2giants/theoracle/issues/27#issuecomment-6221967247)).
5. **Then** normal PR of the combined SECURITY/normal source path only after real current gates (see predecessor baton §6 steps 6–9). Do not ship SQL014. Do not deploy. Do not resume pauses.
6. **Retire this baton** under the successor rule after the next step lands and obligations are carried.

## 7. Constraints and gotchas

- Canonical checkout is landing-only. Edits only in isolated worktrees. No push-all/mirror.
- Never edit another session's `HANDOFF.d/` file. Do not rewrite root `HANDOFF.md`.
- Preserve pauses: company questions/reports, employee messages, Ilona/Jessica grading.
- Require live proof on the **same existing issue**; never a leftover-proof issue.
- No real provider/credentials/API until independently operative authority is reviewed.
- No network under SQL/replay locks. No subclass widening as authority.
- Never equate merged source or passing fixtures with acceptance.
- 32 HTTP-handler cap and 8-socket TLS bridge stay; do not raise limits after contention.
- Original horizons 180/60/30 unchanged; canonical gate is 120s and currently FAILS on typical wall.
- Do not predict a pass; do not retry an unchanged full; do not relax the 120s number.
- Cleanup service stays ours — do not take 96bb's result service.
- PR140 stays REJECT/unmergeable. Policy 740f9 stays REJECT.
- Sign every GitHub post: `Posted by MiMo chat ses_ffe5eba5726bdffeIHFZ2IQNEP on edge-dev3`.

## 8. Access, private custody, claims and resources

- No credential values in this file. Synthetic compose passwords are fixed loopback fixtures already in `dev/oracle2/compose.yaml` and the purpose fixture; do not copy them into docs.
- 1Password vault `vibe_coding` holds `Vercel Personal Access Token` if Vercel metadata is needed — `op read` piped into headers only, never argv/chat. This session did not read it.
- No shared-db object claim/stage owned here. No `popcre/shared-db` touch.
- Purpose synthetic PG and FalkorDB compose project may still be running on edge-dev3 from this session's fixtures; they are disposable synthetic stores. S03 retained an isolated PG fixture historically (idle, not retired) — see predecessor baton §8.
- Vercel access was resolved 2026-10-16 (predecessor baton §8); not used here.

## 9. Open questions and risks

- **Canonical 120s FAIL is ~1.5–4s on typical wall** after speedups (best 120.46s). Unexplained residual is mostly confirmation cadence plus environment variance on edge-dev3. Do not predict a pass (2026-10-16).
- Real-model competence/operative authority UNKNOWN (R9).
- Local commit `e389b126` is **unpushed** on edge-dev3 worktree — durability risk until step 6.1 lands.
- `verify_phase.py` still lacks S04–S13/S15 offline registrations (predecessor).
- S15 cannot accept until S14 accepts; S16 depends on S15. Elapsed-week and live-smoke proofs cannot be simulated.
- Toolkit install remains partial; do not relabel old/spent authority.
- Missing-wire / three-lane concurrency caused DB contention in one experiment; treat concurrent fixture SQL as a measurement question, not a free win.

---

## Mandatory self-audit (this file)

1. **Newcomer continuity: YES** — §§1–3 define application, goal, branch/head, tables of timings, and open gates; §6 is ordered with gates.
2. **Equal effectiveness: YES** — §§4–5 preserve Windows/Phase-B/overlap/signature-SQL/shared-summary dead ends and the confirmation-cost finding; §3 records unpushed commit and unclaimed gate.
3. **All relevant execution detail: YES** — §3 names every changed file and the receipt URL; §7 constraints; §8 custody; no credential values; unpushed work marked with intended GitHub URLs.
4. **Owner-question sweep: YES** — §0 is None with settled list; no technical approval is asked of Albert anywhere in §§1–9.

**Successor-retirement of predecessor batons:** not attempted. `2026-10-16T1558Z-edge-dev3-claude-s03-s16-offline-coordination.md` and `2026-10-16T0101Z-edge-dev3-codex-replacement-coordination.md` remain OPEN for the broader S03–S16/acceptance workstream; this file only covers step-4 timing. Their open obligations stay with them (and are restated in §6 where they gate this slice).
