"""S13 ops-shaped UNPROVEN rows exercise (parent #24) — alerts/retention/quota
and cadence-aware RPO honesty.

Shrinks two S13 UNPROVEN rows on owned synthetic stores only:

  4. Alerts / retention / quota operational exercise at synthetic scale —
     alert firing AND clearing, retention cutoff behavior, and quota
     accounting after restore, with exact JUnit.
  3. Production RPO honesty — a measured, cadence-aware RPO proof with a
     deliberate non-zero backup-to-outage gap, the production-cadence formula,
     and what would be needed for a production figure. The earlier 1.275 s
     RTO and 0.0 s RPO are exercise-specific and are NEVER production figures.

No company originals, production, paid providers, real meetings, POP
shared-db writes, or business acceptance. Real Teams producer stays UNQUALIFIED.
Graph census, real vector license and source/runtime admission are NOT touched
here (other S13 agent's rows).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
import pytest

from oracle_brain.operations.health import StageHealth, Thresholds, alarms
from oracle_brain.operations.retention import Record, RetentionRule, decide
from oracle_brain.operating_model.provider_adapter import Budget

# ---------------------------------------------------------------------------
# Synthetic scale (deliberately larger than a toy; still offline/invented).
# ---------------------------------------------------------------------------
SCALE_STAGES = 40
SCALE_RETENTION = 120
SCALE_QUOTA_ROWS = 24
SCALE_EVENTS_PRE = 25
SCALE_EVENTS_GAP = 6
HEX = "a" * 64
CORRECTION = "c" * 64
DIAGNOSIS = "d" * 64

RESULT: dict = {}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _native(container: str, program: str, name: str, *, dump: Path, admin: dict):
    env = {
        **os.environ,
        "PGDATABASE": name,
        "PGUSER": admin.get("user", "postgres"),
        "PGPASSWORD": admin.get("password", ""),
    }
    cmd = ["docker", "exec", "-i", "--env", "PGDATABASE", "--env", "PGUSER",
           "--env", "PGPASSWORD", container, program]
    if program == "pg_dump":
        cmd += ["--format=custom", "--no-owner", "--no-acl"]
    else:
        cmd += ["--exit-on-error", "--no-owner", "--no-acl", "--dbname", name]
    with dump.open("wb" if program == "pg_dump" else "rb") as stream:
        result = subprocess.run(
            cmd, env=env,
            stdout=stream if program == "pg_dump" else subprocess.PIPE,
            stdin=stream if program != "pg_dump" else subprocess.DEVNULL,
            stderr=subprocess.PIPE, timeout=120,
        )
    if result.returncode:
        raise RuntimeError(f"native {program} failed rc={result.returncode}")


# ---------------------------------------------------------------------------
# Alert firing / clearing at synthetic scale.
# ---------------------------------------------------------------------------
def _alert_exercise(now: datetime) -> dict:
    """Fire alarms over unhealthy stages, then clear them to healthy.

    Proves both transitions with exact codes at SCALE_STAGES, plus a partial
    clear where only some stages recover, and that tighter thresholds expose
    latent stages the default thresholds tolerate.
    """
    # Layout over 40 stages (default limits: age 30 min, failures 3, cost $50):
    #   00-03  stuck 2h                 -> stuck under both limit sets
    #   04-08  failures=3               -> failing under both limit sets
    #   09-14  failures=2, pending 10m  -> silent under default; fires under tight
    #   15-39  cost 2.0 each            -> 25*2.0 = 50 trips cost_cap exactly
    unhealthy: list[StageHealth] = []
    for i in range(SCALE_STAGES):
        if i < 4:
            unhealthy.append(StageHealth(f"stage-{i:02d}", 3, now - timedelta(hours=2), 0, 0.5))
        elif i < 9:
            unhealthy.append(StageHealth(f"stage-{i:02d}", 1, now - timedelta(minutes=1), 3, 0.5))
        elif i < 15:
            unhealthy.append(StageHealth(f"stage-{i:02d}", 1, now - timedelta(minutes=10), 2, 0.5))
        else:
            unhealthy.append(StageHealth(f"stage-{i:02d}", 0, None, 0, 2.0))
    fired = alarms(unhealthy, now)
    expected_fired = sorted(
        [f"stuck:stage-{i:02d}" for i in range(4)]
        + [f"failing:stage-{i:02d}" for i in range(4, 9)]
        + ["cost_cap"]
    )
    assert fired == expected_fired, f"alert firing codes differ: {fired}"

    # Partial clear: recover the stuck stages only; failing + cost_cap remain.
    partial = list(unhealthy)
    for i in range(4):
        partial[i] = StageHealth(f"stage-{i:02d}", 0, None, 0, 0.5)
    partial_codes = alarms(partial, now)
    assert partial_codes == sorted(
        [f"failing:stage-{i:02d}" for i in range(4, 9)] + ["cost_cap"]
    ), f"partial clear codes differ: {partial_codes}"

    # Full clear: every stage healthy again -> empty alarm list.
    healthy = [StageHealth(f"stage-{i:02d}", 0, None, 0, 0.5) for i in range(SCALE_STAGES)]
    cleared = alarms(healthy, now)
    assert cleared == [], f"alert clearing failed: {cleared}"

    # Tighter thresholds expose the latent 09-14 stages as well.
    tight = Thresholds(max_pending_age=timedelta(minutes=5), max_failures=1, cost_cap_usd=1.0)
    tight_codes = alarms(unhealthy, now, tight)
    assert "cost_cap" in tight_codes
    assert len(tight_codes) > len(fired), "tight thresholds must expose latent stages"
    assert "stuck:stage-09" in tight_codes and "failing:stage-12" in tight_codes

    return {
        "scale_stages": SCALE_STAGES,
        "fired_codes": fired,
        "fired_count": len(fired),
        "partial_clear_codes": partial_codes,
        "cleared_codes": cleared,
        "cleared_is_empty": cleared == [],
        "tight_threshold_codes": tight_codes,
        "tight_threshold_codes_count": len(tight_codes),
    }


# ---------------------------------------------------------------------------
# Retention cutoff behavior at synthetic scale.
# ---------------------------------------------------------------------------
def _retention_exercise(now: datetime) -> dict:
    """Prove TTL cutoff, legal hold, tombstone and fail-closed semantics."""
    rules = {
        "meeting": RetentionRule("meeting", timedelta(days=30)),
        "policy": RetentionRule("policy", None),
        "transcript": RetentionRule("transcript", timedelta(days=7)),
    }
    decisions: dict[str, int] = {"purge": 0, "keep": 0, "hide": 0}
    boundary: dict[str, str] = {}

    # Exact TTL boundary: created_at == now - ttl is already >= ttl -> purge.
    ttl = timedelta(days=7)
    boundary["at_cutoff"] = decide(Record("transcript", now - ttl), rules, now)
    boundary["one_second_inside"] = decide(Record("transcript", now - ttl + timedelta(seconds=1)), rules, now)
    boundary["one_second_outside"] = decide(Record("transcript", now - ttl - timedelta(seconds=1)), rules, now)
    assert boundary["at_cutoff"] == "purge"
    assert boundary["one_second_inside"] == "keep"
    assert boundary["one_second_outside"] == "purge"

    # Bulk synthetic population across kinds/ages/holds/tombstones.
    for i in range(SCALE_RETENTION):
        kind = ("meeting", "policy", "transcript")[i % 3]
        age = timedelta(days=i % 40)  # spans past and inside every TTL
        tombstoned = i % 5 == 0
        legal_hold = i % 7 == 0
        verdict = decide(Record(kind, now - age, tombstoned=tombstoned, legal_hold=legal_hold), rules, now)
        decisions[verdict] += 1
    assert sum(decisions.values()) == SCALE_RETENTION
    assert decisions["purge"] > 0 and decisions["keep"] > 0 and decisions["hide"] > 0

    # Tombstone always wins over a readable rule; hold only defers physical purge.
    assert decide(Record("policy", now, tombstoned=True), rules, now) == "purge"
    assert decide(Record("policy", now, tombstoned=True, legal_hold=True), rules, now) == "hide"
    assert decide(Record("meeting", now - timedelta(days=31), legal_hold=True), rules, now) == "keep"
    # TTL None means keep until explicitly deleted.
    assert decide(Record("policy", now - timedelta(days=3650)), rules, now) == "keep"

    # Fail closed on unknown kind and on naive timestamps.
    unknown_refused = False
    try:
        decide(Record("unknown-kind", now), rules, now)
    except KeyError:
        unknown_refused = True
    assert unknown_refused is True
    naive_refused = False
    try:
        decide(Record("meeting", now.replace(tzinfo=None)), rules, now)
    except ValueError:
        naive_refused = True
    assert naive_refused is True

    return {
        "scale_records": SCALE_RETENTION,
        "decisions": decisions,
        "boundary": boundary,
        "unknown_kind_fails_closed": unknown_refused,
        "naive_timestamp_fails_closed": naive_refused,
        "tombstone_wins": True,
        "legal_hold_defers_purge": True,
        "ttl_none_keeps": True,
    }


# ---------------------------------------------------------------------------
# Quota seed + post-restore accounting proof.
# ---------------------------------------------------------------------------
def _seed_quota_rows(conn, *, workspace, principal, now, until):
    """Insert SCALE_QUOTA_ROWS synthetic dispatch accounting rows.

    Mix: completed, failed non-quota, and exactly one quota_exhausted failure
    carrying an immutable diagnosis. reserved_at values span past/future so
    retention cutoff can be evaluated against restored timestamps.
    """
    quota_artifact = uuid4()
    quota_batch = uuid4()
    rows = []
    for i in range(SCALE_QUOTA_ROWS):
        rid = uuid4()
        workspace_id = workspace if i < SCALE_QUOTA_ROWS - 1 else workspace
        artifact_id = uuid4() if i < SCALE_QUOTA_ROWS - 1 else quota_artifact
        batch_id = uuid4() if i < SCALE_QUOTA_ROWS - 1 else quota_batch
        purpose = "source-extraction"
        attempt = 1
        reserved = Decimal("0.01")
        # Spread reserved_at across ~46 days so a 30-day TTL cutoff is meaningful.
        reserved_at = now - timedelta(days=i * 2)
        conn.execute(
            """INSERT INTO oracle2.operating_dispatch_reservations
               (reservation_id,workspace_id,artifact_id,batch_id,purpose,attempt,
                reserved_usd,pricing_hash,reserved_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, workspace_id, artifact_id, batch_id, purpose, attempt,
             reserved, HEX, reserved_at),
        )
        if i == SCALE_QUOTA_ROWS - 1:
            # The one quota_exhausted failure + diagnosis.
            conn.execute(
                """INSERT INTO oracle2.operating_dispatch_receipts
                   (reservation_id,actual_usd,status,response_hash,failure_kind,created_at)
                   VALUES (%s,%s,'failed',%s,'quota_exhausted',%s)""",
                (rid, reserved, HEX, reserved_at),
            )
            conn.execute(
                """INSERT INTO oracle2.operating_dispatch_diagnoses
                   (reservation_id,diagnosed_by,failure_kind,correction_hash,diagnosis_hash,created_at)
                   VALUES (%s,%s,'quota_exhausted',%s,%s,%s)""",
                (rid, principal, CORRECTION, DIAGNOSIS, reserved_at),
            )
            rows.append({"reservation_id": str(rid), "kind": "quota_exhausted",
                         "artifact_id": str(artifact_id), "batch_id": str(batch_id),
                         "reserved_usd": str(reserved)})
        elif i % 4 == 0:
            conn.execute(
                """INSERT INTO oracle2.operating_dispatch_receipts
                   (reservation_id,actual_usd,status,response_hash,failure_kind,created_at)
                   VALUES (%s,%s,'failed',%s,'invalid_output',%s)""",
                (rid, reserved, HEX, reserved_at),
            )
            rows.append({"reservation_id": str(rid), "kind": "invalid_output"})
        else:
            conn.execute(
                """INSERT INTO oracle2.operating_dispatch_receipts
                   (reservation_id,actual_usd,status,response_hash,failure_kind,created_at)
                   VALUES (%s,%s,'completed',%s,NULL,%s)""",
                (rid, reserved, HEX, reserved_at),
            )
            rows.append({"reservation_id": str(rid), "kind": "completed"})
    return {
        "quota_artifact_id": str(quota_artifact),
        "quota_batch_id": str(quota_batch),
        "rows": rows,
    }


def _quota_snapshot(conn, workspace) -> dict:
    total_reserved = conn.execute(
        "SELECT COALESCE(sum(reserved_usd),0) FROM oracle2.operating_dispatch_reservations "
        "WHERE workspace_id=%s", (workspace,),
    ).fetchone()[0]
    counts = dict(conn.execute(
        "SELECT s.status, count(*) FROM oracle2.operating_dispatch_reservations r "
        "JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) "
        "WHERE r.workspace_id=%s GROUP BY s.status", (workspace,),
    ).fetchall())
    quota_failures = conn.execute(
        "SELECT count(*) FROM oracle2.operating_dispatch_receipts s "
        "JOIN oracle2.operating_dispatch_reservations r USING(reservation_id) "
        "WHERE r.workspace_id=%s AND s.failure_kind='quota_exhausted'", (workspace,),
    ).fetchone()[0]
    quota_diagnoses = conn.execute(
        "SELECT count(*) FROM oracle2.operating_dispatch_diagnoses d "
        "JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) "
        "JOIN oracle2.operating_dispatch_reservations r USING(reservation_id) "
        "WHERE r.workspace_id=%s AND d.failure_kind='quota_exhausted'", (workspace,),
    ).fetchone()[0]
    reserved_ts = conn.execute(
        "SELECT min(reserved_at), max(reserved_at), count(*) "
        "FROM oracle2.operating_dispatch_reservations WHERE workspace_id=%s", (workspace,),
    ).fetchone()
    return {
        "total_reserved_usd": str(total_reserved),
        "status_counts": {str(k): int(v) for k, v in counts.items()},
        "quota_exhausted_receipts": int(quota_failures),
        "quota_exhausted_diagnoses": int(quota_diagnoses),
        "reserved_at_min": reserved_ts[0].isoformat() if reserved_ts[0] else None,
        "reserved_at_max": reserved_ts[1].isoformat() if reserved_ts[1] else None,
        "reservation_count": int(reserved_ts[2]),
    }


def _retention_from_restored(conn, workspace, now: datetime) -> dict:
    """Evaluate retention cutoff against restored reserved_at timestamps."""
    rules = {"dispatch-reservation": RetentionRule("dispatch-reservation", timedelta(days=30))}
    rows = conn.execute(
        "SELECT reserved_at FROM oracle2.operating_dispatch_reservations "
        "WHERE workspace_id=%s ORDER BY reserved_at", (workspace,),
    ).fetchall()
    counts = {"purge": 0, "keep": 0}
    for (reserved_at,) in rows:
        verdict = decide(Record("dispatch-reservation", reserved_at), rules, now)
        counts[verdict] += 1
    return {"evaluated": len(rows), "decisions": counts}


# ---------------------------------------------------------------------------
# Module-scoped DR cycle.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ops_cycle(admin_url, tmp_path_factory):
    from dev.oracle2.test_canonical_schema import bootstrap_canonical_test_schema

    scratch = tmp_path_factory.mktemp("s13-ops-unproven")
    scratch.chmod(0o700)
    container = os.environ.get("ORACLE2_WORKER_CONTAINER_ID", "")
    if not container:
        pytest.fail("ORACLE2_WORKER_CONTAINER_ID required for owned synthetic worker")

    parts = psycopg.conninfo.conninfo_to_dict(admin_url)
    if parts.get("host") not in {"127.0.0.1", "localhost"}:
        pytest.fail("loopback synthetic target required")
    original_name = "oracle_operating_model_test_" + uuid4().hex
    restore_name = "oracle_operating_model_test_" + uuid4().hex
    created = []
    urls = {}
    workspace = uuid4()
    principal = uuid4()
    gap_thread = str(uuid4())

    try:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            for name in (original_name, restore_name):
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)
        urls["original"] = psycopg.conninfo.make_conninfo(admin_url, dbname=original_name)
        urls["restore"] = psycopg.conninfo.make_conninfo(admin_url, dbname=restore_name)

        now = datetime.now(timezone.utc)
        until = now + timedelta(days=30)
        bootstrap_canonical_test_schema(urls["original"])

        # --- 1. Alerts: fire then clear (pure; no DB effect). ---
        alert_result = _alert_exercise(now)

        # --- 2. Retention cutoff (pure) at synthetic scale. ---
        retention_result = _retention_exercise(now)

        # --- 3. Seed quota accounting + pre-backup ledger events. ---
        with psycopg.connect(urls["original"]) as conn:
            quota_seed = _seed_quota_rows(conn, workspace=workspace,
                                          principal=principal, now=now, until=until)
            # One thread carrying pre-backup sequences 1..5.
            segment_start = now
            conn.execute(
                """INSERT INTO oracle2.conversation_threads_v1
                   (thread_id,workspace_id,principal_id,mode,revision,topic,language,
                    state,question_count,pending_question,segment_started_at,segment_deadline)
                   VALUES (%s,%s,%s,'ordinary',1,'synthetic ops RPO thread','en',
                    'paused',5,%s,%s,%s)""",
                (gap_thread, workspace, principal, uuid4(),
                 segment_start, segment_start + timedelta(minutes=10)),
            )
            for seq in range(1, SCALE_EVENTS_PRE + 1):
                conn.execute(
                    """INSERT INTO oracle2.conversation_events_v1
                       (event_id,thread_id,workspace_id,principal_id,sequence,command_id,
                        command_sha256,command_bytes,operation,origin,payload)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'question','employee','{}'::jsonb)""",
                    (uuid4(), gap_thread, workspace, principal, seq, uuid4(), HEX, b'{}'),
                )
            pre_snapshot = _quota_snapshot(conn, workspace)
            pre_retention = _retention_from_restored(conn, workspace, now)

        # --- 4. Backup, then commit GAP events AFTER the dump. ---
        dump_path = scratch / "ledger.dump"
        t_backup0 = time.monotonic()
        _native(container, "pg_dump", original_name, dump=dump_path, admin=parts)
        dump_path.chmod(0o600)
        dump_sha = _sha(dump_path)
        backup_seconds = time.monotonic() - t_backup0
        t_backup_done = time.time()

        with psycopg.connect(urls["original"]) as conn:
            for seq in range(SCALE_EVENTS_PRE + 1, SCALE_EVENTS_PRE + SCALE_EVENTS_GAP + 1):
                conn.execute(
                    """INSERT INTO oracle2.conversation_events_v1
                       (event_id,thread_id,workspace_id,principal_id,sequence,command_id,
                        command_sha256,command_bytes,operation,origin,payload)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'question','employee','{}'::jsonb)""",
                    (uuid4(), gap_thread, workspace, principal, seq, uuid4(), HEX, b'{}'),
                )
            gap_committed = conn.execute(
                "SELECT count(*) FROM oracle2.conversation_events_v1 WHERE thread_id=%s",
                (gap_thread,),
            ).fetchone()[0]

        # --- 5. Deliberate non-zero backup-to-outage gap. ---
        GAP_SECONDS_TARGET = 1.5
        time.sleep(GAP_SECONDS_TARGET)
        t_outage = time.time()

        # --- 6. Outage: destroy the original store. ---
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                         (original_name,))
            conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(original_name)))
        created.remove(original_name)

        # --- 7. Restore onto a fresh empty target. ---
        t_restore0 = time.monotonic()
        with psycopg.connect(urls["restore"]) as conn:
            empty_before = conn.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='oracle2'"
            ).fetchone()[0]
        _native(container, "pg_restore", restore_name, dump=dump_path, admin=parts)
        restore_seconds = time.monotonic() - t_restore0

        # --- 8. Post-restore quota accounting + retention + RPO loss proof. ---
        with psycopg.connect(urls["restore"]) as conn:
            restored_tables = conn.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='oracle2'"
            ).fetchone()[0]
            post_snapshot = _quota_snapshot(conn, workspace)
            post_retention = _retention_from_restored(conn, workspace, now)

            # Immutability of accounting rows survives restore.
            immutability_holds = False
            try:
                conn.execute(
                    "UPDATE oracle2.operating_dispatch_diagnoses SET failure_kind='invalid_output'",
                )
            except psycopg.errors.RaiseException:
                immutability_holds = True
            conn.rollback()

            # Pre-backup events survive; gap events are lost (honest RPO).
            pre_events_after = conn.execute(
                "SELECT count(*) FROM oracle2.conversation_events_v1 "
                "WHERE thread_id=%s AND sequence<=%s", (gap_thread, SCALE_EVENTS_PRE),
            ).fetchone()[0]
            gap_events_after = conn.execute(
                "SELECT count(*) FROM oracle2.conversation_events_v1 "
                "WHERE thread_id=%s AND sequence>%s", (gap_thread, SCALE_EVENTS_PRE),
            ).fetchone()[0]
            max_sequence = conn.execute(
                "SELECT COALESCE(max(sequence),0) FROM oracle2.conversation_events_v1 "
                "WHERE thread_id=%s", (gap_thread,),
            ).fetchone()[0]

        # Quota-only failure still blocks a matching retry after restore.
        budget = Budget(urls["restore"])
        retry_blocked = False
        retry_error = ""
        try:
            budget.reserve(
                workspace_id=workspace,
                artifact_id=UUID(quota_seed["quota_artifact_id"]),
                batch_id=UUID(quota_seed["quota_batch_id"]),
                purpose="source-extraction", attempt=2,
                maximum=Decimal("0.01"), pricing_hash=HEX, correction_hash=CORRECTION,
            )
        except PermissionError as exc:
            retry_blocked = True
            retry_error = str(exc)
        assert retry_blocked is True, "quota_exhausted must still block matching retry after restore"

        # Also confirm reserved maximum was preserved (not refunded/zeroed).
        quota_row = None
        with psycopg.connect(urls["restore"]) as conn:
            quota_row = conn.execute(
                """SELECT r.reserved_usd, s.failure_kind, d.failure_kind
                   FROM oracle2.operating_dispatch_reservations r
                   JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)
                   JOIN oracle2.operating_dispatch_diagnoses d USING(reservation_id)
                   WHERE r.artifact_id=%s""",
                (UUID(quota_seed["quota_artifact_id"]),),
            ).fetchone()
        assert quota_row is not None
        assert quota_row[0] == Decimal("0.01"), f"reserved maximum changed: {quota_row[0]}"
        assert quota_row[1] == "quota_exhausted" and quota_row[2] == "quota_exhausted"

        # --- 9. Cadence-aware RPO measurement. ---
        rpo_exposure = t_outage - t_backup_done
        assert rpo_exposure > 0, "RPO exposure must be measured, not zero"
        assert gap_events_after == 0, "post-backup gap events must be lost"
        assert pre_events_after == SCALE_EVENTS_PRE
        assert max_sequence == SCALE_EVENTS_PRE
        assert gap_committed == SCALE_EVENTS_PRE + SCALE_EVENTS_GAP

        production_formula = {
            "worst_case_rpo_seconds": "= backup_interval_seconds (disaster at any cadence phase)",
            "average_rpo_seconds": "= backup_interval_seconds / 2",
            "disaster_during_backup_risk_seconds": "= backup_duration_seconds",
            "measured_exercise_exposure_seconds": round(rpo_exposure, 3),
            "deliberate_gap_sleep_seconds": GAP_SECONDS_TARGET,
            "note": (
                "Production RPO is bounded by the production backup cadence, not by "
                "restore speed. This exercise deliberately left a non-zero gap so the "
                "exposure is measured rather than the 0.0 s artifact of backing up "
                "immediately before the outage."
            ),
            "production_figure_status": "UNPROVEN — see what_would_be_needed",
            "what_would_be_needed": [
                "configured production backup interval (cadence) in seconds",
                "measured production-scale backup duration",
                "disaster exercise at an arbitrary cadence phase, not immediately post-backup",
                "explicit statement of any synchronous replication or WAL shipping (none claimed)",
                "confirmation that no post-backup ledger tail survives without a newer backup",
            ],
            "never_production_figures": {
                "prior_exercise_rto_seconds": 1.275,
                "prior_exercise_rpo_seconds": 0.0,
                "statement": (
                    "The 1.275 s RTO and 0.0 s RPO recorded by the 2026-10-26 full-recovery "
                    "exercise are exercise-specific and must NEVER be quoted as production "
                    "figures."
                ),
            },
        }

        RESULT.update({
            "synthetic_only": True,
            "business_accepted": False,
            "teams_producer": "UNQUALIFIED",
            "project": "s13-ops-unproven-20261026",
            "host": "edge-dev3",
            "gates": {
                "alert_firing_and_clearing": alert_result,
                "retention_cutoff": retention_result,
                "quota_accounting_after_restore": {
                    "pre_snapshot": pre_snapshot,
                    "post_snapshot": post_snapshot,
                    "snapshots_identical": pre_snapshot == post_snapshot,
                    "immutability_trigger_holds": immutability_holds,
                    "retry_blocked_after_restore": retry_blocked,
                    "retry_block_reason": retry_error,
                    "reserved_maximum_preserved": quota_row[0] == Decimal("0.01"),
                    "reserved_maximum_value": str(quota_row[0]),
                    "quota_exhausted_receipt_and_diagnosis_preserved":
                        quota_row[1] == "quota_exhausted" and quota_row[2] == "quota_exhausted",
                    "restored_tables": restored_tables,
                    "empty_tables_before_restore": empty_before,
                    "retention_on_restored_timestamps": {
                        "pre": pre_retention,
                        "post": post_retention,
                        "identical": pre_retention == post_retention,
                    },
                },
                "cadence_aware_rpo": {
                    "backup_seconds": round(backup_seconds, 3),
                    "restore_seconds": round(restore_seconds, 3),
                    "rpo_exposure_seconds": round(rpo_exposure, 3),
                    "deliberate_gap_seconds": GAP_SECONDS_TARGET,
                    "pre_backup_events": SCALE_EVENTS_PRE,
                    "gap_events_committed_after_backup": SCALE_EVENTS_GAP,
                    "gap_events_survived_restore": gap_events_after,
                    "pre_backup_events_survived_restore": pre_events_after,
                    "max_sequence_after_restore": max_sequence,
                    "lost_event_count": SCALE_EVENTS_GAP,
                    "exposure_is_measured_not_zero": rpo_exposure > 0,
                    "production_formula": production_formula,
                },
                "scale": {
                    "stages": SCALE_STAGES,
                    "retention_records": SCALE_RETENTION,
                    "quota_rows": SCALE_QUOTA_ROWS,
                    "events_pre_backup": SCALE_EVENTS_PRE,
                    "events_post_backup_gap": SCALE_EVENTS_GAP,
                    "dump_bytes": dump_path.stat().st_size,
                    "dump_sha256": dump_sha,
                },
            },
            "rows_proved": [
                "4. Alerts / retention / quota operational exercise at synthetic scale",
                "3. Production RPO honesty (cadence-aware measured proof; production figure remains UNPROVEN)",
            ],
            "rows_not_touched": [
                "1. Live FalkorDB graph census (other S13 agent)",
                "2. Real vector-model license (other S13 agent)",
                "5. Source/runtime admission beyond metadata SQL (other S13 agent)",
                "6. Business acceptance / company activation — owner hold",
                "7. Real Teams producer qualification — UNQUALIFIED",
            ],
        })
        result_path = Path(os.environ.get(
            "ORACLE2_S13_OPS_RESULT",
            "/tmp/oracle-parent24-wy02uT/s13-ops-unproven-run-20261026/ops-result.json",
        ))
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(RESULT, indent=2, default=str) + "\n")
        return RESULT
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            for name in list(created):
                try:
                    conn.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                        (name,),
                    )
                    conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Exact JUnit gates.
# ---------------------------------------------------------------------------
def test_alert_firing_and_clearing(ops_cycle):
    g = ops_cycle["gates"]["alert_firing_and_clearing"]
    assert g["scale_stages"] == SCALE_STAGES
    assert g["fired_count"] == 10  # 4 stuck + 5 failing + cost_cap
    assert "cost_cap" in g["fired_codes"]
    assert g["cleared_is_empty"] is True
    assert g["cleared_codes"] == []
    assert any(c.startswith("stuck:") for c in g["fired_codes"])
    assert any(c.startswith("failing:") for c in g["fired_codes"])
    # Partial clear removed only the stuck alarms.
    assert not any(c.startswith("stuck:") for c in g["partial_clear_codes"])
    assert any(c.startswith("failing:") for c in g["partial_clear_codes"])


def test_retention_cutoff_behavior(ops_cycle):
    g = ops_cycle["gates"]["retention_cutoff"]
    assert g["scale_records"] == SCALE_RETENTION
    d = g["decisions"]
    assert d["purge"] > 0 and d["keep"] > 0 and d["hide"] > 0
    assert sum(d.values()) == SCALE_RETENTION
    assert g["boundary"]["at_cutoff"] == "purge"
    assert g["boundary"]["one_second_inside"] == "keep"
    assert g["boundary"]["one_second_outside"] == "purge"
    assert g["unknown_kind_fails_closed"] is True
    assert g["naive_timestamp_fails_closed"] is True
    assert g["tombstone_wins"] is True
    assert g["legal_hold_defers_purge"] is True
    assert g["ttl_none_keeps"] is True


def test_quota_accounting_after_restore(ops_cycle):
    g = ops_cycle["gates"]["quota_accounting_after_restore"]
    assert g["empty_tables_before_restore"] == 0
    assert g["restored_tables"] > 0
    assert g["snapshots_identical"] is True
    assert g["immutability_trigger_holds"] is True
    assert g["retry_blocked_after_restore"] is True
    assert "quota" in g["retry_block_reason"].lower() or "diagnosed" in g["retry_block_reason"].lower()
    assert g["reserved_maximum_preserved"] is True
    assert g["quota_exhausted_receipt_and_diagnosis_preserved"] is True
    assert g["pre_snapshot"]["quota_exhausted_receipts"] == 1
    assert g["pre_snapshot"]["quota_exhausted_diagnoses"] == 1
    assert g["pre_snapshot"]["reservation_count"] == SCALE_QUOTA_ROWS
    assert g["retention_on_restored_timestamps"]["identical"] is True
    assert g["retention_on_restored_timestamps"]["post"]["evaluated"] == SCALE_QUOTA_ROWS


def test_cadence_aware_rpo_measured(ops_cycle):
    g = ops_cycle["gates"]["cadence_aware_rpo"]
    # The exposure is measured and non-zero — not the 0.0 s artifact.
    assert g["exposure_is_measured_not_zero"] is True
    assert g["rpo_exposure_seconds"] > 0
    assert g["deliberate_gap_seconds"] > 0
    # Post-backup events are honestly lost.
    assert g["gap_events_committed_after_backup"] == SCALE_EVENTS_GAP
    assert g["gap_events_survived_restore"] == 0
    assert g["lost_event_count"] == SCALE_EVENTS_GAP
    # Pre-backup ledger survives completely.
    assert g["pre_backup_events_survived_restore"] == SCALE_EVENTS_PRE
    assert g["max_sequence_after_restore"] == SCALE_EVENTS_PRE
    assert g["restore_seconds"] > 0 and g["backup_seconds"] > 0


def test_production_rpo_formula_and_non_production_disclaimer(ops_cycle):
    g = ops_cycle["gates"]["cadence_aware_rpo"]
    f = g["production_formula"]
    assert "backup_interval_seconds" in f["worst_case_rpo_seconds"]
    assert "backup_interval_seconds / 2" in f["average_rpo_seconds"]
    assert f["production_figure_status"].startswith("UNPROVEN")
    assert len(f["what_would_be_needed"]) >= 4
    never = f["never_production_figures"]
    assert never["prior_exercise_rto_seconds"] == 1.275
    assert never["prior_exercise_rpo_seconds"] == 0.0
    assert "NEVER" in never["statement"]
    assert "production" in never["statement"].lower()


def test_ops_scale_recorded(ops_cycle):
    s = ops_cycle["gates"]["scale"]
    assert s["stages"] == SCALE_STAGES
    assert s["retention_records"] == SCALE_RETENTION
    assert s["quota_rows"] == SCALE_QUOTA_ROWS
    assert s["events_pre_backup"] == SCALE_EVENTS_PRE
    assert s["events_post_backup_gap"] == SCALE_EVENTS_GAP
    assert s["dump_bytes"] > 0
    assert len(s["dump_sha256"]) == 64
