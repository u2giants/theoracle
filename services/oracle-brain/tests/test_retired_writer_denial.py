import pytest
from uuid import uuid4
from oracle_brain.operating_model.retirement import require_no_legacy_activation
from oracle_brain.operating_model.retirement_checklist import (
    WriterOwnership, authorize_write,
)

W = uuid4()


def ownership(**changes):
    base = dict(workspace_id=W, active_generation=3, revoked_generations=(1, 2))
    base.update(changes)
    return WriterOwnership(**base)


def test_old_generation_cannot_write():
    old = ownership()
    with pytest.raises(PermissionError, match='revoked writer generation cannot write'):
        authorize_write(old, presented_generation=2, operation='claim-extraction-batch-drain')


def test_non_current_generation_cannot_write_even_before_it_is_revoked():
    with pytest.raises(PermissionError, match='revoked writer generation cannot write'):
        authorize_write(ownership(), presented_generation=99, operation='brain-synthesis')


def test_current_generation_is_authorized_for_the_named_operation():
    result = authorize_write(ownership(), presented_generation=3, operation='document-ingestion')
    assert result['write_authorized'] is True and result['generation'] == 3
    assert result['workspace_id'] == str(W)


def test_blank_operation_and_incoherent_ownership_are_rejected():
    with pytest.raises(ValueError, match='operation name'):
        authorize_write(ownership(), presented_generation=3, operation='   ')
    with pytest.raises(ValueError, match='operation name'):
        authorize_write(ownership(), presented_generation=3, operation='')
    with pytest.raises(ValueError, match='cannot be revoked'):
        WriterOwnership(workspace_id=W, active_generation=2, revoked_generations=(1, 2))
    with pytest.raises(ValueError, match='duplicate revoked generations'):
        WriterOwnership(workspace_id=W, active_generation=3, revoked_generations=(1, 1))
    with pytest.raises(ValueError):
        WriterOwnership(workspace_id=W, active_generation=0, revoked_generations=())


def test_legacy_activation_is_never_authorized_by_retirement():
    with pytest.raises(PermissionError, match='prohibited'):
        require_no_legacy_activation()
    with pytest.raises(PermissionError, match='prohibited'):
        require_no_legacy_activation('claim-extraction.ts', generation=1)
