"""Pure source lifecycle tests: revision versioning and withdrawal tombstones.

No database, network or provider is constructed. All source text is invented.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from oracle_brain.sources.revisions import (
    RevisionDecision,
    SourceRevision,
    admit_revision,
    is_current,
    original_sha256,
)
from oracle_brain.sources.withdrawal import (
    DEPENDENT_ARTIFACT_KINDS,
    WithdrawalTombstone,
    invalidation_targets_for,
    is_serveable,
    reapply_tombstones_after_restore,
    withdraw_revision,
)

S = "src-001"


def rev(source_id: str = S, revision: int = 1, digest: str = "a" * 64, content_type: str = "application/pdf") -> SourceRevision:
    return SourceRevision(
        source_id=source_id,
        revision=revision,
        original_sha256=digest,
        content_type=content_type,
    )


def data(text: bytes = b"original bytes") -> bytes:
    return text


def test_same_bytes_never_reingest_same_revision():
    first = admit_revision(source_id=S, data=data(), content_type="application/pdf", current=None)
    assert first.created is True and first.revision.revision == 1
    second = admit_revision(source_id=S, data=data(), content_type="application/pdf", current=first.revision)
    assert second.created is False and second.revision == first.revision


def test_genuine_edit_creates_new_revision():
    first = admit_revision(source_id=S, data=data(b"v1"), content_type="text/plain", current=None)
    second = admit_revision(source_id=S, data=data(b"v2"), content_type="text/plain", current=first.revision)
    assert second.created is True and second.revision.revision == 2
    assert second.revision.original_sha256 == original_sha256(b"v2")


def test_identical_bytes_cannot_change_content_type():
    first = admit_revision(source_id=S, data=data(), content_type="application/pdf", current=None)
    with pytest.raises(ValueError, match="content_type"):
        admit_revision(source_id=S, data=data(), content_type="text/plain", current=first.revision)


def test_current_revision_must_belong_to_same_source():
    first = admit_revision(source_id=S, data=data(), content_type="text/plain", current=None)
    with pytest.raises(ValueError, match="source_id"):
        admit_revision(source_id="other", data=data(), content_type="text/plain", current=first.revision)


def test_admit_rejects_bad_inputs():
    with pytest.raises(TypeError):
        admit_revision(source_id=S, data="not-bytes", content_type="text/plain", current=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="source_id"):
        admit_revision(source_id="", data=data(), content_type="text/plain", current=None)
    with pytest.raises(ValueError, match="content_type"):
        admit_revision(source_id=S, data=data(), content_type="", current=None)


def test_source_revision_strict_and_forbidden():
    with pytest.raises(ValidationError):
        SourceRevision(source_id=S, revision=0, original_sha256="a" * 64, content_type="text/plain")
    with pytest.raises(ValidationError):
        SourceRevision(source_id=S, revision=1, original_sha256="A" * 64, content_type="text/plain")
    with pytest.raises(ValidationError):
        SourceRevision(source_id=S, revision=1, original_sha256="a" * 64, content_type="text/plain", extra="x")


def test_is_current_only_on_exact_head():
    head = rev()
    assert is_current(head, head) is True
    assert is_current(head, rev(revision=2)) is False


def test_withdrawal_blocks_serving_immediately():
    r = rev()
    record = withdraw_revision(revision=r, reason="owner requested deletion")
    assert record.blocked_serving is True
    assert record.invalidation_targets == DEPENDENT_ARTIFACT_KINDS
    assert is_serveable(revision=r, tombstones=(record.tombstone,)) is False
    assert is_serveable(revision=rev(revision=2), tombstones=(record.tombstone,)) is True


def test_withdrawal_propagates_to_all_dependent_kinds():
    record = withdraw_revision(revision=rev(), reason="delete")
    assert record.invalidation_targets == (
        "graph",
        "embeddings",
        "summaries",
        "recommendations",
        "caches",
        "recoverable_checkpoints",
    )


def test_double_withdrawal_refused():
    record = withdraw_revision(revision=rev(), reason="delete")
    with pytest.raises(ValueError, match="already withdrawn"):
        withdraw_revision(revision=rev(), reason="again", existing=(record.tombstone,))


def test_withdrawal_requires_exact_types_and_aware_time():
    with pytest.raises(TypeError):
        withdraw_revision(revision="not-a-revision", reason="x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="reason"):
        withdraw_revision(revision=rev(), reason="")
    naive = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        withdraw_revision(revision=rev(), reason="x", withdrawn_at=naive)


def test_restore_reapplies_tombstones_before_serving():
    live = rev(revision=1, digest="b" * 64)
    dead = rev(revision=2, digest="c" * 64)
    record = withdraw_revision(revision=dead, reason="delete")
    restored = reapply_tombstones_after_restore(
        restored=(live, dead), tombstones=(record.tombstone,)
    )
    assert restored == (live,)
    assert is_serveable(revision=dead, tombstones=(record.tombstone,)) is False


def test_invalidation_targets_empty_for_live_source():
    assert invalidation_targets_for(revision=rev(), tombstones=()) == ()
    record = withdraw_revision(revision=rev(), reason="delete")
    assert invalidation_targets_for(revision=rev(), tombstones=(record.tombstone,)) == DEPENDENT_ARTIFACT_KINDS


def test_tombstone_strict_and_forbidden():
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        WithdrawalTombstone(source_id=S, revision=1, original_sha256="a" * 64, withdrawn_at=aware, reason="")
    with pytest.raises(ValidationError):
        WithdrawalTombstone(source_id=S, revision=1, original_sha256="A" * 64, withdrawn_at=aware, reason="x")
    with pytest.raises(ValidationError):
        WithdrawalTombstone(
            source_id=S, revision=1, original_sha256="a" * 64, withdrawn_at=aware, reason="x", extra="y"
        )


def test_decision_is_frozen():
    decision = admit_revision(source_id=S, data=data(), content_type="text/plain", current=None)
    assert isinstance(decision, RevisionDecision)
    with pytest.raises(ValidationError):
        decision.created = False  # type: ignore[misc]
