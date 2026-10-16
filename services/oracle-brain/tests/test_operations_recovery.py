from datetime import datetime, timezone

import pytest

from oracle_brain.operations.recovery import (
    AcceptedEvent,
    BlobCopy,
    ProjectionState,
    RestoreReceipt,
    Tombstone,
    enforce_tombstones,
    reconcile,
    replay,
    resume_effects,
)

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def event(event_id: str, subject: str, ack: bool = True) -> AcceptedEvent:
    return AcceptedEvent(event_id, subject, DIGEST_A, acknowledged=ack)


def test_restore_receipt_dto_validation():
    receipt = RestoreReceipt(
        target_id="fresh-target",
        source_metadata_restored=True,
        blobs=(BlobCopy(DIGEST_A, 10), BlobCopy(DIGEST_B, 0)),
        tombstone_count=1,
        accepted_event_count=2,
        recorded_at=NOW,
    )
    assert receipt.blobs[0].digest == DIGEST_A
    with pytest.raises(ValueError):
        RestoreReceipt("t", True, (), 0, 0, NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        BlobCopy("not-a-digest", 1)
    with pytest.raises(ValueError):
        BlobCopy(DIGEST_A, -1)
    with pytest.raises(ValueError):
        AcceptedEvent("e", "s", "short")


def test_replay_is_idempotent():
    events = [event("e1", "s1"), event("e2", "s2")]
    empty = ProjectionState(readable_subject_ids=frozenset({"s1", "s2"}))
    first = replay(events, empty)
    assert first.applied == ("e1", "e2") and first.duplicates == () and first.blocked == ()
    second = replay(events, first.state)
    assert second.applied == () and second.duplicates == ("e1", "e2")
    assert second.state.applied_event_ids == first.state.applied_event_ids
    # Full replay of the surviving ledger is graph-loss zero: every event accounted.
    assert len(first.state.applied_event_ids) == 2


def test_tombstone_enforcement_blocks_reads_before_accepting_them():
    state = ProjectionState(readable_subject_ids=frozenset({"keep", "gone"}))
    sealed = enforce_tombstones(state, [Tombstone("gone", "deleted")])
    assert sealed.readable_subject_ids == frozenset({"keep"})
    # A restore that replays onto the unsealed state cannot resurrect the subject.
    blocked = replay([event("e9", "gone")], sealed)
    assert blocked.applied == () and blocked.blocked == ("e9",)
    denied = enforce_tombstones(
        ProjectionState(readable_subject_ids=frozenset({"x"})), [Tombstone("x", "denied")]
    )
    assert denied.readable_subject_ids == frozenset()


def test_resume_effects_never_redispatches_a_sent_nonce():
    state = ProjectionState(
        pending_effect_nonces=frozenset({"n1", "n2", "n3"}),
        sent_effect_nonces=frozenset({"n2"}),
    )
    assert resume_effects(state) == ("n1", "n3")
    assert resume_effects(ProjectionState(sent_effect_nonces=frozenset({"n2"}))) == ()


def test_reconcile_accepts_consistent_restore_and_flags_unaccounted_evidence():
    events = [event("e1", "s1"), event("e2", "s2")]
    tombstones = [Tombstone("s3", "revoked")]
    receipt = RestoreReceipt(
        target_id="fresh-target",
        source_metadata_restored=True,
        blobs=(BlobCopy(DIGEST_A, 4),),
        tombstone_count=1,
        accepted_event_count=2,
        recorded_at=NOW,
    )
    state = enforce_tombstones(
        ProjectionState(
            applied_event_ids=frozenset({"e1", "e2"}),
            readable_subject_ids=frozenset({"s1", "s2", "s3"}),
        ),
        tombstones,
    )
    assert reconcile(receipt, events, tombstones, state) == []

    dropped = ProjectionState(applied_event_ids=frozenset({"e1"}), readable_subject_ids=frozenset({"s1", "s3"}))
    problems = reconcile(receipt, events, tombstones, dropped)
    assert "acknowledged event unaccounted e2" in problems
    assert "tombstoned subject readable s3" in problems

    bad_counts = RestoreReceipt("t", False, (BlobCopy(DIGEST_A, 1), BlobCopy(DIGEST_A, 1)), 5, 9, NOW)
    problems = reconcile(bad_counts, [], [], ProjectionState())
    assert "receipt accepted_event_count differs from ledger" in problems
    assert "receipt tombstone_count differs from tombstones" in problems
    assert "source metadata not restored" in problems
    assert "duplicate blob digest in receipt" in problems


def test_acknowledged_false_event_may_stay_unapplied_without_breach():
    events = [event("e1", "s1", ack=True), event("e0", "s1", ack=False)]
    receipt = RestoreReceipt("t", True, (), 0, 2, NOW)
    state = ProjectionState(applied_event_ids=frozenset({"e1"}), readable_subject_ids=frozenset({"s1"}))
    assert reconcile(receipt, events, [], state) == []
