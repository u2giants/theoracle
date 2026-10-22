"""Invented typed action proposals, no write/source/employee authority."""
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4
import json
import pytest
from test_assembly_context import context
from test_consolidation_contracts_v1 import core_fixture
from test_recommendation_contract import recommendation
from test_measurement_evidence_v1 import assertion, record
from oracle_brain.operating_model.contracts import ArtifactManifest, canonical_bytes, digest
from oracle_brain.operating_model.consolidation_contracts_v1 import ConsolidationCoreV1
from oracle_brain.operating_model.consolidation_recommendations_v1 import (
    QualifiedRecommendationsV1, parse_qualified_recommendations, validate_recommendation_parent,
    consulting_evidence_revision_v2,
)
from oracle_brain.operating_model.consultant.recommendations import recommendation_to_payload
from oracle_brain.operating_model.consultant.recommendation_actions_v1 import (
    ConsultingRecommendationV2, FeedbackCommandV1, MeasurementCommandV1,
    source_bound_measurement_v1, observed_difference_v1,
)
from oracle_brain.operating_model.consultant.measurement_evidence_v1 import MeasurementEvidenceV1

ID = UUID('11111111-1111-4111-8111-111111111111')
OTHER = UUID('22222222-2222-4222-8222-222222222222')
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def parent_case(context):
    _, core, _ = core_fixture(context)
    payload = {'consolidation_core': core.model_dump(mode='json'),
               'source_refs': [r.model_dump(mode='json') for r in core.model.source_refs]}
    parent = ArtifactManifest(workspace_id=core.model.workspace_id, artifact_id=core.model.model_id,
        version=1, kind='processing_qualified_model_v1', input_digest='a'*64, source_digest='b'*64,
        permission_digest='c'*64, compiler_digest='d'*64, dependency_digest='e'*64,
        content_hash=digest(payload), private_object_key='operating-model/invented.json', state='ready')
    return core, payload, parent


def item_case(context, lens='approval_exception'):
    core, payload, parent = parent_case(context)
    evidence = consulting_evidence_revision_v2(core, parent, payload)
    advice = recommendation(lens=lens, opposing_evidence=(), opposing_unknown=True)
    ref = evidence.evidence_refs[0]
    advice = replace(advice, recommendation_id=str(ID), evidence=evidence,
        options=tuple(replace(option, evidence_refs=(ref,)) for option in advice.options))
    plan = dict(schema_version=1, experiment_id=str(OTHER), option_id='opt:1', metric_id=str(ID),
        unit='money', currency='USD', period='per_week', population_id=str(ID),
        baseline_start='2026-10-01T00:00:00Z', baseline_end='2026-10-08T00:00:00Z',
        followup_start='2026-10-08T00:00:00Z', followup_end='2026-10-15T00:00:00Z',
        success_metric='Compare reported cost for same population', reversible_step='Revert the bounded trial')
    item = ConsultingRecommendationV2.model_validate_json(canonical_bytes(dict(schema_version=1,
        recommendation_id=str(ID), advice=recommendation_to_payload(advice),
        scope=core.assertions[0].scope.model_dump(mode='json'), problem='Reported approval delay',
        competing_explanations=['Missing information may explain the delay'], effort='Unknown pending measurement',
        risks=['Downstream effort is not yet measured'], owner_role_description='Process owner, not an appointment',
        review_due='2026-10-20T00:00:00Z', experiments=[plan])))
    body = dict(schema_version=1, contract='qualified-consulting-recommendations-v2',
        parent_model_id=str(parent.artifact_id), parent_version=parent.version, parent_content_hash=parent.content_hash,
        recommendations=[item.model_dump(mode='json')])
    return item, body, core, payload, parent


def selector():
    return dict(schema_version=1, artifact_id=str(OTHER), artifact_version=1,
                artifact_sha256='f'*64, recommendation_id=str(ID))


def command(operation='feedback', **changes):
    value = dict(schema_version=1, operation=operation, selector=selector(), expected_head=0,
        command_id=str(uuid4()), caller_deadline='2026-10-21T00:00:20Z')
    if operation == 'feedback':
        value.update(decision='accept', option_id='opt:1', reason='Try the bounded reversible option')
        cls = FeedbackCommandV1
    else:
        value.update(experiment_id=str(OTHER), phase='baseline', assertion_id=str(ID), assertion_revision=1)
        cls = MeasurementCommandV1
    return cls.model_validate_json(canonical_bytes(value | changes))


@pytest.mark.parametrize('lens', ['handoff_rework', 'approval_exception', 'information_duplication'])
def test_actual_canonical_v2_owner_validates_all_three_lenses_and_no_change(context, lens):
    item, body, core, payload, parent = item_case(context, lens)
    candidate = {'source_refs': payload['source_refs'], 'findings': [], 'recommendations': body}
    manifest = parent.model_copy(update={'artifact_id': OTHER, 'kind': 'processing_recommendation_v1',
        'content_hash': digest(candidate)})
    parsed = validate_recommendation_parent(manifest, candidate, parent, payload)
    assert parsed.recommendations[0].advice['lens'] == lens
    assert sum(option['is_no_change'] for option in item.advice['options']) == 1
    assert item.expected_benefit == 'unknown' and not item.policy_accepted and not item.effect_executed


def test_old_v1_protocol_bytes_and_hash_do_not_change(context):
    core, payload, parent = parent_case(context)
    v1 = dict(schema_version=1, contract='qualified-documentary-recommendations-v1',
        parent_model_id=str(parent.artifact_id), parent_version=1, parent_content_hash=parent.content_hash,
        recommendations=[dict(schema_version=1, recommendation_id=str(ID), proposal='Investigate only',
            assertion_ids=[str(core.assertions[0].assertion_id)], unknowns=['Unmeasured'], measured_benefit='unknown', policy_accepted=False)])
    before = canonical_bytes(v1)
    assert type(parse_qualified_recommendations(v1)) is QualifiedRecommendationsV1
    assert canonical_bytes(parse_qualified_recommendations(v1).model_dump(mode='json')) == before
    assert digest(v1) == __import__('hashlib').sha256(before).hexdigest()


@pytest.mark.parametrize('damage', ['parent-hash', 'workspace', 'generic-report', 'source-population', 'unknown-protocol', 'evidence-seal', 'broaden-scope', 'invent-opposition', 'measured-benefit', 'execute'])
def test_canonical_v2_parent_or_authority_substitution_refuses(context, damage):
    item, body, core, payload, parent = item_case(context)
    candidate = {'source_refs': payload['source_refs'], 'findings': [], 'recommendations': body}
    manifest = parent.model_copy(update={'artifact_id': OTHER, 'kind': 'processing_recommendation_v1'})
    if damage == 'parent-hash': body['parent_content_hash'] = '0'*64
    elif damage == 'workspace': manifest = manifest.model_copy(update={'workspace_id': OTHER})
    elif damage == 'generic-report': manifest = manifest.model_copy(update={'kind': 'report'})
    elif damage == 'source-population': candidate['source_refs'] = []
    elif damage == 'unknown-protocol': body['contract'] = 'recommendations'
    elif damage == 'evidence-seal': body['recommendations'][0]['advice']['evidence']['evidence_seal'] = '0'*64
    elif damage == 'broaden-scope': body['recommendations'][0]['scope']['customer'] = {'schema_version': 1, 'mode': 'unknown', 'identities': []}
    elif damage == 'invent-opposition':
        body['recommendations'][0]['advice']['opposing_unknown'] = False
        body['recommendations'][0]['advice']['opposing_evidence'] = list(item.advice['evidence']['evidence_refs'])
    elif damage == 'measured-benefit': body['recommendations'][0]['expected_benefit'] = 'realized'
    elif damage == 'execute': body['recommendations'][0]['effect_executed'] = True
    with pytest.raises((PermissionError, ValueError)):
        validate_recommendation_parent(manifest, candidate, parent, payload)


@pytest.mark.parametrize('decision', ['accept', 'reject', 'defer'])
def test_personal_decision_does_not_claim_policy_or_fact_approval(decision):
    value = command(decision=decision, option_id='opt:1' if decision == 'accept' else None)
    assert value.decision == decision
    assert not any(key in value.model_dump() for key in ['workspace_id', 'actor_id', 'policy_accepted', 'falsifies_facts'])


@pytest.mark.parametrize('change', [
    {'decision': 'approve-policy'}, {'decision': 'reject'}, {'decision': 'accept', 'option_id': None},
    {'expected_head': True}, {'reason': ' '}, {'actor_id': str(ID)}, {'workspace_id': str(ID)}, {'effect_executed': True},
])
def test_closed_personal_feedback_refuses_authority_and_missing_cas(change):
    with pytest.raises(ValueError): command(**change)


@pytest.mark.parametrize('change', [{'amount': '12'}, {'unit': 'money'}, {'currency': 'USD'}, {'source_path': '/private'}, {'observed_through': NOW.isoformat()}, {'phase': 'actual-savings'}])
def test_measurement_request_cannot_supply_numeric_or_permission_facts(change):
    with pytest.raises(ValueError): command('measurement', **change)


def test_complete_comparison_is_only_reported_difference_and_incomplete_is_unavailable():
    baseline = MeasurementEvidenceV1.model_validate_json(canonical_bytes(record()))
    followup = MeasurementEvidenceV1.model_validate_json(canonical_bytes(record(amount='10',
        window_start='2026-10-08T00:00:00Z', window_end='2026-10-15T00:00:00Z', observed_through='2026-10-15T00:00:00Z')))
    result = observed_difference_v1(baseline, followup, now=NOW)
    assert result['observed_difference'] == '2.5'
    assert not result['causal_savings'] and not result['realized_savings_verified']
    incomplete = followup.model_copy(update={'complete': False, 'censored': True})
    assert observed_difference_v1(baseline, incomplete, now=NOW)['observed_difference'] is None
    with pytest.raises(ValueError): observed_difference_v1(baseline, followup.model_copy(update={'currency': 'CAD'}), now=NOW)


def test_actual_measurement_is_derived_from_exact_parent_assertion_and_scope(context):
    item, body, core, payload, parent = item_case(context)
    measured = assertion()
    raw = core.model_dump(mode='json'); raw['assertions'] = [measured.model_dump(mode='json')]
    current = ConsolidationCoreV1.model_validate_json(canonical_bytes(raw))
    item = item.model_copy(update={'scope': measured.scope})
    result = source_bound_measurement_v1(current, item, command('measurement'), now=NOW)
    assert result['measurement']['amount'] == '12.5' and result['reported_only']
    wrong = command('measurement', assertion_revision=2)
    with pytest.raises(PermissionError): source_bound_measurement_v1(current, item, wrong, now=NOW)
