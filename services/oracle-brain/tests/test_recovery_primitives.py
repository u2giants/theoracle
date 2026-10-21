"""S13 offline gate: restored-backup tombstones plus recovery primitives.

Restored-backup tombstone enforcement is real on main (sources.withdrawal).
Non-serving orchestration and observed-effect classification are exercised;
actual export/import and durable workflow resume remain separate integration.
Invented/synthetic only.
"""
from __future__ import annotations

import pytest

from oracle_brain.sources.revisions import RevisionLedger
from oracle_brain.sources.withdrawal import DERIVED_STORES, Tombstone, WithdrawalRegistry


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
    """Exercise actual non-serving orchestration, including all-store denial."""
    from uuid import uuid4
    from oracle_brain.operations.recovery import AcceptedEvent,RecoverySnapshot,packet_digest,rebuild
    workspace,source=uuid4(),uuid4()
    item=AcceptedEvent(workspace_id=workspace,event_id=uuid4(),source_id=source,
        sequence=1,revision=1,operation='project',payload_digest='a'*64)
    packet=RecoverySnapshot(workspace_id=workspace,backup_id=uuid4(),events=(item,),
        event_packet_digest=packet_digest((item,)))
    stores={name:RecordingStore() for name in DERIVED_STORES}
    projected=[]
    result=rebuild(packet,expected_workspace_id=workspace,stores=stores,
        backup_tombstones=(),current_tombstones=(Tombstone(str(source),None),),
        prior_events=(),current_can_read=lambda _:True,project=projected.append)
    assert result.blocked==(item.event_id,) and projected==[]
    assert all(store.purged==[(str(source),None)] for store in stores.values())
    assert result.serving_authorized is False and result.live_proof_required is True


def test_paused_workflow_resume_without_duplicate_sends():
    """Uncertain observed effects never acquire permission to retry."""
    from uuid import uuid4
    from oracle_brain.operations.recovery import DeliveryObservation,resume
    observed=DeliveryObservation(workspace_id=uuid4(),effect_id=uuid4(),
        intent_digest='a'*64,state='uncertain')
    result=resume((observed,),expected_workspace_id=observed.workspace_id,
        current_allowed=lambda _:True,host_enabled=True,
        validate_retained_receipt=lambda _:pytest.fail('uncertain send must not be retried'))
    assert result[0].state=='UNKNOWN'
