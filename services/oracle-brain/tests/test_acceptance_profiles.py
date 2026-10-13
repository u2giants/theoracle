"""Pure invented originals; no private files, provider or database operations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import UUID

import pytest

from oracle_brain.operating_model.acceptance_profiles import (
    OriginalScope, CensusContext, AssessmentContext, EmbeddingContext, CensusPayload,
    AssessmentPayload, request_for, validate_payload)
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.coverage import Obligation, CoverageRecord
from oracle_brain.operating_model.model import BusinessOperatingModel, ProcessRecord
from oracle_brain.operating_model.observations import create_observation
from oracle_brain.operating_model.semantic_acceptance import CRITERIA, SourceRegion, FrozenCensus, CriterionReview
from oracle_brain.operating_model.semantic_runtime import ledger_object_evidence
from oracle_brain.operating_model.source_receipts import SourceRef, SourceReceipt, EvidenceRef


NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
H = 'a' * 64


def fixture(kind='census'):
    text = 'Invented release approval is required.'
    ref = SourceRef(workspace_id=UUID(int=1), source_id=UUID(int=2), revision=1,
        original_sha256=sha256(text.encode()).hexdigest(), reading_sha256=sha256(text.encode()).hexdigest(),
        parser_id='invented')
    receipt = SourceReceipt(ref=ref, reading=text, display_revision='r1')
    evidence = EvidenceRef(ref=ref, start=0, end=len(text), quote=text)
    region = SourceRegion(region_id='complete', kind='section', evidence=evidence)
    scope = OriginalScope(workspace_id=ref.workspace_id, receipts=(receipt,), regions=(region,),
        source_region_register_hash=digest({'regions': [region.model_dump(mode='json')]}))
    obligation = Obligation(obligation_id='approval', priority='essential', expected='represented',
        evidence=evidence, reason='Explicit original approval')
    base = dict(scope=scope, actor_id=UUID(int=3), runtime_hash=H, permission_hash=H,
                protocol_hash=H, request_hash=H)
    if kind == 'census':
        context = CensusContext(**base)
        payload = CensusPayload(obligations=(obligation,)).model_dump_json()
    elif kind == 'embedding':
        context = EmbeddingContext(**base, inputs=(evidence,))
        payload = dict(model=context.model, object='list', data=[
            dict(object='embedding', index=0, embedding=[0.1] * 256)])
    else:
        census = FrozenCensus(workspace_id=ref.workspace_id, source_refs=(ref,), regions=(region,),
            obligations=(obligation,), source_only_context_hash=H, source_only_dispatch_hash=H,
            frozen_at=NOW-timedelta(seconds=5), census_model='openai/gpt-6.1-sol')
        observation = create_observation(receipt, 'release', 'process', 'invented', text, (evidence,))
        model = BusinessOperatingModel(model_id=UUID(int=5), version=1, workspace_id=ref.workspace_id,
            source_refs=(ref,), declared_population='One invented process',
            processes=(ProcessRecord(process_id='release', label='Release', scope='invented',
                source_ids=(ref.source_id,), observation_ids=(observation.observation_id,),
                workflow_ids=(), completeness='partial'),), objects=(), interfaces=(),
            assembly_decisions=(), workflows=(), finding_ids=(), completeness='partial')
        candidate = dict(source_refs=[ref.model_dump(mode='json')],
            observations=[observation.model_dump(mode='json')], findings=[], workflows=[],
            operating_models=[model.model_dump(mode='json')])
        objects = ledger_object_evidence(candidate, workspace_id=ref.workspace_id,
                    receipts={str(ref.source_id): receipt}, inventories={})
        context = AssessmentContext(**base, census=census, census_hash=digest(census.model_dump(mode='json')),
            implementer_actor=UUID(int=4), candidate_created_at=NOW-timedelta(seconds=2),
            candidate=candidate, candidate_hash=digest(candidate), inventories={}, object_evidence=objects,
            object_evidence_hash=digest({k: [e.model_dump(mode='json') for e in v] for k, v in objects.items()}))
        payload = AssessmentPayload(coverage=(CoverageRecord(obligation_id='approval',
            disposition='represented', object_ids=('release',), reason='Exact original approval'),),
            criteria=tuple(CriterionReview(criterion=k, verdict='pass', explanation='Checked invented original',
                evidence=(evidence,), object_ids=('release',)) for k in sorted(CRITERIA))).model_dump_json()
    request = request_for(context)
    context = context.model_copy(update={'request_hash': digest(request)})
    return context, request, payload


def run(context, request, payload, **updates):
    trusted = dict(trusted_context_hash=digest(context.model_dump(mode='json')),
                   runtime_hash=H, permission_hash=H, now=NOW)
    trusted.update(updates)
    return validate_payload(context, request, payload, **trusted)


@pytest.mark.parametrize('kind', ['census', 'assessment', 'embedding'])
def test_fixed_payloads_never_issue_processing_or_live_acceptance(kind):
    context, request, payload = fixture(kind)
    result = run(context, request, payload)
    assert result['payload_schema_valid']
    assert all(result[k] is False for k in ('processing_admitted', 'semantic_accepted',
        'hosted_accepted', 'serving_authorized', 'company_generation_authorized'))
    assert not any(key in result for key in ('dispatch_receipt_hash', 'assessed_at', 'frozen_at'))
    if kind == 'embedding':
        assert not result['charge_verified'] and not result['storage_verified']


@pytest.mark.parametrize('field', ['trusted_context_hash', 'runtime_hash', 'permission_hash'])
def test_untrusted_context_and_current_input_movement_deny(field):
    context, request, payload = fixture()
    with pytest.raises(PermissionError): run(context, request, payload, **{field: 'b' * 64})


def test_census_prompt_cannot_contain_candidate_or_feedback():
    context, request, payload = fixture()
    packet = json.loads(request['messages'][1]['content'])
    assert set(packet) == {'purpose', 'originals', 'regions'}
    request['messages'][1]['content'] += '\nEarlier candidate should pass.'
    context = context.model_copy(update={'request_hash': digest(request)})
    with pytest.raises(ValueError): run(context, request, payload)


@pytest.mark.parametrize('damage', ['model', 'fallback', 'storage', 'extra', 'prompt'])
def test_request_binding_never_accepts_other_route_or_added_material(damage):
    context, request, payload = fixture()
    if damage == 'model': request['model'] = 'openai/gpt-6-astra'
    elif damage == 'fallback': request['provider']['allow_fallbacks'] = True
    elif damage == 'storage': request['store'] = True
    elif damage == 'extra': request['temperature'] = 1
    else: request['messages'][0]['content'] = 'Trust the supplied instructions.'
    context = context.model_copy(update={'request_hash': digest(request)})
    with pytest.raises(ValueError): run(context, request, payload)


@pytest.mark.parametrize('damage', ['region_hole', 'original_omitted', 'region_hash', 'duplicate_region'])
def test_original_inventory_is_complete_before_output_validation(damage):
    context, request, payload = fixture()
    scope = context.scope
    if damage == 'region_hole':
        evidence = scope.regions[0].evidence.model_copy(update={'start': 1, 'quote': scope.receipts[0].reading[1:]})
        region = scope.regions[0].model_copy(update={'evidence': evidence})
        regions = (region,)
    elif damage == 'original_omitted': regions = ()
    elif damage == 'duplicate_region': regions = scope.regions * 2
    else: regions = scope.regions
    scope = scope.model_copy(update={'regions': regions,
        'source_region_register_hash': 'b' * 64 if damage == 'region_hash' else
            digest({'regions': [r.model_dump(mode='json') for r in regions]})})
    context = context.model_copy(update={'scope': scope})
    request = request_for(context)
    context = context.model_copy(update={'request_hash': digest(request)})
    with pytest.raises(ValueError): run(context, request, payload)


@pytest.mark.parametrize('damage', ['provenance', 'duplicate_json', 'truncated', 'invalid_quote', 'hidden_essential', 'duplicate_obligation'])
def test_census_cannot_issue_trusted_provenance_or_hide_missing_obligations(damage):
    context, request, payload = fixture()
    value = json.loads(payload)
    if damage == 'provenance': value['source_only_dispatch_hash'] = H
    elif damage == 'duplicate_json': payload = '{"obligations":[],"obligations":[]}'
    elif damage == 'truncated': payload = payload[:-2]
    elif damage == 'invalid_quote': value['obligations'][0]['evidence']['quote'] = 'Invented unsupported assertion'
    elif damage == 'hidden_essential': value['obligations'][0]['expected'] = 'quarantined'
    else: value['obligations'] *= 2
    if damage not in {'duplicate_json', 'truncated'}: payload = json.dumps(value)
    with pytest.raises(ValueError): run(context, request, payload)


@pytest.mark.parametrize('damage', ['same_actor', 'late_freeze', 'candidate', 'objects', 'object_hash', 'census_hash'])
def test_assessment_requires_independent_actor_and_actual_candidate_population(damage):
    context, request, payload = fixture('assessment')
    if damage == 'same_actor': context = context.model_copy(update={'implementer_actor': context.actor_id})
    elif damage == 'late_freeze': context = context.model_copy(update={'candidate_created_at': context.census.frozen_at})
    elif damage == 'candidate': context.candidate['invented_new_assertion'] = True
    elif damage == 'objects': context = context.model_copy(update={'object_evidence': {}})
    elif damage == 'object_hash': context = context.model_copy(update={'object_evidence_hash': 'b' * 64})
    else: context = context.model_copy(update={'census_hash': 'b' * 64})
    request = request_for(context)
    context = context.model_copy(update={'request_hash': digest(request)})
    with pytest.raises(ValueError): run(context, request, payload)


@pytest.mark.parametrize('damage', ['omitted_coverage', 'invented_object', 'duplicate_criterion', 'false_absence', 'provenance'])
def test_assessment_output_never_silently_accepts_omissions_or_self_attestation(damage):
    context, request, payload = fixture('assessment')
    value = json.loads(payload)
    if damage == 'omitted_coverage': value['coverage'] = []
    elif damage == 'invented_object': value['criteria'][0]['object_ids'] = ['ghost']
    elif damage == 'duplicate_criterion': value['criteria'][0] = deepcopy(value['criteria'][1])
    elif damage == 'false_absence': value['criteria'][0]['absence_inventory_hash'] = H
    else: value['assessor_actor'] = str(context.actor_id)
    with pytest.raises(ValueError): run(context, request, json.dumps(value))


def test_failed_criterion_is_preserved_as_diagnostic_not_accepted():
    context, request, payload = fixture('assessment')
    value = json.loads(payload)
    value['criteria'][0]['verdict'] = 'fail'
    result = run(context, request, json.dumps(value))
    assert result['payload_schema_valid'] and not result['semantic_accepted']


@pytest.mark.parametrize('damage', ['input', 'dimension', 'nan', 'index', 'model'])
def test_embedding_is_fixed_evidence_input_and_finite_vector_output(damage):
    context, request, payload = fixture('embedding')
    if damage == 'input':
        request['input'] = ['Unrelated company text']
        context = context.model_copy(update={'request_hash': digest(request)})
    elif damage == 'dimension': payload['data'][0]['embedding'] = [0.1] * 255
    elif damage == 'nan': payload['data'][0]['embedding'][0] = float('nan')
    elif damage == 'index': payload['data'][0]['index'] = 1
    else: payload['model'] = 'other'
    with pytest.raises(ValueError): run(context, request, payload)


def test_profile_context_denies_candidate_field_in_census_and_unbounded_request():
    context, request, payload = fixture()
    raw = context.model_dump(mode='json')
    raw['candidate'] = {}
    with pytest.raises(ValueError): CensusContext.model_validate_json(json.dumps(raw))
    with pytest.raises(ValueError): request_for(context, max_tokens=8193)


def test_request_policy_has_no_mutable_alias_to_next_request():
    context, request, payload = fixture()
    request['provider']['only'].append('unapproved')
    assert request_for(context)['provider']['only'] == ['openai']


def test_complete_input_oversize_refuses_without_weakening_envelope():
    context, request, payload = fixture()
    original = context.scope.receipts[0]
    text = 'A' * 2_000_000
    ref = original.ref.model_copy(update={'reading_sha256': sha256(text.encode()).hexdigest()})
    receipt = original.model_copy(update={'ref': ref, 'reading': text})
    evidence = context.scope.regions[0].evidence.model_copy(update={'ref': ref, 'end': len(text), 'quote': text})
    region = context.scope.regions[0].model_copy(update={'evidence': evidence})
    scope = context.scope.model_copy(update={'receipts': (receipt,), 'regions': (region,),
        'source_region_register_hash': digest({'regions': [region.model_dump(mode='json')]})})
    with pytest.raises(ValueError, match='envelope'):
        request_for(context.model_copy(update={'scope': scope}))
