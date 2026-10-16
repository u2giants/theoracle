"""Resume at a watermark and shadow-reconcile counts; fixture-only, no live target."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from oracle_brain.migration.backfill import ReplayState, build_batch, replay_batch
from oracle_brain.migration.inventory import (
    LegacyChange,
    LegacyInventory,
    LegacyPermission,
    LegacySourceRecord,
)
from oracle_brain.migration.legacy_mapping import build_manifest
from oracle_brain.migration.reconcile import (
    ShadowManifest,
    ShadowMigrationCounts,
    check_fidelity,
    permission_digest,
    reconcile_counts,
    reconcile_manifest,
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


def test_restart_at_watermark_replays_only_unseen_changes():
    deltas = (
        change(0, "c0", "insert", "legacy-1", record()),
        change(1, "c1", "insert", "legacy-2", record("legacy-2")),
        change(2, "c2", "update", "legacy-1", record(content_sha256=B)),
    )
    cursor, applications, outcomes = replay_batch(ReplayState(last_watermark=-1), deltas[:2])
    assert cursor.last_watermark == 1
    assert [a.kind for a in applications] == ["insert", "insert"]
    assert [o.action for o in outcomes] == ["applied", "applied"]
    # Crash before batch 2. Resume at watermark 1 re-delivers c1 and c2.
    cursor2, applications2, outcomes2 = replay_batch(cursor, deltas[1:])
    assert [o.action for o in outcomes2] == ["duplicate", "applied"]
    assert [a.kind for a in applications2] == ["update"]
    assert cursor2.last_watermark == 2
    assert cursor2.applied_change_ids == ("c0", "c1", "c2")


def test_restart_never_double_applies_deletes():
    deltas = (
        change(0, "c0", "insert", "legacy-1", record()),
        change(1, "c1", "delete", "legacy-1", None),
    )
    first, apps, _ = replay_batch(ReplayState(last_watermark=-1), deltas)
    assert [a.kind for a in apps] == ["insert", "delete"]
    again, apps2, outcomes = replay_batch(first, deltas)
    assert [o.action for o in outcomes] == ["duplicate", "duplicate"]
    assert apps2 == ()
    assert again == first


def test_restart_at_watermark_with_permission_change_is_idempotent():
    permitted = record(
        permissions=(
            LegacyPermission(principal_id="p1", kind="read"),
            LegacyPermission(principal_id="p2", kind="approve"),
        )
    )
    deltas = (
        change(0, "c0", "insert", "legacy-1", record()),
        change(1, "c1", "permission", "legacy-1", permitted),
    )
    cursor, _, _ = replay_batch(ReplayState(last_watermark=-1), deltas)
    cursor2, apps, outcomes = replay_batch(cursor, deltas)
    assert apps == ()
    assert [o.action for o in outcomes] == ["duplicate", "duplicate"]
    assert cursor2 == cursor


def test_batch_resume_cursor_is_durable_ordered():
    deltas = (
        change(3, "c3", "insert", "legacy-1", record()),
        change(7, "c7", "update", "legacy-1", record(content_sha256=B)),
    )
    batch = build_batch(batch_index=0, cursor_before=ReplayState(last_watermark=2), changes=deltas)
    assert batch.cursor_before.last_watermark == 2
    assert batch.cursor_after.last_watermark == 7
    assert batch.cursor_after.applied_change_ids == ("c3", "c7")
    resumed = build_batch(
        batch_index=1,
        cursor_before=batch.cursor_after,
        changes=(change(7, "c7", "update", "legacy-1", record(content_sha256=B)),),
    )
    assert resumed.applied == ()
    assert resumed.cursor_after == batch.cursor_after


def test_shadow_counts_must_sum_to_inventory():
    counts = ShadowMigrationCounts(
        accepted=2,
        quarantined=1,
        intentionally_excluded=3,
        failed=0,
    )
    ok = reconcile_counts(6, counts)
    assert ok.complete
    assert ok.manifest_total == 6
    incomplete = reconcile_counts(7, counts)
    assert not incomplete.complete


def test_reconcile_manifest_requires_binding_and_complete_accounting():
    inv = LegacyInventory(
        inventory_id=uuid4(),
        captured_at=NOW,
        records=(
            record("legacy-1"),
            record("legacy-2", kind="summary", is_ai_summary=True),
            record("legacy-3", has_original=False),
            record("legacy-4", review_state="pending"),
        ),
    )
    mapping = build_manifest(inv, mapping_id=uuid4())
    mapped = mapping.counts()
    assert mapped == {
        "accepted": 1,
        "quarantined": 0,
        "intentionally_excluded": 3,
        "failed": 0,
    }
    manifest = ShadowManifest(
        manifest_id="shadow-1",
        inventory_digest=inv.content_digest(),
        mapping_digest=mapping.content_digest(),
        counts=ShadowMigrationCounts(
            accepted=1,
            quarantined=0,
            intentionally_excluded=3,
            failed=0,
        ),
        accepted_legacy_ids=("legacy-1",),
        intentionally_excluded_legacy_ids=("legacy-2", "legacy-3", "legacy-4"),
    )
    result = reconcile_manifest(inv, mapping, manifest)
    assert result.complete
    assert result.inventory_size == 4

    with pytest.raises(ValueError, match="do not match mapping decisions"):
        reconcile_manifest(
            inv,
            mapping,
            ShadowManifest(
                manifest_id="shadow-2",
                inventory_digest=inv.content_digest(),
                mapping_digest=mapping.content_digest(),
                counts=ShadowMigrationCounts(
                    accepted=1,
                    quarantined=0,
                    intentionally_excluded=2,
                    failed=0,
                ),
                accepted_legacy_ids=("legacy-1",),
                intentionally_excluded_legacy_ids=("legacy-2", "legacy-3"),
            ),
        )

    with pytest.raises(ValueError, match="not bound to this inventory"):
        reconcile_manifest(
            inv,
            mapping,
            ShadowManifest(
                manifest_id="shadow-3",
                inventory_digest=B,
                mapping_digest=mapping.content_digest(),
                counts=ShadowMigrationCounts(
                    accepted=1,
                    quarantined=0,
                    intentionally_excluded=3,
                    failed=0,
                ),
                accepted_legacy_ids=("legacy-1",),
                intentionally_excluded_legacy_ids=("legacy-2", "legacy-3", "legacy-4"),
            ),
        )

    with pytest.raises(ValueError, match="not bound to this mapping"):
        reconcile_manifest(
            inv,
            mapping,
            ShadowManifest(
                manifest_id="shadow-3b",
                inventory_digest=inv.content_digest(),
                mapping_digest=A,
                counts=ShadowMigrationCounts(
                    accepted=1,
                    quarantined=0,
                    intentionally_excluded=3,
                    failed=0,
                ),
                accepted_legacy_ids=("legacy-1",),
                intentionally_excluded_legacy_ids=("legacy-2", "legacy-3", "legacy-4"),
            ),
        )


def test_manifest_count_must_match_id_bucket():
    with pytest.raises(ValueError, match="does not match id bucket"):
        ShadowManifest(
            manifest_id="shadow-4",
            inventory_digest=A,
            mapping_digest=B,
            counts=ShadowMigrationCounts(
                accepted=2,
                quarantined=0,
                intentionally_excluded=0,
                failed=0,
            ),
            accepted_legacy_ids=("legacy-1",),
        )


def test_permission_and_attribution_fidelity_must_not_degrade():
    before = record()
    ok = check_fidelity(
        legacy_id="legacy-1",
        before=before,
        after_attribution="legacy-1",
        after_permission_digest=permission_digest(before),
    )
    assert ok.legacy_id == "legacy-1"
    with pytest.raises(ValueError, match="permission fidelity degraded"):
        check_fidelity(
            legacy_id="legacy-1",
            before=before,
            after_attribution="legacy-1",
            after_permission_digest=A,
        )
    with pytest.raises(ValueError, match="attribution fidelity degraded"):
        check_fidelity(
            legacy_id="legacy-1",
            before=before,
            after_attribution="other",
            after_permission_digest=permission_digest(before),
        )
