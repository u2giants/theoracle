"""Retirement never admits a legacy writer, irrespective of supplied values."""
import pytest

from oracle_brain.operating_model.retirement import require_no_legacy_activation
from oracle_brain.operating_model.retirement_checklist import verify_retirement_checklist
from test_legacy_routes_retired import packet_inputs


@pytest.mark.parametrize('generation', [True, False, 0, 1, -1, 1.0, float('nan'),
    float('inf'), '1', 'current', None, object(), {'generation': 1}, [1]])
def test_every_legacy_activation_attempt_is_unconditionally_refused(generation):
    with pytest.raises(PermissionError, match='prohibited'):
        require_no_legacy_activation('claim-extraction', generation=generation)


def test_no_argument_or_named_current_generation_also_refuse():
    with pytest.raises(PermissionError, match='prohibited'):
        require_no_legacy_activation()
    with pytest.raises(PermissionError, match='prohibited'):
        require_no_legacy_activation(current_generation=1, presented_generation=1, authorized=True)


def test_extension_exposes_no_writer_authority_helper_or_output():
    import oracle_brain.operating_model.retirement_checklist as extension
    assert not hasattr(extension, 'WriterOwnership')
    assert not hasattr(extension, 'authorize_write')
    result = verify_retirement_checklist(**packet_inputs())
    assert 'write_authorized' not in result and result['deletion_authorized'] is False
