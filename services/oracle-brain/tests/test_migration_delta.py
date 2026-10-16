"""Idempotent delta replay: late updates, deletions, permission changes, duplicates."""
from datetime import datetime, timezone
from uuid import uuid4

from oracle_brain.migration.backfill import (
    DeltaAdapter,
    ReplayState,
    apply_delta,
    application_for,
    build_batch,
    replay_batch,
)
from oracle_brain.migration.inventory import (
    LegacyChange,
    LegacyPermission,
    LegacySourceRecord,
)

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
A = "a" * 64
B = "b" * 64


def record(legacy_id="legacy-1", **changes):
    base = dict(
        legacy_id=legacy_id,
        kind="document",
        content_sha256=A,
        permissions=(LegacyPermission(principal_id="p1", kind="read"),),
        review_state="confirmed",
        relationships=(),
        translation_lineage=(),
        is_ai_summary=False,
        has_original=True,
    )
    base.update(changes)
    return LegacySourceRecord(**base)


def change(watermark, change_id, kind, legacy_id, rec=None):
    return LegacyChange(
        watermark=watermark,
        change_id=change_id,
        kind=kind,
        legacy_id=legacy_id,
        record=rec,
    )


def test_insert_then_late_update_applies_in_order():
    state = ReplayState(last_watermark=-1)
    insert = change(0, "c0", "insert", "legacy-1", record())
    update = change(1, "c1", "update", "legacy-1", record(content_sha256=B))
    first = apply_delta(state, insert)
    assert first.action == "applied"
    second = apply_delta(first.state, update)
    assert second.action == "applied"
    assert second.kind == "update"
    assert second.state.last_watermark == 1
    assert second.state.applied_change_ids == ("c0", "c1")


def test_deletion_delta_carries_no_record_and_applies():
    state = ReplayState(last_watermark=0, applied_change_ids=("c0",))
    deletion = change(1, "c1", "delete", "legacy-1", None)
    outcome = apply_delta(state, deletion)
    assert outcome.action == "applied"
    assert outcome.kind == "delete"
    application = application_for(deletion)
    assert application.record is None


def test_changed_permission_delta_applies():
    state = ReplayState(last_watermark=0, applied_change_ids=("c0",))
    permitted = record(
        permissions=(LegacyPermission(principal_id="p1", kind="read"),
                     LegacyPermission(principal_id="p2", kind="approve"))
    )
    delta = change(1, "c1", "permission", "legacy-1", permitted)
    outcome = apply_delta(state, delta)
    assert outcome.action == "applied"
    assert outcome.kind == "permission"
    assert application_for(delta).record.permissions[-1].kind == "approve"


def test_duplicate_delta_is_idempotent_noop():
    state = ReplayState(last_watermark=-1)
    delta = change(0, "c0", "insert", "legacy-1", record())
    first = apply_delta(state, delta)
    assert first.action == "applied"
    again = apply_delta(first.state, delta)
    assert again.action == "duplicate"
    assert again.state is first.state
    assert again.state.applied_change_ids == ("c0",)


def test_unseen_delta_at_or_below_watermark_is_rejected():
    state = ReplayState(last_watermark=5, applied_change_ids=("c0",))
    stale = change(5, "c5", "update", "legacy-1", record())
    outcome = apply_delta(state, stale)
    assert outcome.action == "rejected"
    assert outcome.state is state


def test_replay_batch_applies_only_new_changes():
    state = ReplayState(last_watermark=-1)
    batch = (
        change(0, "c0", "insert", "legacy-1", record()),
        change(1, "c1", "update", "legacy-1", record(content_sha256=B)),
        change(2, "c2", "delete", "legacy-1", None),
    )
    cursor, applications, outcomes = replay_batch(state, batch)
    assert [o.action for o in outcomes] == ["applied", "applied", "applied"]
    assert [a.kind for a in applications] == ["insert", "update", "delete"]
    assert cursor.last_watermark == 2
    cursor2, applications2, outcomes2 = replay_batch(cursor, batch)
    assert [o.action for o in outcomes2] == ["duplicate", "duplicate", "duplicate"]
    assert applications2 == ()
    assert cursor2 == cursor


def test_batch_builder_records_applied_and_quarantine_separately():
    state = ReplayState(last_watermark=-1)
    batch = build_batch(
        batch_index=0,
        cursor_before=state,
        changes=(
            change(0, "c0", "insert", "legacy-1", record()),
            change(1, "c1", "update", "legacy-1", record(content_sha256=B)),
        ),
        quarantined_change_ids=("c1",),
    )
    assert [item.change_id for item in batch.applied] == ["c0"]
    assert batch.quarantined_change_ids == ("c1",)
    assert batch.cursor_after.last_watermark == 0
    assert batch.cursor_after.applied_change_ids == ("c0",)


def test_batch_rejects_quarantine_ids_outside_batch():
    state = ReplayState(last_watermark=-1)
    try:
        build_batch(
            batch_index=0,
            cursor_before=state,
            changes=(change(0, "c0", "insert", "legacy-1", record()),),
            quarantined_change_ids=("ghost",),
        )
    except ValueError as exc:
        assert "must come from this batch" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected rejection")


def test_delta_adapter_records_mechanism_and_pause():
    feed = DeltaAdapter(mechanism="change_feed")
    assert feed.pause_seconds is None
    pause = DeltaAdapter(mechanism="write_pause_snapshot", pause_seconds=12.5)
    assert pause.pause_seconds == 12.5
    try:
        DeltaAdapter(mechanism="change_feed", pause_seconds=1.0)
    except ValueError as exc:
        assert "no write pause" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected rejection")
    try:
        DeltaAdapter(mechanism="write_pause_snapshot")
    except ValueError as exc:
        assert "measured pause" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected rejection")
