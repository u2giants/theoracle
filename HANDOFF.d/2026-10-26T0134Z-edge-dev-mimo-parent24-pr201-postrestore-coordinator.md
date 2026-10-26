---
issue: 24
status: OPEN
owner: mimo/parent24-pr201-postrestore-2026-10-25
---

# Parent24 after PR201 post-restore 503 fix: workspace journey green; recommendation fixture and Muse full-head APPROVE left; coordinator to finish #24

Record owner: MiMo chat on edge-dev (session `ses_ffe5e8a856ffcffeHv7dfknx7E`). Observations rechecked October 25, 2026, approximately 7:00 PM–9:35 PM EDT (America/New_York). Dated observations, not transferable authority. Program is NOT complete. No company use, production adoption, or parent closure is claimed. Business-acceptance hold remains.

## 0. Business decisions only the owner can make

**No new business question is outstanding.** Continue every permitted structural and invented-data obligation before requesting company use. Then present the entire genuine business-question list together, once.

**Already settled — do NOT re-ask:**
- October 22, 2026: "Remain in force until withdrawn" for previously approved immutable assertion/version/scope (PR182 / #29).
- October 23, 2026: "muse and deepseek are working fine as reviewers" — session-scoped routing. Muse used this session (multiple SOURCE+ONE runs).
- Closeout/resume/completion handoffs are not permission for company use.

Nothing else in this workstream needs the owner. Every remaining item is technical (AI reviewer gates, fixture data, proof completion).

## 1. What this application is

The Oracle ([u2giants/theoracle](https://github.com/u2giants/theoracle)) is POP Creations' evidence-backed company consultant. Replacement: isolated Python/PostgreSQL/FalkorDB/GraphRAG operating model with protected mTLS boundaries. STATUS-first sources: [plan_oracle_consultant_overhaul.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_consultant_overhaul.md) and [parent #24](https://github.com/u2giants/theoracle/issues/24), plus the four companion plans on `main`. Closeout of record (NOT retired): [2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md). Prior baton (on branch): [2026-10-25T2335Z-edge-dev-mimo-parent24-pr200-pr201-s07-wrap.md](https://github.com/u2giants/theoracle/blob/codex/parent24-mimo-wrap-20261025/HANDOFF.d/2026-10-25T2335Z-edge-dev-mimo-parent24-pr200-pr201-s07-wrap.md). Earlier: [2026-10-25T1400Z-edge-dev-mimo-parent24-s07-pr201-approve.md](https://github.com/u2giants/theoracle/blob/codex/parent24-mimo-s07-pr201-approve/HANDOFF.d/2026-10-25T1400Z-edge-dev-mimo-parent24-s07-pr201-approve.md).

## 2. What we set out to do this session, and why

Resume parent #24 from main `4e365535`. Named next action: isolate which of the six `_processing_model_admission_v1` sub-checks fires on the post-restore `action(a,'Read current knowledge',0)` (expected 200, got 503), fix only that cause (prefer Python/test binding over sealed SQL 017), get one-shot green past restore-a, Muse re-review the delta, finish the journey. Keep real Teams producer UNQUALIFIED.

## 3. Current state — what is true right now

### 3.1 PR201 post-restore 503 — FIXED and workspace journey GREEN

Root cause was **NOT** an admission sub-check. Temporary diagnostic SQL (never pushed) named the six checks. Check6-revoked fired on the OUTER admission (`f15190c9`/equivalent) — that was the expected pre-journey deny after the line-210 revoke of the outer `h['aid']`. The actual post-restore failure was `ConnectionError: Error connecting to localhost:44407` from redis — the owned graph TLS tunnel `BoundedSemaphore(8)` exhausted during the multi-recipient journey. Graph URL port matched (44407).

**Fix delta** on PR [#201](https://github.com/u2giants/theoracle/pull/201) branch `codex/parent24-s11-compose-01a16013`, head [`77b78c5b`](https://github.com/u2giants/theoracle/commit/77b78c5baad0f96796394e4590d1b9e49488996c):

| Commit | What |
|---|---|
| [`87d3e442`](https://github.com/u2giants/theoracle/commit/87d3e442c5f64e4e6d123c7611a26d6ae5aa50a3) | Widen graph TLS tunnel slots 8→32; schema bootstrap reuse |
| [`0a036f4e`](https://github.com/u2giants/theoracle/commit/0a036f4ed6eb1c500c7eea055c815e2a44bfc68e) | Pin schema inventory digest in-DB (Muse M3) |
| [`070343cd`](https://github.com/u2giants/theoracle/commit/070343cdc8209793446457ea837725f293b0162a) | Harden pin guard + TLS backlog (Muse C1/C2/H4) |
| [`a2cdf6c6`](https://github.com/u2giants/theoracle/commit/a2cdf6c64d4c4a52ed0aa06ea57dd7d80aa4d8ab) | Surface TLS overflow; thread-start leak (Muse L1) |
| [`3404bcff`](https://github.com/u2giants/theoracle/commit/3404bcff83923e46ff50353579d9a866b55245f1) | Runner root from `__file__`; STOP on scratch exists (Muse H1) |
| [`77b78c5b`](https://github.com/u2giants/theoracle/commit/77b78c5baad0f96796394e4590d1b9e49488996c) | `waitFor` on recommendation source option (Muse critical) |

**Verified on head `77b78c5b`:** `workspace_next_recipients_sql_v1` **9 tests, 0 failures, 0 errors, 0 skipped**. Journey receipt written: `action-8: 200` (restore-a Read current knowledge), `action-6/10/11: 503` (disable-a and revoke-a deny), `all_requests_original_window: true`, `page_errors: []`. Response counts `[4, 7]` for the two recipients.

Sealed SQL 017 is **unchanged**. Real Teams producer stays **UNQUALIFIED**.

### 3.2 Recommendation suite — RED (pre-existing fixture gap)

`test_recommendation_next_auth_browser_v1` fails at `recommendation-next-auth-proof.ts:44`: `waitFor` on the option matching `/^baseline: 12\.5 /` times out — the measurement-source option **never renders**. Not a timing race. The label format in [recommendation-controls.tsx](https://github.com/u2giants/theoracle/blob/77b78c5baad0f96796394e4590d1b9e49488996c/apps/web/app/consultant/recommendations/recommendation-controls.tsx#L101) is `{phase}: {amount} {currency} {unit}, {period} · …`. Either `view.measurement_sources` is empty in the fixture or the label text does not match. This is fixture data / setup in `test_recommendation_next_auth_browser_v1.py`, outside the post-restore 503 cause. The one-shot runner expects both suites green (`expected 0/0/0`).

### 3.3 Muse — REJECT on full head (pre-existing PR findings)

Muse SOURCE+ONE run `d20261026T011641-2963573-8366` REJECT at `3404bcff`. Later heads not re-reviewed. Blocking items on the **whole PR** (not the 503 delta):
- Recommendation suite red (see 3.2) — Muse treats both suites as one flagship proof.
- [s11-actual-next-proof-plan.md](https://github.com/u2giants/theoracle/blob/codex/parent24-s11-compose-01a16013/docs/verification/oracle2/s11-actual-next-proof-plan.md) misdescribes the change (claims invented-auth-service unchanged; claims no package/workflow source changed).
- Procedural gates (`natural_unblock`, unsigned `/tmp` receipt) leak.
- W10 registration with no W10-fit evidence; `measure-s11-setup-batch-01.py` still hardcodes root.
- Mediums: graph password in `result.json`; sealed-digest fail-open for deletions; Playwright browser preflight gap; browser TLS overclaimed (`ignoreHTTPSErrors`).

### 3.4 Prior state that still holds

- **S07 W10 two clean full runs** at main `4e365535` (run 40030632154 attempts 1 and 5, 5472/0). Create-child stable for that head. Business acceptance false.
- **PR200** ([#200](https://github.com/u2giants/theoracle/pull/200)) DONE: Muse SOURCE+ONE APPROVE at `3d5314a6`, 21 SQL green, one-shot journey (stage 0a UNPROVEN fail-closed, cleanup proven). **PR still open — not merged.**
- **PR201 lock path-scope fix** APPROVE at `978cb89f`; sticky `_cleanup_unknown` fix at `5f7d34bc`; admission-window insert-time fix at `ecec0ff3`.
- **PR207 / PR210** still open branches (S07 plan v5 / diagnostics). Do not delete.
- **PR211** handoff PR open (`bin/ai-doc-safety` missing).
- Real Teams producer **UNQUALIFIED**. Business-acceptance hold remains.

### 3.5 What is NOT done

- PR201: recommendation suite green (fixture data); Muse VERDICT APPROVE on full 40-char head; then one-shot EXIT 0 both suites.
- PR200 merge (APPROVE + 21 SQL + one-shot done; PR open).
- PR207 / PR210 land or close with branch kept.
- S12 nine-case Next/AuthSDK proof.
- Tool1988 / doc-safety recovery.
- Writer-cut implementation.
- S14–S16 comparison/adoption/retirement (business hold).
- Remaining S03–S16 product/semantic/host qualifications from the closeout ledger.

## 4. Everything we tried that did NOT work

1. **Assumed the SQL admission sub-check was the cause.** Dump ruled out expiry/revocation/operation/hash on the two recipient admissions; check6-revoked fired on the OUTER admission (expected pre-journey deny). Do not chase admission identity again.
2. **Broken diagnostic SQL** (`current_setting( role)` unquoted) died during setup with `UndefinedColumn`. Quote `current_setting('role')`.
3. **PowerShell heredoc / inline Python** over SSH gets parsed by PowerShell (`ParserError: Missing '('` after 'IF'). Ship scripts as base64 and decode on edge-dev3.
4. **Listener swallows backend exceptions** (`except Exception: self._deny()`). Temporary `BACKEND_DENY` print (never pushed) was required to see `ConnectionError` / DIAG messages.
5. **Graph TLS tunnel `BoundedSemaphore(8)`** silently `raw.close()`s overflow → redis `Error connecting to localhost:44407`. Widen slots AND `listen` backlog; count overflow.
6. **Schema bootstrap across two pytest processes** hit `DuplicateTable` (per-process `_RECEIPTS` cache). Adoption path must verify landmarks + inventory pin, never self-compare inventory.
7. **Vacuous inventory guard** (`_inventory_digest(files)!=inventory`) compared a value to itself — Muse Critical. Use `to_regclass` + single-row pin table + `ORDER BY LIMIT 2` and require `len==1`.
8. **`scratch.mkdir(exist_ok=False)`** without moving prior scratch aside raises `FileExistsError` traceback (not STOP). Runner now STOPs cleanly; still move scratch aside before re-runs.
9. **Recommendation `sourceOption.count()` without `waitFor`** looked like a race; `waitFor(15s)` proved the option never appears — fixture data gap, not timing.
10. **Diagnostic commits** (`ecc7c4c6`, `7409f4a3`, `1000d4b3`, `f81898a0`, `888f7cc7`) were left local-only on edge-dev3 and not pushed. Clean fix branch is `pr201-fix-graph-bootstrap` @ `77b78c5b`.

## 5. Root causes and key findings

- Post-restore 503 cause: **owned graph TLS tunnel slot exhaustion**, not `_processing_model_admission_v1`. Evidence: BACKEND_DENY `ConnectionError: Error connecting to localhost:44407`; graph-url pin in answer-0/answer-1 is port 44407.
- `_processing_model_admission_v1` raises ONE message for six checks. Name them with temporary DIAG SQL (never push sealed 017). Check6-revoked on the outer admission at line 210 of [test_connected_answer_sdk_sql_v1.py](https://github.com/u2giants/theoracle/blob/77b78c5baad0f96796394e4590d1b9e49488996c/services/oracle-brain/tests/test_connected_answer_sdk_sql_v1.py#L210) is expected (outer `h['aid']` revoked before the journey).
- [owned_graph_tls](https://github.com/u2giants/theoracle/blob/77b78c5baad0f96796394e4590d1b9e49488996c/dev/oracle2/test_graph_tls_fixture.py) is a test-only loopback tunnel. Production `gateway.py` already uses 32. Fixture semaphore + `listen` backlog must match.
- [bootstrap_canonical_test_schema](https://github.com/u2giants/theoracle/blob/77b78c5baad0f96796394e4590d1b9e49488996c/dev/oracle2/test_canonical_schema.py#L156) has a per-process `_RECEIPTS` cache. Cross-process reuse must adopt via landmarks (017/024/025 tables) + single-row inventory pin in `oracle2._test_schema_inventory`.
- `_catalog` hashes `pg_proc` only — no table DDL. The inventory pin covers table content drift.
- Next.js `installedForEmployeeV1` uses the recipient index when `ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE` is set. `current()` falls back to `readInstalledConnectedAnswerBinding()` if the binding is not in `recipientBindingOriginsV1`.
- `ignoreHTTPSErrors: true` in browser proofs is an overclaim versus the plan's "trust only the owned fixture CA bundle".
- Muse SOURCE+ONE reviews the **whole PR head**, not just the fix delta. Pre-existing PR findings block APPROVE even when the named gate is green.

## 6. Exact next steps

**Next session is a COORDINATOR. Spin subagents for independent workstreams; keep verification and Muse gates at coordinator level.**

1. **Recommendation fixture (subagent A).** Find why `view.measurement_sources` is empty or mis-labeled in `test_recommendation_next_auth_browser_v1` / the advice fixture. The option must render as `baseline: 12.5 …` matching `/^baseline: 12\.5 /`. Fix fixture data or label binding only. Gate: `test_recommendation_next_auth_browser_v1` passes (`1 passed`).
2. **Muse pre-existing findings (subagent B).** Fix plan misdescription in [s11-actual-next-proof-plan.md](https://github.com/u2giants/theoracle/blob/codex/parent24-s11-compose-01a16013/docs/verification/oracle2/s11-actual-next-proof-plan.md); redact graph password from `result.json`; harden measure script root; name `ignoreHTTPSErrors` as a weakening. Gate: no Critical/High on those items in the next Muse run.
3. **Muse SOURCE+ONE on the new head (coordinator).** `ai-review muse plan-review --detach --assert-head <full-40-char-sha>`. Gate: `VERDICT: APPROVE <full-head>`.
4. **One-shot both suites (coordinator).** PATH includes `/home/ahazan/.local/bin`, python `/tmp/pglast-venv-20261023/bin/python3`, runner `scripts/oracle2/run-s11-next-multiemployee-proof-01.py`. Move scratch aside first. Gate: EXIT 0; both suites 0 F/E/S; `EXACT_OWNED_CLEANUP True`.
5. **PR200 merge** when Albert wants it — APPROVE + 21 SQL + one-shot are done. Keep real Teams producer UNQUALIFIED.
6. **S12 / Tool1988 / writer-cut / S14–S16 / closeout ledger.** Continue remaining S/U/W. Do not stop at the repairs.

You'll know step 1 worked when the option count is 1 and the suite is green. Step 3: `VERDICT: APPROVE <full-head>`. Step 4: one-shot EXIT 0.

## 7. Constraints and gotchas in force

- Canonical checkout is landing-only. Every write task gets its own current-upstream worktree. Branch + PR, never push to protected main. Commit identity `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve all safety gates and the separate business-acceptance hold. No company originals, production, paid providers, real meetings, or POP shared-db writes from Oracle work.
- W10 SAME shared 120s / ten workers / per-request ≤30 / full mandatory population / 0 F/E/S/timeout/launch/cleanup. No case cuts or budget raises.
- Do not suppress strict framing/currentness, refresh original windows, or resend uncertain claims. UNKNOWN never equals drained or done.
- Never apply a two-dot old-head diff that would delete current-main files. True three-way merge for recovery integrations.
- Observation week: `ai-review --detach`, read with `ai-review outcome`. Full 40-char `--assert-head` SHAs only. Muse invocation: write launcher as `.sh`, run via Git `bash.exe` to dodge PowerShell `ChildProcess.kill`.
- Do not delete open PR branches (200/201/207/210). Do not delete other sessions' worktrees or handoff files.
- Invoke edge-dev3 runners with `/tmp/pglast-venv-20261023/bin/python3` and `PATH` including `/home/ahazan/.local/bin`.
- Windows host cannot honestly run `os.getuid`/`O_PATH`/`mkfifo`/hnswlib suites. Linux (edge-dev3) is the source of truth for Docker/SQL proofs.
- Move leftover scratch dirs aside before reruns. Receipt files are operator-minted JSON outside scratch.
- PowerShell corrupts SSH heredocs and inline Python. Ship scripts as base64.
- Sealed SQL 017 is unchanged in this delta — do not weaken fail-closed for genuine integrity failures.

## 8. Access, tools, environment

- Machine edge-dev (Windows), authenticated personal GitHub `u2giants/theoracle`. edge-dev3 (Linux) via SSH BatchMode; Docker works there.
- Muse SOURCE+ONE used successfully all session. DeepSeek/Codex/Claude/Gemini/Qwen/Grok not used.
- edge-dev3 worktree: `/tmp/oracle-parent24-wy02uT/pr201-s11` (branch `pr201-fix-graph-bootstrap` @ `77b78c5b`, pushed to `codex/parent24-s11-compose-01a16013`). Runners/receipts under `/tmp/oracle-parent24-wy02uT/`.
- Windows: `C:/repos/oracle` is landing-only main (do not edit). Prior worktrees under `C:/tmp/`.
- Secrets: none appeared this session except ephemeral synthetic test-fixture passwords (invented FalkorDB/history logins, regenerated per run). 1Password vault `vibe_coding` only if needed.
- Shared-db: no POP shared-db claims this session.

### Part (b): session activity blocks

**Coordinator (this session).** Read named baton + prior batons + SQL 017. Isolated post-restore 503 via temporary DIAG SQL + listener prints (never pushed). Fixed graph TLS slots + schema adoption + runner/H1 + recommendation waitFor. Drove workspace suite to 9/0/0/0. Muse REJECT on full head (pre-existing PR findings + recommendation fixture). Did NOT: green the recommendation suite, obtain Muse APPROVE, merge any PR.

No subagents were dispatched this session.

## Mandatory self-audit

1. **Yes** — §1–2 define application and mission; §3 binds heads, the green workspace journey, the red recommendation suite, and Muse state with GitHub URLs; §6 gives ordered next steps with gates; §4 records dead ends; §7–8 preserve constraints and custody.
2. **Yes** — §3 records exact HEADs and Muse run IDs; §5 captures graph TLS exhaustion, schema adoption, and admission-check findings; part (b) states no subagents.
3. **Yes** — goals §2; delivery §3; failures §4; findings §5; next steps §6; constraints §7; access §8; risks in §3.5/§6. Full S01–S16/W/U criteria remain in the closeout handoff and plan STATUS.
4. **Yes** — §0 contains only the continuing business hold and the two settled rulings. Every other approval is technical (Muse SOURCE+ONE / W10). No outside business judgment found in §1–§9.

Posted by MiMo chat ses_ffe5e8a856ffcffeHv7dfknx7E on edge-dev.
