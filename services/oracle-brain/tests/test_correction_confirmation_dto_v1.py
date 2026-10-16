"""Fixture-only U4/U5 correction and confirmation DTO tests. Pure offline."""
from uuid import UUID, uuid4

import pytest

from oracle_brain.knowledge.correction_confirmation_dto_v1 import (
    ConfirmationHistoryEntryV1,
    CorrectionCandidateSubmissionV1,
    ScopedConfirmationV1,
    UserEvidenceV1,
)
from oracle_brain.operating_model.source_receipts import SourceRef


def ref(workspace_id, source_id):
    return SourceRef(
        workspace_id=workspace_id,
        source_id=source_id,
        revision=1,
        original_sha256='a' * 64,
        reading_sha256='b' * 64,
        parser_id='fixture-parser',
    )


def correction(workspace_id=None, **overrides):
    workspace_id = workspace_id or uuid4()
    source_id = uuid4()
    base = dict(
        workspace_id=workspace_id,
        actor_id=uuid4(),
        model_id=uuid4(),
        base_artifact_id=uuid4(),
        base_version=3,
        base_content_hash='c' * 64,
        next_version=4,
        source_refs=(ref(workspace_id, source_id),),
        evidence=(
            UserEvidenceV1(ref=ref(workspace_id, source_id), start=0, end=3, quote='abc'),
        ),
        correction_text='the order was revised on Tuesday',
    )
    base.update(overrides)
    return CorrectionCandidateSubmissionV1(**base)


def confirmation(**overrides):
    base = dict(
        workspace_id=uuid4(),
        actor_id=uuid4(),
        model_id=uuid4(),
        map_version=2,
        map_hash='d' * 64,
        artifact_id=uuid4(),
        artifact_version=5,
        artifact_content_hash='e' * 64,
        workflow_id='fixture-workflow',
        reviewer_scope='process-map',
        reviewer_appointment_id=uuid4(),
        reviewer_leaf_current=True,
    )
    base.update(overrides)
    return ScopedConfirmationV1(**base)


def test_valid_correction_is_new_candidate_not_truth():
    item = correction()
    assert item.is_truth is False
    assert item.truth_status == 'unadmitted-user-evidence'
    assert item.candidate_identity == (item.model_id, item.next_version)
    assert item.next_version == item.base_version + 1


def test_correction_requires_exact_next_version_and_same_model():
    with pytest.raises(ValueError, match='next version'):
        correction(next_version=6)
    with pytest.raises(ValueError, match='next version'):
        correction(base_version=4, next_version=4)


def test_correction_refuses_in_place_edit_of_admitted_content():
    with pytest.raises(ValueError, match='NEW candidate'):
        correction(targets_admitted_content=True)


def test_correction_refuses_historical_review_patch_and_population_bypass():
    with pytest.raises(ValueError, match='historical review'):
        correction(patches_historical_review=True)
    with pytest.raises(ValueError, match='source population'):
        correction(bypasses_source_population=True)


def test_correction_binds_exact_workspace_source_refs_and_evidence():
    other = uuid4()
    with pytest.raises(ValueError, match='workspace'):
        correction(source_refs=(ref(other, uuid4()),))
    workspace_id = uuid4()
    source_id = uuid4()
    foreign = UserEvidenceV1(ref=ref(uuid4(), source_id), start=0, end=2, quote='ab')
    with pytest.raises(ValueError, match='workspace'):
        correction(workspace_id=workspace_id,
                   source_refs=(ref(workspace_id, source_id),),
                   evidence=(foreign,))
    unlisted = UserEvidenceV1(ref=ref(workspace_id, uuid4()), start=0, end=2, quote='ab')
    with pytest.raises(ValueError, match='listed SourceRef'):
        correction(workspace_id=workspace_id,
                   source_refs=(ref(workspace_id, source_id),),
                   evidence=(unlisted,))


def test_correction_requires_authenticated_actor():
    with pytest.raises(ValueError, match='actor_id'):
        correction(actor_id=UUID(int=0))


def test_user_evidence_span_and_role_are_fixed():
    workspace_id = uuid4()
    source_id = uuid4()
    with pytest.raises(ValueError, match='end must be greater'):
        UserEvidenceV1(ref=ref(workspace_id, source_id), start=3, end=3, quote='abc')
    ok = UserEvidenceV1(ref=ref(workspace_id, source_id), start=0, end=3, quote='abc')
    assert ok.principal_role == 'original-user'


def test_confirmation_pins_exact_scope_and_never_grants_serving():
    item = confirmation()
    assert item.current_badge is True
    assert item.serving_granted is False
    assert item.grants_serving is False
    with pytest.raises(ValueError):
        confirmation(reviewer_scope='root')
    with pytest.raises(ValueError):
        confirmation(grants_serving=True)


def test_withdrawal_or_reviewer_revocation_removes_current_badge_keeps_history():
    item = confirmation()
    withdrawn = item.badge_after_withdrawal()
    assert withdrawn.current_badge is False
    assert withdrawn.withdrawn is True
    revoked = item.badge_after_reviewer_revocation()
    assert revoked.current_badge is False
    assert revoked.reviewer_leaf_current is False
    history = ConfirmationHistoryEntryV1(
        confirmation=item,
        badge_was_current=item.current_badge,
        removed_reason='withdrawn',
    )
    assert history.badge_was_current is True
    assert history.removed_reason == 'withdrawn'


def test_confirmation_requires_nonzero_reviewer_identity():
    with pytest.raises(ValueError, match='nonzero'):
        confirmation(reviewer_appointment_id=UUID(int=0))
