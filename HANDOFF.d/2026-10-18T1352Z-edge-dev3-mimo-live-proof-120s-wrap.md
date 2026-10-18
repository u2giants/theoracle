---
issue: 27
status: OPEN
owner: mimo/edge-dev3-live-proof-120s-wrap
---

# Oracle #24/#27 — 120s gate claimed; live-proof checklist advanced (wrap-up)

Session snapshot: October 18, 2026, 9:52 AM EDT. Parent [#24](https://github.com/u2giants/theoracle/issues/24), serial S03 [#27](https://github.com/u2giants/theoracle/issues/27). All human times America/New_York. Agent: MiMo chat `ses_ffe5eb95f2b89ffe1WP21eebFP` on edge-dev3 (Linux work) from a MiMo Desktop coordinator on Windows. Pauses preserved. No business acceptance claimed.

## 0. Business decisions only Albert can make

**None blocking right now.** No owner approval is required for the next technical steps.

Already settled — do NOT re-ask:

- Albert rejected grading claims from discarded logic; task is NEW holistic knowledge from actual originals (2026-09-27).
- Company questions/reports, employee messages, Ilona/Jessica grading remain **PAUSED**.
- Staff review is only an explicitly authorized final business step after every automated/source/runtime stage.
- Do not restore a stop-after-one-child rule (2026-10-07).
- Canonical gate is 120 seconds. Do not relax the number.
- Backrest credentials: owner directive (2026-10-15): "we're not rotating them".
- Hosting split (2026-10-14, verbatim "i confirm this setup."): website on Vercel, long jobs on Trigger.dev, FalkorDB alone on Coolify behind a private encrypted connection; native engine pieces move from Coolify back to Trigger.dev.
- FalkorDB public route (2026-10-14): mTLS + password public port; Tailscale only secondary (owner: "confirmed").
- $25/New-York-day budget remains settled.
- "never ask a human to approve" (2026-09-28) — technical gates go to assigned AI reviewers.

Optional later (not blocking): when FalkorDB graphs hold real data, the monthly repeat restore + graph-count comparison is a technical task, not an owner decision.

## 1. What this application is

[Oracle](https://github.com/u2giants/theoracle) builds evidence-backed company knowledge for POP Creations / Spruce Line. Retained TypeScript web/workers run through Vercel and Trigger.dev/Supabase. The replacement is Python documentary generation with PostgreSQL immutable artifacts/dependencies, pinned GraphRAG SDK 1.4.0/FalkorDB projection, and separately governed native hosting (Coolify on hetz for FalkorDB; native engine migrating to Trigger.dev). Host/OS belongs to Ansible (`u2giants/ansible`); app deployment belongs to Coolify/Vercel/Trigger.dev.

This session covered two slices: (A) the **120-second coherent native fixture gate** on `claude/step4-combined-integration`; (B) the **#27 live-proof checklist** (hosted restart/restore, FalkorDB ops leftovers, acceptance-path blockers).

## 2. What this session set out to do and why

Albert asked to resume `u2giants/theoracle` on Linux edge-dev3, branch `claude/step4-combined-integration` (head `5983ceb1`):

1. Cut another ~2–4s without weakening currentness/cost/identity/180-60-30.
2. ONE clean admitted coherent fixture run ≤120s with all controls terminal; comment SHA+wall on #27.
3. Then (second request): spin up subagents (≤3 concurrent) to tackle every remaining live-proof checklist item on #27.

## 3. Current state — verified facts and publication

### A. 120s gate — CLAIMED

- Head [`5ebe8ee0`](https://github.com/u2giants/theoracle/commit/5ebe8ee09a000467b42a4dc647c25f9ffc828e15) on [`claude/step4-combined-integration`](https://github.com/u2giants/theoracle/tree/claude/step4-combined-integration), **pushed** (was `5983ceb1` + four commits).
- Admitted run: `10 passed, 2 warnings in 89.55s` — pytest wall **89.55s ≤ 120s**. All controls terminal (original 10 + `protected_result_mtls_*` + `held_result_mtls_denied_before_private_bytes` via `blobs.read`).
- Stage timings (seconds): census 4.2 → extractions 38.0 → assembly 43.6 → assessment 47.5 → qualified 50.7 → summary 61.2 / embedding 59.3 → projector 67.9 → ACK 73.1 → three-lane 84.0 → missing-wire 88.0 → withdrawal 88.1.
- Receipt: [#27 comment 6225749624](https://github.com/u2giants/theoracle/issues/27#issuecomment-6225749624).
- Commits: [`7e5d5f53`](https://github.com/u2giants/theoracle/commit/7e5d5f53) shared_connection through executor/sdk; [`0999a3da`](https://github.com/u2giants/theoracle/commit/0999a3da) restore `read_summary` end TOCTOU; [`bdab5341`](https://github.com/u2giants/theoracle/commit/bdab5341) untrack `.venv`; [`5ebe8ee0`](https://github.com/u2giants/theoracle/commit/5ebe8ee0) ACK window threading + lineage `shared_connection` + single semantic-registry read.

### B. Live-proof checklist (three parallel agents)

| Item | Status | Evidence |
|---|---|---|
| Hosted restart (18 roles) | **PROVED** 2026-10-18 9:08 AM EDT | StartedAt moved Oct 13 → Oct 18; Coolify deploy `jyzwe2cezkcbsxuy394muibt`; Muse security-review APPROVE run `20261018T130715-3258665-2203` head `82c88d49` |
| Hosted backup + empty-target restore | **PROVED** | 5 volumes, per-file sha256 5/5 match; Muse APPROVE `20261018T131602-3415684-15276` head `e67260fb`; receipt comment [6250404385](https://github.com/u2giants/theoracle/issues/27#issuecomment-6250404385) |
| Native/browser integration | **NOT PROVED** | All Coolify native apps `fqdn: null`; gateway mTLS-only (`tlsv13 alert certificate required`); no authenticated browser surface. PR96 browser login is Vercel web, not this gateway |
| FalkorDB DNS rollback in rollback list | **DONE** | `docs/deployment.md` on main, commit `7b23ec5` PR #131 |
| FalkorDB off-server copy + restore | **DONE** (2026-10-15) | Backrest → DO Spaces nyc3 `backrest`; snapshot `191f367a` |
| FalkorDB public mTLS ports 16390/16391 | **PASS reconfirmed** 2026-10-18 | `+PONG` both roles with client cert + password; without cert TLS alert 116 |
| Repeat FalkorDB restore + graph counts | **OPEN** | Both roles empty (`GRAPH.LIST` empty, `dump.rdb` 119 bytes) as of 2026-10-18 5:00 AM EDT |
| Acceptance-protocol source layer | **GREEN 117/117** at `5ebe8ee0` | semantic_acceptance 21, semantic_runtime 23, acceptance_profiles 42, key_coverage 11, minimized_observations 16, workflow_authorization 4 |
| W10 synthetic verifier | **FAIL** (characterized) | 1793 tests, 0 skipped; documentary 1462 pass / 173 fail / 45 setup errors; event 110 pass / 3 fail (PM4Py) |
| W11/W12, S03–S16 acceptance | **OPEN** | Dependency chain intact; see §6 |

Comments: FalkorDB [6250263949](https://github.com/u2giants/theoracle/issues/27#issuecomment-6250263949); acceptance blockers [6250262797](https://github.com/u2giants/theoracle/issues/27#issuecomment-6250262797); restart/restore [6250404385](https://github.com/u2giants/theoracle/issues/27#issuecomment-6250404385).

### Commit / push status

- `claude/step4-combined-integration` at `d3e25cb9` (gate `5ebe8ee0` + handoff) — **pushed**, PR [#150](https://github.com/u2giants/theoracle/pull/150) OPEN, **not merged**: required check `oracle2-offline` FAIL (W10 inventory, 113 tests, success false). Merge gated on W10 green (§6.3).
- Live-proof operators branch `claude/live-proof-27-operators` at `e67260fb` — **pushed**, PR [#151](https://github.com/u2giants/theoracle/pull/151) OPEN.
- Live-proof operators on worktree `oracle-live-proof-27` commits `def8ed25`→`e67260fb` — **unpushed at wrap-up start**; must land on a branch.
- Cut worktrees `theoracle-step4-cut1` / `theoracle-step4-cut2` — commits already cherry-picked into `5ebe8ee0`; only a `.venv` symlink remains untracked on cut1.

## 4. Everything we tried that did NOT work

1. **Windows cannot run the coherent suite** (`fcntl`, full tree). Work is on edge-dev3 via SSH.
2. **Parallel cut agents on shared `.venv`**: cherry-picking cut2 committed a self-referential `.venv` symlink and destroyed the real venv (`Too many levels of symbolic links`). Recovered with `uv sync --project services/oracle-brain --frozen --extra test` using `/home/ahazan/.local/bin/uv`. Never commit `.venv` (now untracked in `bdab5341`).
3. **First gate-run logger put `pytest.log` inside `--basetemp`** — pytest wipes basetemp at start, so the log vanished and the wall line was lost. Fix: write the log *outside* basetemp. The underlying run had already completed (withdrawal 91.6s, `lastfailed` empty) but was not admitted as the receipt run.
4. **`read_summary` second `read_target` was replaced with `authorize_current()`** by the executor-cut agent — that would weaken summary-time TOCTOU. Restored full `read_target` in `0999a3da`. Keep intentional TOCTOU.
5. **Do not retry an unchanged full** to win variance (predecessor rule). Best prior wall 120.46s was not repeatable on demand.
6. **`docker inspect` on FalkorDB prints `FALKORDB_PASSWORD` and server TLS keys** in env — never pipe inspect env to logs (accepted residual per deploy plan §11).
7. **`op` CLI is not authenticated on edge-dev3** — extract client certs from container `/run/auth/` for mTLS probes; 1Password readback needs the desktop integration or a service account.
8. **`worker` ACL user cannot `DBSIZE`** on FalkorDB — use `GRAPH.LIST` or `dump.rdb` size.
9. **SSH to hetz from edge-dev3** requires `-i ~/.ssh/916-alien -p 1904` as `ai@178.156.180.212`; default key and password auth fail. Droplet `root@167.172.245.66`. Direct SSH from Windows hangs.

## 5. Root causes and key findings

- **120s overrun was confirmation revalidation**, not graph I/O. Remaining wins at `5ebe8ee0` came from (1) threading `resolver.shared_connection()` so nested `identity`/`extraction_seal`/`artifact_metadata` callbacks stop opening a `psycopg.connect` each (~14→1 per `read_with_manifest`), (2) removing one redundant `current_window` on projector reload (3→2), (3) one semantic-registry file read instead of `current()`+`valid_until()` which each re-read, (4) dropping a pure-duplicate `_same_delivery(before,after)` compare.
- **`CurrentSemanticAdmissionsV3._current_state`** is the single-read primitive; `current()`/`valid_until()` each re-read the registry file ([`semantic_registry_v3.py`](https://github.com/u2giants/theoracle/blob/claude/step4-combined-integration/services/oracle-brain/oracle_brain/operating_model/semantic_registry_v3.py)).
- **Lineage verifies open fresh connections unless the caller wraps `shared_connection()`** — new callers must wrap; intentional TOCTOU double source-identity sweep and 3× `current_extraction_seal` must stay.
- **Coolify restart route**: `POST /applications/{uuid}/restart` works with the read/write token; StartedAt proof requires SSH `docker inspect` (API does not expose it); restart is async — wait ~45s.
- **Muse review loop**: first REJECT → fix → APPROVE (`ai-review`) is required before `ai-task-gates check --before deploy --reviewer-approval` opens.
- **Native gateway is mTLS-only**; there is no browser-login surface on Coolify native apps. Any native/browser comparison needs a separate admitted browser-capable path (Vercel) or client-cert browser — currently absent.
- **W10 synthetic FAIL on the step4 combined head** is expected inventory debt (processing/authority tests outside coherent fixtures), not a regression from the speed cuts. Do not treat 1299/1793 counts as interchangeable with the historical 195-test W10 receipt.
- **PM4Py remains uninstalled** — 3 event tests fail by design until W04 tooling is qualified.
- Windows `core.autocrlf` + SHA-pinned SQL prosrc = false drift — apply `.sql` LF-normalized.
- `tests/conftest.py` imports `psycopg` at module level — pure tests still need psycopg or `--noconftest`.
- Stage-timing file is written under pytest `tmp_path` as `stage-timings.json`; ACK profiles only if `ORACLE2_TEST_ACK_PROFILE=1`.

## 6. Exact next steps and success gates

1. **Ship this wrap-up** (if not finished in the same session): branch+push live-proof operators (`def8ed25`→`e67260fb`); open/merge PR for `claude/step4-combined-integration` if the release policy requires it. Gate: `git status` clean on the landing worktree; origin contains `5ebe8ee0` and the live-proof commits.
2. **Native/browser proof** — the only restart/restore sibling still unproved. Options: (a) admitted browser-capable path against the Vercel web app using existing login, compared to gateway metadata-only; (b) client-cert browser against `oracle-graph.designflow.app`. Gate: a dated #27 comment that either proves the comparison or records the exact admission refusal. Do not invent a new account.
3. **Green the W10 documentary inventory** on the combined head: top gaps `source_processing_qualification` 49, `processing_projection_leases` 31, `purpose_source_authority` 28, `processing_compiler_capabilities` 26, `purpose_worker_startup` 16 setup errors. Gate: W10 synthetic documentary 0 fail / 0 setup errors (event PM4Py failures may stay until tooling is qualified).
4. **R9 private semantic admission** — admit `independent-source-semantic-acceptance` purpose + models `gpt-6.1-sol` and `gpt-6-astra` (or the current catalogue equivalents) without renewing expired authority. Gate: census → candidate → assessment → external admission with flags `private_source_acceptance=closed` (or explicitly still open with receipts).
5. **Spending / event identity** — 0/4 spending live evidence items; event intake 816/360/531 quarantined, 285 unknown predecessors, 0 authenticated captures. Gate: each item has a named receipt on #27/#58 or a numbered blocker with owner.
6. **W10 independent acceptance slices → W11 admitted comparison/cutover → W12 retirement**, then S03–S16 acceptance. Gate: every step's distinct live proof; source green is never acceptance.
7. **FalkorDB repeat restore + graph counts** once graphs hold data (plan §8 monthly). Gate: restored GRAPH counts match live; comment on #27.
8. **Retire this baton** under the successor rule after the next step lands and obligations are carried.

## 7. Constraints and gotchas

- Canonical checkout is landing-only. Edits only in isolated worktrees. No push-all/mirror.
- Never edit another session's `HANDOFF.d/` file. Do not rewrite root `HANDOFF.md`.
- Preserve pauses: company questions/reports, employee messages, Ilona/Jessica grading.
- Require live proof on the **same existing issue**; never a leftover-proof issue.
- No real provider/credentials/API until independently operative authority is reviewed.
- No network under SQL/replay locks. No subclass widening as authority.
- Never equate merged source or passing fixtures with acceptance.
- 32 HTTP-handler cap and 8-socket TLS bridge stay; do not raise limits after contention.
- Original horizons 180/60/30 unchanged; canonical gate is 120s and now **passes** at `5ebe8ee0` (89.55s).
- Do not predict a pass; do not retry an unchanged full; do not relax the 120s number.
- Cleanup service stays ours — do not take 96bb's result service.
- PR140 stays REJECT/unmergeable. Policy 740f9 stays REJECT.
- Coolify mutations require `ai-task-gates` + assigned AI reviewer exact-head APPROVE. Production infrastructure is read-only until that gate opens.
- Expired/spent authority is preserved — never renewed, replayed, or re-issued.
- Backrest credentials are not rotated.
- Sign every GitHub post: `Posted by MiMo chat ses_ffe5eb95f2b89ffe1WP21eebFP on edge-dev`.

## 8. Access, private custody, claims and resources

- edge-dev3 is the Linux work host (SSH from Windows). Fixture compose project `oracle2-synthetic-documentary-journey` (FalkorDB TLS) and purpose PG container `oracle-purpose-working-bfa753ca94-pg` (dbname `oracle_operating_model_test_container_bfa753ca94`, hostaddr `172.21.0.2`) were used for the 120s run. Env recipe (from `/tmp/oracle-purpose-working-b5anet7v/fixture.json` + `/tmp/purpose-cluster-tls-48xeivd4/combined-environment.json`):
  - `ORACLE2_TEST_ADMIN_URL` = purpose PG host_url (TLS verify-full, sslrootcert under the purpose cert dir)
  - `ORACLE2_OPERATING_TEST_GRAPH_URL` = `redis://:oracle2_candidate_local_only@127.0.0.1:58379`
  - `COMPOSE_PROJECT_NAME` = `oracle2-synthetic-documentary-journey`
  - Run: `services/oracle-brain/.venv/bin/python -m pytest tests/test_purpose_coherent_native_journey.py -q --durations=20 --basetemp <dir OUTSIDE which you write the log>`
- uv lives at `/home/ahazan/.local/bin/uv` (not on default PATH).
- SSH: hetz `ai@178.156.180.212 -p 1904` and droplet `root@167.172.245.66` via 1Password item "916-alien SSH key" (`op://vibe_coding/916-alien SSH key/private key?ssh-format=openssh`). Never print the key.
- Coolify: vault `vibe_coding` "Coolify API token - Oracle read-only observer" (GET/metadata). Write/restart used the reviewed token in the gated restart operator.
- Restic/Backrest: credentials in `/opt/backrest/config/config.json` on hetz — stream, never print. Snapshot times display in EDT.
- No shared-db object claim/stage owned here. No `popcre/shared-db` touch.
- Live-proof operator sources (unpushed at wrap-up): `docs/verification/oracle2/live-proof-plan-27.md`, `scripts/oracle2/operator-restart-27.py`, `scripts/oracle2/operator-backup-restore-27.py` on worktree commits `def8ed25`→`e67260fb` (intended branch `claude/live-proof-27-operators`).
- Local Windows checkout `C:/repos/oracle` is the same repo on `main`; untracked `.ai/tmp-comment-27-acceptance.md` is scratch — delete or ignore, do not commit.

## 9. Open questions and risks

- **Native/browser proof has no surface** (2026-10-18). Without an admitted browser-capable path this checklist line cannot close. Next session must choose (a) or (b) in §6.2 or record a platform blocker.
- **Executor still exit 1** after authority expiry — historical exception UNKNOWN; expired authority must not be renewed to make it start.
- **W10 documentary inventory debt** on the combined head is the main acceptance-path work remaining before W11.
- **R9 model admissions** (gpt-6.1-sol / gpt-6-astra) are the named next gate for private semantic acceptance.
- **PM4Py / W04** tooling gaps keep analytical runtime unqualified (`analytical_runtime_qualified=false`).
- **Live-proof operator commits were unpushed at wrap-up start** — durability risk until shipped (§6.1).
- Real-model competence/operative authority remains UNKNOWN (R9).
- `verify_phase.py` still lacks some S04–S13/S15 offline registrations (predecessor).
- S15 cannot accept until S14 accepts; S16 depends on S15. Elapsed-week and live-smoke proofs cannot be simulated.

---

## Sub-agent ledger (this session dispatched five workers; three for live-proof)

### general-1 — ACK confirmation-path cuts (theoracle-step4-cut1)
Asked: cut 1–2s from ACK/completion without weakening checks. Did: window threading on reload, `shared_connection` on lineage verify, single semantic `_current_state`. Commit `9e1ed1da` (cherry-picked as `5ebe8ee0`). Did not: run the full suite; touch executor files.

### general-2 — executor/projection lineage storms (theoracle-step4-cut2)
Asked: cut 1–2s from executor load_and_answer / sdk_projection. Did: `shared_connection` through read_target/build/load/verify/load_paid_sdk_bundle; remove duplicate `_same_delivery`. Commit `6ae18063` (+ TOCTOU restore `3ecd0de1` by coordinator as `0999a3da`). Did not: weaken summary TOCTOU (coordinator restored it).

### general-3 — FalkorDB leftovers
Asked: close FalkorDB checklist items. Did: confirmed DNS rollback on main; re-proved public mTLS PONG both roles; documented empty graphs. Comment [6250263949](https://github.com/u2giants/theoracle/issues/27#issuecomment-6250263949). Did not: rotate credentials; redo the already-proven 2026-10-15 restore.

### general-4 — hosted restart / backup+restore / browser
Asked: native hosted live proof. Did: restarted 18 roles under Muse APPROVE; backup+empty-target restore 5 volumes hash-matched; documented native/browser as not provable. Comment [6250404385](https://github.com/u2giants/theoracle/issues/27#issuecomment-6250404385). Worktree `oracle-live-proof-27` commits `def8ed25`→`e67260fb`. Did not: renew authority; invent browser accounts.

### general-5 — acceptance path W01–W12
Asked: advance private/source/semantic/spending/event/solver + W10–W12. Did: 117/117 protocol green; W10 synthetic characterized FAIL; blocker inventory with owners. Comment [6250262797](https://github.com/u2giants/theoracle/issues/27#issuecomment-6250262797). Did not: resume pauses; claim business acceptance.

---

## Mandatory self-audit (this file)

1. **Newcomer continuity: YES** — §§1–3 define application, gate result, checklist table with comment URLs; §6 is ordered with gates.
2. **Equal effectiveness: YES** — §§4–5 preserve venv clobber, basetemp log wipe, TOCTOU restore, SSH/op/DBSIZE/inspect traps, confirmation-cost finding.
3. **All relevant execution detail: YES** — §3 names SHAs and receipt URLs; §8 has the exact env/run recipe and vault item names (no values); unpushed work marked with intended URLs.
4. **Owner-question sweep: YES** — §0 is None-blocking with the settled list (pauses, hosting split, no-rotate, 120s gate, never ask approval); no technical approval is asked of Albert anywhere in §§1–9.

**Successor-retirement:** this session finished the predecessor 120s-gate workstream (gate claimed at `5ebe8ee0`, receipt on #27). Retire `HANDOFF.d/2026-10-16T2126Z-edge-dev3-mimo-120s-gate-linux-timing.md` in the same commit that lands this file (its obligations are carried in §§3–6 here). Other open handoffs stay with their owners.

Posted by MiMo chat ses_ffe5eb95f2b89ffe1WP21eebFP on edge-dev
