# Public complete-source review brief: S12 preauth proof runner 04 (successor)

Prepared source/review inputs only. DO NOT run database, Next, Auth/Storage, provider, platform, child native, installation or release actions. Root retains security/schema/merge/admission/actual-run judgment. The separate business-acceptance hold is unchanged. Real Teams producer remains UNQUALIFIED.

This brief is the exact successor to `s12-current-public-review-brief.md` (which describes runner 03). Runner 03 was NEVER EXECUTED. Runner 04 is the prepared successor and has NEVER EXECUTED as a real database gate. Neither scratch directory exists. The prior draft `docs/verification/oracle2/s12-current-preauth-public-review-brief-04.md` is superseded by this closeout-directory successor, which enumerates the nine cases exactly.

## 1. Exact frozen inputs

| Input | Exact value |
|---|---|
| Consumer source HEAD | `7defd1eeeaccad46ba04b96952c439305065c796` |
| Genuine main parent | `c187bfc36723ca891ad7558fe202a258ee2f27f8` |
| Complete source census | full 1703 cached + untracked NUL census, regular files only, no symlinks |
| Reviewed source map | `s12-current-preauth-reviewed-source.json` (exact bytes; not the wrapped full-manifest substitute) |
| Frozen manifest | 215406 bytes, SHA256 `06e8b1ce008d8d23d305f75c58d7417a9e3d401e22b35a9158f3049a8e220e5f` |
| Runner | `run-s12-current-preauth-proof-04.py`, SHA256 `5b05cb4a41a8bc50b6284b4c1d09fa99b7003deb0680e8e9fd5063fd48731911` |
| Base project | `oracle2-synthetic-s12c04` + worker's owned `w<12hex>` suffix |
| Label | `documentary-99` |
| Phase owner | `owned_phase_database` (SAME existing helper; 7def helper lacks the new 2633 receipt — 04 invents no startup receipt) |
| Canonical owner | `dev.oracle2.test_canonical_schema` |
| Limits | context 120s / admission 115s / request max 30s / test deadline 120s (unchanged) |

## 2. Complete shared / authguard dependency set (review ALL, not only changed files)

A missing review file is a review-custody blocker, not a pass.

- `packages/shared/src/protected-server-binding.ts` — static admission, SAME eight closed validators, current recipient index, actual installed selector/reselector
- `packages/shared/src/protected-control-window.ts` — original wall/mono/domain; wall_end may only shorten
- `packages/shared/src/_protected-file.ts` — file custody primitives
- `packages/shared/src/protected-service-channel.ts` — protected service response framing
- `apps/web/proxy.ts` — request/origin path
- `apps/web/lib/auth-guard.ts` — actual unique non-disabled employee SQL and disable rules
- `apps/web/lib/supabase/server.ts` — verified getUser path
- `apps/web/lib/replacement-protected-client.ts` and `apps/web/lib/replacement-server-binding.ts` (same-export forwarder)
- `services/oracle-brain/tests/test_workspace_next_recipients_sql_v1.py` — the nine-case suite
- `services/oracle-brain/tests/test_workspace_workflow_fixture_v1.py` — named artwork-rework workflow fixture
- `services/oracle-brain/tests/invented_next_employee_fixture_v1.py` — two-recipient employee pair fixture
- `apps/web/tests/oracle2/workspace-next-recipients-proof.ts` — actual Next/AuthSDK HTTPS driver
- `apps/web/tests/oracle2/invented-auth-service.ts` — invented Auth issuer for HTTPS getUser

Root new-main 191/S14 source, registrations, and SQL027 remain inherited unchanged. No inverse old-tree replacement.

## 3. Technical requirement (unchanged from accepted source)

Before SDK construction / getUser / employeeSQL, SAME installed finite recipient index/project/purpose selects only pinned profile JSON through SAME eight closed validators. BOTH request Origin header and actual URL origin must match before AuthSDK/employeeSQL. Return only origin + minimum index horizon; ALL matched-origin profiles' expiry/original horizons bind `validUntil`. Unmatched-origin profiles cannot extend the lease. Legacy singleton remains only if the index is ABSENT; a valid singleton cannot rescue an explicitly configured failed recipient index. Profile currentness/index pins checked; malformed/expired/missing/changed facts refuse with zero Auth/SQL. Profile 3s / index 60s fixtures prove the corrected shortest matched horizon. Original wall/mono end only shortens by the same delta; no new clock capture.

Named artwork-rework workflow `workspace-artwork-rework-v1` (five steps, six edges, one rework, two exclusive conditions, three role assignments across Design/Supplier) is required by the current Next driver before raw capture/qualification, with four tamper negatives refusing.

## 4. Nine-case suite — exact enumeration (what independent review must assess)

JUnit totals must be exactly `{tests:9, failures:0, errors:0, skipped:0}` under the original 120/115/30 limits. No retry, no reuse of old receipts, no full W10 claim.

### Case 1 (the one actual end-to-end case)

`test_actual_next_two_recipients_workspace_and_independent_revocation` in
`services/oracle-brain/tests/test_workspace_next_recipients_sql_v1.py`:

- Actual Next (`next dev --turbopack --experimental-https`) + AuthSDK HTTPS getUser against an invented issuer + actual unique employee SQL join → SQL ACK → readonly SDK.
- Two independently installed recipients (A non-admin, B admin) with distinct principals, distinct A/B certs/profiles.
- Named workflow `workspace-artwork-rework-v1` required before raw capture: five steps (Start artwork review, Prepare ART, Review ART, Revise ART, Release ART), six transitions including one rework (Revise ART → Review ART), two exclusive conditions (ART approved / ART needs changes), three role assignments (Design prepare, Supplier review, Design revise), one handoff (Design → Supplier).
- Positive source-derived SVG drawing (6 lines, 1 dashed rework), conditions text, HTML export with full quote/evidence, CSV export with Original link + Company-wide completeness unverified.
- Two recipients, mobile EN/ZH language switch, 1280 desktop / 393 mobile, no overflow, no page errors.
- Permission revocation path: A disabled → 503, B 200; A restored → same original identities/horizons A 200; irreversible A admission revocation → 503 export/read, B 200; B auth revoke → 503.
- Foreign principal / foreign process / unauth no body → 503.
- All requests inside original window (caller_deadline remaining > 0 and ≤ 30000).
- Employee SQL observations require TLS (`ssl_in_use`).

### Cases 2–9 (eight pure malformed-input negatives that refuse before database access)

`test_employee_pair_fixture_rejects_malformed_population_before_database` parametrized by `damage`:

| # | damage | Input shape | Refusal |
|---|---|---|---|
| 2 | `empty` | `entries=()` | `ValueError` matching `(?:exact two\|distinct exact) invented` before `owned_worker_database` |
| 3 | `one` | single valid tuple | same |
| 4 | `three` | three valid tuples | same |
| 5 | `auth-duplicate` | two tuples sharing auth_user_id | same |
| 6 | `employee-duplicate` | two tuples sharing employee_id | same |
| 7 | `string-uuid` | auth_user_id is `str` not `UUID` | same |
| 8 | `boolean-admin` | is_admin is `1` not `bool` | same |
| 9 | `unknown-tuple` | third element is `'foreign'` not `bool` | same |

All eight call `invented_next_employee_pair_fixture_v1('', container='never-connect', entries=...)`. The empty/one/three shape check raises before any SQL. The type/distinctness check in `_invented_next_employee_rows_v1` raises before `owned_worker_database`. Therefore none of cases 2–9 opens a database connection.

## 5. Runner 04 edge cases (custody controls independent review must assess)

1. **Exact review receipt required at argv[1]; runner SHA at argv[2].** Missing/invalid raises before any effect. Review receipt SHA is recorded and rechecked after the database gate; mutation at gate raises.
2. **Clean exact frozen source required** — `git rev-parse HEAD` equals HEAD and `git status --porcelain --untracked-files=all` is empty before any setup.
3. **Manifest bytes/SHA bind the complete 1703 census** before database gate. Source before is written; any mismatch raises.
4. **Database gate** runs `ai-task-gates check --before database --reviewer-approval <receipt>`. Gate refusal stops; no effect follows.
5. **Missing/invalid retained ownership is UNKNOWN / absence_proven:false and raises** — never an empty inventory, never an invented startup receipt. The 7def helper lacks the new 2633 receipt; 04 invents none.
6. **Finally-block source-after** is always attempted; startup failures still record source-after and independently check exact retained project labels even pre-yield.
7. **Owned cleanup** uses the sole retained ownership receipt (`project`, `container_id`, `port`, `worker`, `synthetic_only:true`, 0600, single link, matching regexes). Yields/retained identity must match. Remaining containers/networks/volumes filtered by `com.docker.compose.project=<retained.project>` must all be empty or `absence_proven:false` and the run raises.
8. **One fresh PG + owned graph / canonical once / owned phase.** Fresh compose project `oracle2-synthetic-s12c04-w<12hex>`, worker `documentary-99`, one Falkor candidate with numeric owned URL/label checks.
9. **No retry, no reuse of old receipts, no full W10 claim.** Focused 9-case proof only.

## 6. What 04 does not claim

- No actual Supabase session or real employee database is proved by proxy/TLS tests that use invented Auth/employee import hooks.
- No company/private originals, real external Auth/Storage/provider calls, or paid effects.
- No documentation-check capability remains UNKNOWN/INVALID.
- No full product acceptance: grouped inbox, editable correction, source-failure/retry health, full a11y/task rubric remain open.
- No business acceptance, company comparison, adoption, or retirement.
- Real Teams producer UNQUALIFIED.

## 7. Offline-provable vs UNPROVEN (as of this brief)

### Provable offline (this packet — live offline executions recorded)

- Runner 04 SHA256 is exactly `5b05cb4a41a8bc50b6284b4c1d09fa99b7003deb0680e8e9fd5063fd48731911` (verified against exact blob bytes).
- Nine-case suite source exists at 7def and enumerates exactly 1 end-to-end + 8 pre-database negatives.
- **Cases 2–9 PROVEN offline by live execution** (2026-10-26): all eight malformed employee-pair inputs raised `ValueError` before `owned_worker_database`; the DB stub was never reached. Results: `empty/one/three` → `exact two invented employee entries required`; `auth-duplicate/employee-duplicate/string-uuid/boolean-admin/unknown-tuple` → `distinct exact invented authuser/employee/bool tuples required`.
- **Workflow structure PROVEN offline** (2026-10-26): `workspace-artwork-rework-v1` constructs under `formal_eligible=True` with steps=5, transitions=6, conditions=2, roles=3, handoffs=1, rework=1 (art-t6 Revise ART → Review ART), exclusive split edges=2 (art-decision). All step labels and condition wordings appear in QUOTE.
- Runner 04 binds clean HEAD, complete 1703 manifest, review-receipt recheck, source-after, owned cleanup absence.
- Runner 04 has NEVER EXECUTED as a real database gate. Scratch directory `/tmp/oracle-parent24-wy02uT/s12-current-preauth-owned-proof-04` does not exist.

### UNPROVEN (named gates — do not invent receipts)

| Gate ID | What is required | Status |
|---|---|---|
| `S12-04-REVIEW` | Independent exact SOURCE + ONE resource-plan assessment of this complete packet | **UNPROVEN** — not yet performed |
| `S12-04-DB-GATE` | `ai-task-gates check --before database` with a real review receipt binding this exact HEAD and runner digest | **UNPROVEN** — no receipt exists |
| `S12-04-ROOT-RELEASE` | Root one-fresh-release decision | **UNPROVEN** — root decision pending |
| `S12-04-LIVE-9CASE` | Actual execution of the nine-case suite under runner 04 with JUnit `{9,0,0,0}` | **UNPROVEN** — never executed |
| `S12-04-NEXT-E2E` | Actual Next/AuthSDK HTTPS end-to-end case with real SQL ACK and readonly SDK | **UNPROVEN** — not run |
| `S12-04-TEAMS` | Real Teams producer qualification | **UNQUALIFIED** |
| `S12-04-BIZ` | Business acceptance / company comparison / adoption / retirement | **UNPROVEN** — hold remains |

## 8. Remaining sequence before any execution

1. Independent exact SOURCE + ONE resource-plan assessment of this complete packet (all §2 files + runner 04 + exact manifest map).
2. True database gate with a real review receipt that binds this exact HEAD and runner digest.
3. Root one-fresh release decision.
4. Then and only then, one fresh invented instance under the original limits, with full source-before/after and process/owned-resource absence.
5. After that proof: continue remaining full S12 product tasks; this proof is not whole-program acceptance.

Posted by MiMo chat on edge-dev3. Closeout runner 03 and this successor 04 remain PREPARED ONLY.
