# S13 ops-shaped UNPROVEN rows — alerts/retention/quota + cadence-aware RPO

**Date:** 2026-10-26 (EDT)
**Branch:** `codex/parent24-s13-ops-unproven-20261026`
**Base:** `48cfc494d06056ab2736ac1456621b0e179134b3`
**Class:** code (offline synthetic DB; no production, no shared-db write)
**Host:** edge-dev3
**Runner:** `run-s13-ops-unproven-20261026.py` (external harness)
**Test module:** `services/oracle-brain/tests/test_s13_ops_unproven_exercise_v1.py`

Sibling evidence for parent #24, S13. Touches only the ops-shaped UNPROVEN
rows. Graph census, real vector license and source/runtime admission are
owned by the other S13 agent and are NOT addressed here. No company originals,
production, paid providers, real meetings, POP shared-db writes or business
acceptance. Real Teams producer stays UNQUALIFIED.

## Rows this exercise addresses

| Row | Status after this exercise |
|-----|----------------------------|
| 4. Alerts / retention / quota operational exercise at synthetic scale | **PROVED** (exact JUnit) |
| 3. Production RPO figure under real backup cadence | **SHRUNK** — cadence-aware measured proof landed; the production *figure* stays UNPROVEN with formula and requirements |

## Exact JUnit totals

**6 passed, 0 failed, 0 errors, 0 skipped** (6.327 s test time).

| # | Test | Result |
|---|------|--------|
| 1 | `test_alert_firing_and_clearing` | PASSED |
| 2 | `test_retention_cutoff_behavior` | PASSED |
| 3 | `test_quota_accounting_after_restore` | PASSED |
| 4 | `test_cadence_aware_rpo_measured` | PASSED |
| 5 | `test_production_rpo_formula_and_non_production_disclaimer` | PASSED |
| 6 | `test_ops_scale_recorded` | PASSED |

JUnit XML SHA-256: `a6568c28e77eb9bc11121463c534b1456ffc87d85b1f4942359258eac7d16ee7`
ops-result.json SHA-256: `257ae6ab7bff531060faecb378b930ff78a02469da1ab226c811c61887b8d5f6`
runner-result.json SHA-256: `0be1e02323a5754e4c5b7055af0c06391f0eb34ea1738ee61901a99bb41e6a26`

Files in this directory: `s13-ops-unproven-junit.xml`, `ops-result.json`,
`runner-result.json`, `pytest.txt`, `database-gate.txt`, and the recorded
harness `run-s13-ops-unproven-20261026.py` for reproducible re-runs.

## Row 4 — alerts / retention / quota operational exercise

Synthetic scale (deliberately larger than a toy, still offline): **40**
pipeline stages, **120** retention records, **24** quota accounting rows.

**Alert firing AND clearing** (`operations/health.py` `alarms`):

- 40 stages under default limits (age 30 min / failures 3 / cost cap $50):
  4 stuck 2 h + 5 failing (failures=3) + 25 cost-heavy stages whose summed
  cost trips `cost_cap`.
- Fired codes exactly: `cost_cap`, `failing:stage-04..08`, `stuck:stage-00..03`
  (10 codes).
- Partial clear: recovering only the 4 stuck stages leaves
  `failing:stage-04..08` + `cost_cap` — alarms clear independently.
- Full clear: all 40 stages healthy → `[]`.
- Tighter limits (age 5 min / failures 1 / cost $1) expose 6 latent stages
  (09–14) the default limits tolerate → 22 codes. Thresholds are honored,
  not decorative.

**Retention cutoff behavior** (`operations/retention.py` `decide`):

- 120 records across `meeting` / `policy` / `transcript` kinds, ages spanning
  0–39 days, mixed tombstones and legal holds.
- Decisions: `purge` > 0, `keep` > 0, `hide` > 0 (sum = 120).
- Exact TTL boundary: `created_at == now - ttl` → `purge`;
  1 s inside → `keep`; 1 s outside → `purge`.
- Tombstone always wins over a readable rule (→ `purge`); a legal hold only
  defers physical purge (→ `hide`).
- `ttl=None` keeps until explicitly deleted (e.g. `policy` at 3650 days → `keep`).
- Fail-closed: unknown kind → `KeyError`; naive timestamp → `ValueError`.

**Quota accounting after restore** (SQL 004 `operating_dispatch_*`):

- 24 reservations (17 completed, 7 failed; exactly 1 `quota_exhausted` with an
  immutable diagnosis). `reserved_at` spread across ~46 days so a 30-day TTL
  cutoff is meaningful on restored timestamps.
- pg_dump → drop original → pg_restore onto an empty target (0 oracle2 tables
  before, 120 after).
- Pre/post snapshots **identical**: total reserved `$0.240000`, status counts,
  quota-exhausted receipt + diagnosis counts, `reserved_at` min/max, row count.
- Reserved maximum preserved exactly (`0.010000`) — not refunded, not zeroed.
- `quota_exhausted` receipt and diagnosis survive byte-for-byte.
- Immutability trigger holds after restore (`UPDATE` on
  `operating_dispatch_diagnoses` raises `operating model history is append-only`).
- Quota-only failure still **blocks a matching retry** after restore:
  `Budget.reserve(..., attempt=2, correction_hash=<same>)` refuses with
  *"one correction requires a diagnosed failed receipt"*.
- Retention cutoff evaluated against restored `reserved_at` timestamps gives
  the same decisions pre- and post-restore (24 rows).

## Row 3 — cadence-aware RPO honesty

The earlier full-recovery exercise measured RPO exposure `0.0 s` **only**
because the backup completed immediately before the simulated outage. That
number is an artifact of the exercise shape, not a property of the system.

This exercise deliberately separates backup from outage:

| Quantity | Value |
|----------|-------|
| Backup duration | 0.138 s |
| Restore duration | 1.374 s |
| Deliberate gap sleep | 1.500 s |
| **Measured RPO exposure** (`outage − backup_done`) | **1.511 s** |
| Pre-backup events committed | 25 |
| Post-backup ("gap") events committed after dump | 6 |
| Gap events surviving restore | **0** (honest loss) |
| Pre-backup events surviving restore | 25 |
| Max event sequence after restore | 25 |

The exposure is measured and **non-zero**. The 6 events committed after the
dump are genuinely lost — the RPO gap is demonstrated, not assumed.

### Production-cadence formula (explicit)

```
worst-case RPO seconds    = backup_interval_seconds          # disaster at any cadence phase
average RPO seconds       = backup_interval_seconds / 2
extra risk if disaster
  lands during a backup   = backup_duration_seconds
```

Production RPO is bounded by the **production backup cadence**, not by restore
speed. This exercise measured a 1.511 s exposure against a deliberate 1.5 s
gap; that is an exercise measurement, not a production figure.

### What would be needed for a production RPO figure

1. Configured production backup interval (cadence) in seconds.
2. Measured production-scale backup duration.
3. Disaster exercise at an arbitrary cadence phase — not immediately post-backup.
4. Explicit statement of any synchronous replication or WAL shipping (none claimed).
5. Confirmation that no post-backup ledger tail survives without a newer backup.

### Never production figures

The **1.275 s RTO** and **0.0 s RPO** recorded by the 2026-10-26 full-recovery
exercise are exercise-specific and must **NEVER** be quoted as production
figures. Neither this exercise nor that one claims a production RTO/RPO.

## Scale recorded

| Dimension | Count |
|-----------|-------|
| Alert stages | 40 |
| Retention records | 120 |
| Quota rows | 24 |
| Events pre-backup | 25 |
| Events post-backup (gap) | 6 |
| Native dump | 1,246,665 bytes (sha256 `7dfdeefc5321e3adcce4a6ffd8626b4eadf98cfb9ca2d374d7053cda084cc379`) |
| Restored oracle2 tables | 120 |

## Cleanup

Owned synthetic worker project `oracle2-synthetic-p24ops-mimo-*` torn down
(`docker compose down -v`). Databases dropped in the fixture `finally` block.
No production, shared-db, or company resources touched. PR branches 200/201/
207/210 untouched. No PR merges.

## What remains UNPROVEN after this exercise

1. Live FalkorDB graph census after full ledger replay — other S13 agent.
2. Real vector-model license proof — other S13 agent.
3. **Production RPO figure** — formula and requirements recorded above; the
   figure itself needs a production-cadence measurement (cannot be obtained
   offline).
5. Source/runtime admission beyond the metadata SQL path — other S13 agent.
6. Business acceptance / company activation — owner hold, unchanged.
7. Real Teams producer qualification — UNQUALIFIED.

Row 4 (alerts/retention/quota operational exercise) is **closed** at synthetic
scale by this exercise.
