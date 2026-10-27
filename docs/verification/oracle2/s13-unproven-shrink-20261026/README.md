# S13 UNPROVEN-row shrink — evidence (2026-10-26)

**Date:** 2026-10-26 (EDT)
**Branch:** `codex/parent24-s13-full-recovery-20261026`
**Base head:** `48cfc494d06056ab2736ac1456621b0e179134b3`
**Class:** code (offline synthetic DB + synthetic FalkorDB; no production, no shared-db write)
**Host:** edge-dev3
**Runner:** `run-s13-full-recovery-20261026.py` (external harness, FalkorDB lifecycle added)
**Test module:** `services/oracle-brain/tests/test_s13_full_recovery_exercise_v1.py`

## Exact JUnit totals

**14 passed, 0 failed, 0 errors, 0 skipped** (4.728s test time).

The original 11 tests are unchanged and remain green. Three new named tests
shrink three previously UNPROVEN rows:

| # | Test | Result | UNPROVEN row |
|---|------|--------|--------------|
| 12 | `test_live_falkordb_graph_census_after_replay` | PASSED | Live FalkorDB graph census after full ledger replay |
| 13 | `test_real_vector_model_license_proof_artifact_recorded` | PASSED | Real vector-model license proof honesty |
| 14 | `test_source_runtime_admission_beyond_metadata_sql` | PASSED | Source/runtime admission beyond metadata SQL |

JUnit XML SHA-256: `0deac49c0d55efb694ee0deb06e4c30d361c5cde17b67112e2f14120a85e5c7a`

## Row 1 — Live FalkorDB graph census after full ledger replay

Live synthetic FalkorDB (pinned `falkordb/falkordb:v4.20.7` image, loopback-only,
password-protected). Pre-outage: every accepted event projected into the live
graph (`FalkorGraphStore.project` + deterministic Source/APPEARS_IN edges), then
census recorded. Simulated graph loss (`DETACH DELETE`, confirmed 0 nodes).
Post-restore ledger replay rebuilt the graph through the same projection
callback. Census compared.

| Census dimension | Pre-outage | Post-replay | Match |
|---|---|---|---|
| node_count | 26 | 26 | yes |
| edge_count | 25 | 25 | yes |
| labels | Assertion:25, Source:1 | Assertion:25, Source:1 | yes |
| active_assertions | 25 | 25 | yes |

Graph loss zero at synthetic scale: the surviving ledger fully rebuilds the
graph to an identical census. This is a live graph-store count comparison, not
a ledger-identity inference.

## Row 2 — Real vector-model license proof honesty

Named fixture-level artifact `real-vector-model-license-proof-v1` recorded
without calling any paid provider.

- Artifact SHA-256: `33335fba322dc60263e9deaaf9252793001275e8d148d4177ba436eba3ce1efa`
- Real model named: `openai/text-embedding-3-small`
- License instrument named: OpenAI Terms of Use (service terms governing API model use)
- Admission pins recorded from codebase closed contracts (model literal,
  terms_hash pattern, pricing class)
- `fixture_level_only=true`, `provider_call_made=false`,
  `live_license_text_fetched=false`
- Synthetic embedder (`synthetic-fixed-8`, invented-fixed-dimensions) explicitly
  marked distinct; synthetic is never equated with real.

Honest scope (verbatim from artifact): fixture-level named license/admission
proof for the real model; no live license text fetched; does not prove the live
license terms currently in force at the provider.

## Row 3 — Source/runtime admission beyond metadata SQL

Runtime and source-path admission checks exercised against the restored
database — not metadata row counts:

| Check | Expected | Observed |
|---|---|---|
| `has_authority` positive (root appointment holder, scope intake) | True | True |
| `has_authority` negative (unappointed actor, scope intake) | False | False |
| `admit_document` no processing approval | refused | refused ("no current processing approval for exact request") |
| `admit_document` with exact matching approval | admitted | admitted |

`has_authority` runs the recursive appointment-lineage SQL against the restored
store. `admit_document` exercises the full source-path admission (intake scope +
processing approval authorize). Both are runtime code paths, not metadata SQL.

## Measured (unchanged from base exercise)

- RTO: 1.246 s (target <= 3600 s)
- Backup: 0.251 s (target <= 900 s)
- RPO exposure: 0.0 s (exercise-specific; production RPO depends on backup cadence)
- Scale: 25 events, 8 artifacts, 5 conversation events, 1 once-intent, 1 cost observation

## Files

- `s13-full-recovery-junit.xml` — exact JUnit XML (14 tests)
- `dr-result.json` — full measured gate results including the three new gates
- `runner-result.json` — runner identity and elapsed
- `real-vector-model-license-proof-v1.json` — named license/admission proof artifact

## Cleanup

Synthetic worker Postgres project torn down (`docker compose down -v`).
Synthetic FalkorDB container removed (`docker rm -f`). Databases dropped in
fixture finally block. No production, shared-db, or company resources touched.

## What remains UNPROVEN after this increment

See S13-recovery.md "UNPROVEN gates (exact) after this exercise" — updated list.
