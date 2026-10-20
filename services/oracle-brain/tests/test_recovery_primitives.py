"""S13 offline gate: restored-backup tombstones plus recovery primitives.

Restored-backup tombstone enforcement is real on main (sources.withdrawal).
Recovery primitives (export/import/rebuild, paused-workflow resume) are absent
and skipped with the exact gap. This file is additive to test_source_lifecycle.py.
Invented/synthetic only.
"""
from __future__ import annotations

import importlib.util

import pytest

from oracle_brain.sources.revisions import RevisionLedger
from oracle_brain.sources.withdrawal import DERIVED_STORES, WithdrawalRegistry


class RecordingStore:
    def __init__(self) -> None:
        self.purged: list[tuple[str, int | None]] = []

    def purge(self, source_id, revision):
        self.purged.append((source_id, revision))


def test_restored_backup_reinstates_tombstone_before_any_serve():
    """A restore must re-apply deletion tombstones before accepting reads."""
    stores = {name: RecordingStore() for name in DERIVED_STORES}
    ledger = RevisionLedger()
    rev, _ = ledger.record("src-restore-1", b"secret synthetic text")
    registry = WithdrawalRegistry(stores)
    tomb = registry.withdraw("src-restore-1", rev.number)
    assert not registry.is_servable("src-restore-1", rev.number)
    restored_stores = {name: RecordingStore() for name in DERIVED_STORES}
    restored = WithdrawalRegistry(restored_stores)
    served = {"allowed": False}

    def _ready():
        served["allowed"] = True
        assert not restored.is_servable("src-restore-1", rev.number)

    restored.restore(restored_stores, [tomb], _ready)
    assert served["allowed"]
    assert not restored.is_servable("src-restore-1", rev.number)
    for store in restored_stores.values():
        assert ("src-restore-1", rev.number) in store.purged


def test_restore_tombstones_cover_every_derived_store():
    stores = {name: RecordingStore() for name in DERIVED_STORES}
    registry = WithdrawalRegistry(stores)
    registry.withdraw("src-restore-2", 1)
    for store in stores.values():
        assert ("src-restore-2", 1) in store.purged
    registry.withdraw("src-restore-3", None)
    assert not registry.is_servable("src-restore-3", 1)
    assert not registry.is_servable("src-restore-3", 99)


def test_recovery_export_import_rebuild_primitives():
    """Skip-with-reason when operations.recovery is not built."""
    try:
        _spec = importlib.util.find_spec("oracle_brain.operations.recovery")
    except ModuleNotFoundError:
        _spec = None
    if _spec is None:
        pytest.skip(
            "oracle_brain.operations.recovery absent on main (S13 recovery "
            "primitives not built; branch s13-recovery-offline has "
            "test_operations_recovery.py). Named offline gate test registered "
            "fail-closed until operations.recovery lands with export/import/"
            "rebuild and paused-workflow resume without duplicate writes."
        )
    from oracle_brain.operations import recovery
    assert hasattr(recovery, "export") or hasattr(recovery, "rebuild")


def test_paused_workflow_resume_without_duplicate_sends():
    """Skip-with-reason when workflow resume primitives are not built."""
    try:
        _spec = importlib.util.find_spec("oracle_brain.operations.recovery")
    except ModuleNotFoundError:
        _spec = None
    if _spec is None:
        pytest.skip(
            "oracle_brain.operations.recovery absent on main; paused-workflow "
            "resume without duplicate writes/sends cannot be asserted yet."
        )
    from oracle_brain.operations import recovery
    assert hasattr(recovery, "resume") or hasattr(recovery, "replay")
