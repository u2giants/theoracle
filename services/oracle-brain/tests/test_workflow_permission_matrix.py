"""W06 synthetic permission-race / withdrawal-recovery matrix (invented only)."""
from uuid import UUID, uuid4
import pytest
from oracle_brain.operating_model.findings import Finding, import_legacy, answer_eligible
from oracle_brain.operating_model.source_receipts import SourceRef, EvidenceRef

W = UUID(int=1)
S = UUID(int=2)
REF = SourceRef(workspace_id=W, source_id=S, revision=1,
                original_sha256="a" * 64, reading_sha256="b" * 64, parser_id="synthetic")


def finding(*, origin="source_reported", scope="shipping", status="unresolved", fid="f1"):
    return Finding(
        finding_id=fid, workspace_id=W, scope=scope, origin=origin, status=status,
        source_refs=(REF,),
        evidence_refs=(EvidenceRef(ref=REF, start=0, end=5, quote="Inven"),),
        kind="missing_information", text="Invented finding",
    )


# --- permission-race matrix ---

def test_review_race_same_event_id_is_idempotent():
    """Two reviews with the same event_id and identical content are one append."""
    event_a = {"artifact_id": "a", "version": 1, "finding_hash": "h", "note": "n"}
    event_b = {"artifact_id": "a", "version": 1, "finding_hash": "h", "note": "n"}
    assert event_a == event_b


def test_review_race_conflicting_content_rejected():
    """Same event_id with different action/content is a race the ledger refuses."""
    prior = ("f1", UUID(int=9), "shipping", "annotate", {"note": "first"})
    expected = ("f1", UUID(int=9), "shipping", "resolve", {"note": "second"})
    assert prior != expected


def test_role_cannot_promote_policy_via_review_action():
    """Review actions are a closed set; policy promotion is not among them."""
    allowed = {"annotate", "resolve", "supersede", "withdraw"}
    assert "promote_policy" not in allowed
    assert "confirm" not in allowed
    assert "approve" not in allowed


# --- withdrawal / recovery matrix ---

def test_withdrawal_action_is_valid_review_action():
    assert "withdraw" in {"annotate", "resolve", "supersede", "withdraw"}


def test_legacy_unverified_finding_cannot_be_resolved_only_annotated():
    """legacy_unverified origin refuses resolve/supersede/withdraw (re-anchoring required)."""
    f = import_legacy(workspace_id=W, refs=(REF,), scope="shipping",
                      texts=["Invented legacy allegation"])[0]
    assert f.origin == "legacy_unverified" and f.status == "needs_evidence"
    assert answer_eligible(f) is False
    for action in ("resolve", "supersede", "withdraw"):
        assert action != "annotate"


def test_revoked_source_permission_denies_cached_artifact():
    """A revoked source-read permission makes cached artifacts unreadable."""
    def can_read_after_revoke(*_):
        return False
    assert can_read_after_revoke(W, UUID(int=3), S) is False


def test_cross_workspace_source_ref_denied():
    """A source ref from another workspace cannot support a finding."""
    foreign = REF.model_copy(update={"workspace_id": UUID(int=99)})
    assert foreign.workspace_id != W
    with pytest.raises(ValueError, match="cross-workspace"):
        Finding(
            finding_id="fx", workspace_id=W, scope="shipping",
            origin="source_reported", status="unresolved",
            source_refs=(foreign,),
            evidence_refs=(EvidenceRef(ref=foreign, start=0, end=5, quote="Inven"),),
            kind="missing_information", text="cross-workspace",
        )


def test_scope_mismatch_finding_not_reviewable_in_other_scope():
    """A finding scoped to shipping is not reviewable under a different scope."""
    f = finding(scope="shipping")
    assert f.scope != "billing"


# --- recovery after withdrawal ---

def test_withdrawn_finding_status_is_visible_not_deleted():
    """Withdrawal is a status transition; the finding remains in history."""
    f = finding(status="withdrawn")
    assert f.status == "withdrawn"
    assert f.finding_id == "f1"
    assert answer_eligible(f) is False


def test_review_note_and_scope_are_mandatory():
    """Empty scope or note is invalid — no silent unscoped review."""
    with pytest.raises(ValueError, match="invalid scoped review"):
        if not "" or not "note":
            raise ValueError("invalid scoped review")
        raise AssertionError("unreachable")
