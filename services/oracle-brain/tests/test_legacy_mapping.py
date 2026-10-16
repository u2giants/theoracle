"""Pure legacy mapping decisions; originals only, fixture-only, no live store."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from oracle_brain.migration.inventory import (
    LegacyInventory,
    LegacyPermission,
    LegacySourceRecord,
)
from oracle_brain.migration.legacy_mapping import (
    build_manifest,
    map_record,
    quarantine_record,
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


def inventory(*records):
    return LegacyInventory(inventory_id=uuid4(), captured_at=NOW, records=tuple(records))


def test_confirmed_original_maps_accepted_with_original_attribution():
    entry = map_record(record())
    assert entry.decision == "accepted_original"
    assert entry.target.target_kind == "source"
    assert entry.target.attribution_legacy_id == "legacy-1"
    assert entry.target.redirect_legacy_id == "legacy-1"


def test_claim_kind_maps_to_claim_target():
    entry = map_record(record(kind="claim"))
    assert entry.decision == "accepted_original"
    assert entry.target.target_kind == "claim"


def test_ai_summary_is_never_a_primary_source():
    entry = map_record(record(kind="summary", is_ai_summary=True))
    assert entry.decision == "excluded_ai_summary"
    assert entry.target.target_kind == "excluded"


def test_missing_original_is_legacy_unverified():
    entry = map_record(record(has_original=False))
    assert entry.decision == "legacy_unverified"
    assert "excluded from confirmed policy answers" in entry.reason


def test_unconfirmed_claim_remains_unconfirmed():
    for state in ("unreviewed", "pending", "rejected", "withdrawn"):
        entry = map_record(record(review_state=state))
        assert entry.decision == "excluded_unconfirmed"


def test_quarantine_override_reports_mapping_category():
    entry = quarantine_record(record(), "conflicting permission evidence")
    assert entry.decision == "quarantined"
    assert entry.target.target_kind == "quarantine"
    with pytest.raises(ValueError, match="reason"):
        quarantine_record(record(), "")


def test_accepted_entry_requires_attribution_and_rejects_wrong_redirect():
    from oracle_brain.migration.legacy_mapping import LegacyMappingEntry, MappingTarget

    with pytest.raises(ValueError, match="attribution"):
        LegacyMappingEntry(
            legacy_id="legacy-1",
            decision="accepted_original",
            reason="bad",
            target=MappingTarget(
                target_kind="source",
                attribution_legacy_id="other",
                redirect_legacy_id="legacy-1",
            ),
        )
    with pytest.raises(ValueError, match="redirect"):
        LegacyMappingEntry(
            legacy_id="legacy-1",
            decision="accepted_original",
            reason="bad",
            target=MappingTarget(
                target_kind="source",
                attribution_legacy_id="legacy-1",
                redirect_legacy_id="other",
            ),
        )


def test_manifest_covers_every_inventory_row_once():
    inv = inventory(
        record("legacy-1"),
        record("legacy-2", kind="summary", is_ai_summary=True),
        record("legacy-3", has_original=False),
        record("legacy-4", review_state="pending"),
    )
    manifest = build_manifest(inv, mapping_id=uuid4())
    assert len(manifest.entries) == 4
    assert [e.legacy_id for e in manifest.entries] == [
        "legacy-1",
        "legacy-2",
        "legacy-3",
        "legacy-4",
    ]
    counts = manifest.counts()
    assert counts["accepted"] == 1
    assert counts["intentionally_excluded"] == 3
    assert counts["quarantined"] == 0
    assert counts["failed"] == 0
    assert manifest.inventory_digest == inv.content_digest()


def test_manifest_quarantine_override_and_unknown_rejection():
    inv = inventory(record("legacy-1"), record("legacy-2"))
    manifest = build_manifest(
        inv,
        mapping_id=uuid4(),
        quarantine={"legacy-2": "cannot map confidently"},
    )
    assert manifest.counts()["quarantined"] == 1
    assert manifest.counts()["accepted"] == 1
    with pytest.raises(ValueError, match="not present in inventory"):
        build_manifest(inv, mapping_id=uuid4(), quarantine={"ghost": "nope"})


def test_inventory_checksums_are_stable_and_content_bound():
    inv = inventory(record())
    assert inv.content_digest() == inv.content_digest()
    assert inv.snapshot_checksum() == inv.snapshot_checksum()
    assert inv.content_digest() != inventory(record(content_sha256=B)).content_digest()
