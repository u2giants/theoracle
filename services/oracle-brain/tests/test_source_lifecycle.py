"""S04 offline building block: revisions and withdrawal (fixture F12)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from oracle_brain.sources.revisions import RevisionLedger
from oracle_brain.sources.withdrawal import DERIVED_STORES, WithdrawalRegistry

MANIFEST = Path(__file__).resolve().parents[3] / "evals/oracle2/synthetic-cases.jsonl"
F12 = next(c for c in map(json.loads, MANIFEST.read_text().splitlines()) if c["id"] == "F12")


class RecordingStore:
    def __init__(self) -> None:
        self.purged: list[tuple[str, int | None]] = []

    def purge(self, source_id, revision):
        self.purged.append((source_id, revision))


def _stores():
    return {name: RecordingStore() for name in DERIVED_STORES}


def test_same_bytes_do_not_reingest_and_edits_create_revisions():
    ledger = RevisionLedger()
    first, created = ledger.record("s1", b"Old limit 18")
    again, created_again = ledger.record("s1", b"Old limit 18")
    edit, created_edit = ledger.record("s1", b"New limit 16")
    assert created and not created_again and again == first
    assert created_edit and edit.number == 2 and ledger.current("s1") == edit
    other, _ = ledger.record("s2", b"Old limit 18")
    assert other.number == 1
    reverted, created_revert = ledger.record("s1", b"Old limit 18")
    assert created_revert and reverted.number == 3 and ledger.current("s1") == reverted


def test_f12_withdrawn_revision_is_never_served():
    rows = [json.loads(line) for line in F12["input_text"].splitlines()]
    ledger, stores = RevisionLedger(), _stores()
    registry = WithdrawalRegistry(stores)
    for row in rows:
        ledger.record(row["source_id"], row["text"].encode())
    for row in rows:
        if row["status"] == "withdrawn":
            registry.withdraw(row["source_id"], row["revision"])
    servable = [r["text"] for r in rows if registry.is_servable(r["source_id"], r["revision"])]
    assert servable == ["New limit 16"]
    for store in stores.values():
        assert store.purged == [("s1", 1)]


def test_whole_source_withdrawal_keeps_unrelated_sources():
    registry = WithdrawalRegistry(_stores())
    registry.withdraw("s1")
    assert not registry.is_servable("s1", 1) and not registry.is_servable("s1", 2)
    assert registry.is_servable("s2", 1)


def test_withdrawal_requires_every_derived_store():
    stores = _stores()
    del stores["embeddings"]
    with pytest.raises(ValueError, match="embeddings"):
        WithdrawalRegistry(stores)


def test_restore_reapplies_tombstones_before_serving():
    registry = WithdrawalRegistry(_stores())
    registry.withdraw("s1", 1)
    durable = registry.tombstones()
    restored = _stores()
    order: list[str] = []

    def ready():
        assert all(s.purged == [("s1", 1)] for s in restored.values())
        order.append("ready")

    registry.restore(restored, durable, ready)
    assert order == ["ready"] and not registry.is_servable("s1", 1)
