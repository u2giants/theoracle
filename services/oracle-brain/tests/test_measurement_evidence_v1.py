"""Invented qualified assertion content only; parsing is not qualification."""
from datetime import datetime, timezone
from uuid import UUID
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.consolidation_contracts_v1 import AssertionRevisionV1
from oracle_brain.operating_model.consultant.measurement_evidence_v1 import (
    MeasurementEvidenceV1, measurement_from_assertion_v1, PREDICATE, ASSERTION_UNIT,
)

ID = UUID('11111111-1111-4111-8111-111111111111')
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def record(**changes):
    value = dict(schema_version=1, contract='qualified-measurement-evidence-v1', amount='12.5',
        unit='money', currency='USD', period='per_week', population_id=str(ID),
        window_start='2026-10-01T00:00:00Z', window_end='2026-10-08T00:00:00Z',
        observed_through='2026-10-08T00:00:00Z', complete=True, censored=False)
    return value | changes


def assertion(value=None, **changes):
    scope = {key: {'schema_version': 1, 'mode': 'exact', 'identities': [str(ID)]}
             for key in ('process', 'customer', 'product', 'region')}
    raw = dict(schema_version=1, assertion_id=str(ID), revision=1, predecessor_hash=None,
        subject_id=str(ID), predicate=PREDICATE, value=canonical_bytes(record() if value is None else value).decode(),
        unit=ASSERTION_UNIT, provenance='documented_process', scope={'schema_version': 1, **scope},
        valid_time='evidenced', valid_from='2026-10-01T00:00:00Z', valid_to='2026-10-08T00:00:00Z',
        supporting_observations=['actual-observation'], opposing_observations=[], unknown_finding_ids=[],
        temporal_observations=['actual-temporal-observation'])
    return AssertionRevisionV1.model_validate_json(canonical_bytes(raw | changes))


def test_exact_source_value_and_unit_are_derived_without_caller_number():
    measured = measurement_from_assertion_v1(assertion(), now=NOW)
    assert measured.measurement().amount.as_tuple().digits == (1, 2, 5)
    assert measured.currency == 'USD'
    assert measured.complete and not measured.censored


@pytest.mark.parametrize('change', [
    {'amount': 12.5}, {'amount': 'NaN'}, {'amount': 'Infinity'}, {'amount': '-1'}, {'amount': '-0'},
    {'amount': '1.0'}, {'amount': '1e2'}, {'amount': '01'}, {'amount': '0.0000000000000000001'},
    {'amount': '1'*37}, {'currency': 'usd'}, {'unit': 'hours', 'currency': 'USD'},
    {'unit': ' hours'}, {'period': ''}, {'complete': 1}, {'censored': 'false'},
    {'complete': True, 'censored': True}, {'observed_through': '2026-10-07T00:00:00Z'},
    {'window_end': '2026-10-01T00:00:00Z'}, {'window_start': '2026-10-01T01:00:00+01:00'},
    {'observed_through': '2027-01-01T00:00:00Z'}, {'actor': str(ID)}, {'population_id': 'any'},
])
def test_malformed_recognized_measurement_refuses(change):
    with pytest.raises((ValueError, TypeError)):
        measurement_from_assertion_v1(assertion(record(**change)), now=NOW)


def test_currency_token_does_not_claim_iso_membership_or_conversion():
    assert measurement_from_assertion_v1(assertion(record(currency='XYZ')), now=NOW).currency == 'XYZ'


def test_missing_currency_cannot_be_inferred_from_money_or_role():
    raw = record(); del raw['currency']
    with pytest.raises(ValueError): measurement_from_assertion_v1(assertion(raw), now=NOW)


@pytest.mark.parametrize('changes', [
    {'predicate': 'ordinary'}, {'unit': 'hours'}, {'supporting_observations': []},
    {'valid_from': '2026-09-30T00:00:00Z'}, {'valid_to': '2026-10-09T00:00:00Z'},
])
def test_discriminator_and_actual_assertion_source_window_cannot_be_borrowed(changes):
    with pytest.raises(ValueError): measurement_from_assertion_v1(assertion(**changes), now=NOW)


def test_ordinary_assertions_preserve_exact_existing_body():
    old = assertion(predicate='cycle-time', unit='hours', value='12.5')
    before = canonical_bytes(old.model_dump(mode='json'))
    assert measurement_from_assertion_v1(old, now=NOW) is None
    assert canonical_bytes(old.model_dump(mode='json')) == before


def test_duplicate_or_noncanonical_value_is_not_qualified_by_generic_string():
    for raw in [canonical_bytes(record()).decode()+' ', canonical_bytes(record()).decode().replace('"amount":"12.5"', '"amount":"12.5","amount":"12.5"')]:
        with pytest.raises(ValueError): measurement_from_assertion_v1(assertion(value=raw), now=NOW)


def test_incomplete_censored_source_stays_reported_and_incomplete():
    value = measurement_from_assertion_v1(assertion(record(complete=False, censored=True)), now=NOW)
    assert not value.complete and value.censored


from test_assembly_context import context
from test_purpose_qualification_v3 import qualified_v3, serving


def test_recognized_measurement_refuses_at_actual_assembly_owner(context):
    from test_consolidation_contracts_v1 import core_fixture
    from oracle_brain.operating_model.pipeline import assembly_candidate_payload, assembly_inputs
    ctx, core, _ = core_fixture(context)
    raw = core.model_dump(mode='json')
    obs = raw['assertions'][0]['supporting_observations']
    measured = assertion(record(amount='NaN'), supporting_observations=obs, temporal_observations=obs)
    raw['assertions'] = [measured.model_dump(mode='json')]
    refs, observations, findings = assembly_inputs(tuple(e.payload for e in ctx.extractions))
    with pytest.raises(ValueError):
        assembly_candidate_payload(canonical_bytes(raw), workspace_id=ctx.job.workspace_id,
            refs=refs, observations=observations, findings=findings, candidate_contract=core.contract)


def test_whole_fresh_capture_assessment_census_and_sdk_bind_actual_measurement_value(qualified_v3,monkeypatch):
    """Actual canonical machinery, injected invented assessments; no native proof."""
    from copy import deepcopy
    from test_consolidation_contracts_v1 import temporal_qualified_fixture
    from oracle_brain.operating_model.purpose_qualification_v3 import verify_purpose_final_assembly_v3
    from oracle_brain.operating_model.sdk_projection import SDKProjection
    from oracle_brain.operating_model.paid_sdk_embeddings_v3 import processing_embedding_inventory_v3
    # Every measurement field is present in the ACTUAL invented source bytes
    # before capture/assessment. Host-injected qualification remains synthetic.
    from qualified_source_fixture_v1 import qualified_two_source_fixture_v1
    text=canonical_bytes({'metric_id':str(ID),'scope':assertion().scope.model_dump(mode='json'),'measurement':record()}).decode()
    qualified_v3=qualified_two_source_fixture_v1(monkeypatch,(text,text))
    q = temporal_qualified_fixture(qualified_v3)
    obs = q['payload']['consolidation_core']['assertions'][0]['supporting_observations']
    measured = assertion(supporting_observations=obs, temporal_observations=obs)
    fresh = temporal_qualified_fixture(qualified_v3, assertions=[measured.model_dump(mode='json')])
    assert verify_purpose_final_assembly_v3(**serving(fresh)) is None
    payload = fresh['payload']; identifier = 'assertion:'+str(ID)+':1'
    assert SDKProjection.records(payload)[identifier][1] != SDKProjection.records(q['payload']).get(identifier, ('', ''))[1]
    nodes, _ = SDKProjection.semantic_projection(payload)
    assert nodes[identifier][1].find('qualified-measurement-evidence-v1') >= 0
    before = processing_embedding_inventory_v3(payload)
    for key, value in [('amount', '13'), ('currency', 'CAD'), ('period', 'per_month'), ('population_id', '22222222-2222-4222-8222-222222222222'), ('complete', False)]:
        altered = deepcopy(payload)
        altered['consolidation_core']['assertions'][0]['value'] = canonical_bytes(record(**{key: value})).decode()
        assert processing_embedding_inventory_v3(altered) != before
        args = serving(fresh); args['payload'] = altered
        args['manifest'] = args['manifest'].model_copy(update={'content_hash': __import__('hashlib').sha256(canonical_bytes(altered)).hexdigest()})
        with pytest.raises((PermissionError, ValueError)):
            verify_purpose_final_assembly_v3(**args)
