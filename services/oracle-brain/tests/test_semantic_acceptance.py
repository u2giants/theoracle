"""Invented originals only: omissions and forged independent acceptance fail."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID

import pytest

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.coverage import Obligation, CoverageRecord
from oracle_brain.operating_model.semantic_acceptance import (
    CRITERIA, SourceRegion, FrozenCensus, IndependentAssessment, CriterionReview,
    SemanticAdmission, sealed, verify_semantic_acceptance,
)
from oracle_brain.operating_model.source_receipts import SourceRef, SourceReceipt, EvidenceRef


@pytest.fixture
def case():
    t = datetime(2026, 10, 12, 10, tzinfo=timezone.utc)
    ref = SourceRef(workspace_id=UUID(int=1), source_id=UUID(int=2), revision=1,
                    original_sha256='1'*64, reading_sha256=sha256(b'A must approve.').hexdigest(), parser_id='invented-v1')
    source = SourceReceipt(ref=ref, reading='A must approve.', display_revision='r1')
    evidence = EvidenceRef(ref=ref, start=0, end=len(source.reading), quote=source.reading)
    region = SourceRegion(region_id='section-1', kind='section', evidence=evidence)
    obligation = Obligation(obligation_id='approval', priority='essential',
                            expected='represented', evidence=evidence, reason='Explicit mandatory approval')
    census = FrozenCensus(workspace_id=ref.workspace_id, source_refs=(ref,), regions=(region,),
                          obligations=(obligation,), source_only_context_hash='2'*64,
                          source_only_dispatch_hash='3'*64, frozen_at=t, census_model='openai/gpt-6.1-sol')
    candidate = {'source_refs': [ref.model_dump(mode='json')], 'objects': ['approval-step']}
    assessment = IndependentAssessment(workspace_id=ref.workspace_id, census_hash=sealed(census),
        candidate_hash=digest(candidate), permission_hash='4'*64, protocol_hash='5'*64,
        assessor_actor=UUID(int=4), assessor_model='openai/gpt-6-astra', assessed_at=t+timedelta(seconds=2),
        dispatch_receipt_hash='6'*64, raw_response_hash='7'*64,
        coverage=(CoverageRecord(obligation_id='approval', disposition='represented',
                                 object_ids=('approval-step',), reason='Exact original approval'),),
        criteria=tuple(CriterionReview(criterion=k, verdict='pass', explanation='Invented source checked',
                                      evidence=(evidence,), object_ids=('approval-step',)) for k in sorted(CRITERIA)))
    objects = {'approval-step': (evidence,)}
    admission = SemanticAdmission(protocol_hash='5'*64, runtime_hash='8'*64,
        source_region_register_hash=digest({'regions': [region.model_dump(mode='json')]}),
        census_hash=sealed(census), assessment_hash=sealed(assessment), candidate_hash=digest(candidate),
        object_evidence_hash=digest({k: [e.model_dump(mode='json') for e in v] for k,v in objects.items()}),
        candidate_created_at=t+timedelta(seconds=1), permission_hash='4'*64, reviewer_report_hash='9'*64,
        implementer_actor=UUID(int=3), assessor_actor=UUID(int=4), candidate_model='openai/gpt-6.1-sol',
        purpose='independent-source-semantic-acceptance', expires_at=t+timedelta(hours=1))
    return dict(census=census, assessment=assessment, admission=admission,
        trusted_admission_hashes=frozenset({sealed(admission)}), source_regions=(region,),
        candidate=candidate, object_evidence=objects, runtime_hash='8'*64, permission_hash='4'*64,
        candidate_created_at=t+timedelta(seconds=1), now=t+timedelta(seconds=3),
        current_source=lambda *args: source, can_read=lambda *args: True)


def reseal(case):
    """Admit malformed fixtures too, to exercise checks beyond hash matching."""
    case['assessment'] = case['assessment'].model_copy(update={
        'census_hash': sealed(case['census']), 'candidate_hash': digest(case['candidate'])})
    case['admission'] = case['admission'].model_copy(update={
        'census_hash': sealed(case['census']), 'assessment_hash': sealed(case['assessment']),
        'candidate_hash': digest(case['candidate']),
        'source_region_register_hash': digest({'regions': [r.model_dump(mode='json') for r in case['source_regions']]}),
        'object_evidence_hash': digest({k: [e.model_dump(mode='json') for e in v] for k,v in case['object_evidence'].items()})})
    case['trusted_admission_hashes'] = frozenset({sealed(case['admission'])})


def test_independent_documentary_acceptance_does_not_authorize_release_or_company_generation(case):
    result = verify_semantic_acceptance(**case)
    assert result['semantic_accepted'] and result['essential_represented'] == 1
    assert not any(result[k] for k in ('business_accepted', 'actual_event_accepted',
                                      'hosted_accepted', 'serving_authorized', 'company_generation_authorized'))
    assert 'A must approve' not in str(result)


def test_unadmitted_self_supplied_receipt_denied_before_private_source_access(case):
    case['trusted_admission_hashes'] = frozenset()
    case['current_source'] = lambda *args: pytest.fail('unadmitted source opened')
    with pytest.raises(PermissionError, match='admission unavailable'):
        verify_semantic_acceptance(**case)


@pytest.mark.parametrize('field', ['runtime_hash', 'permission_hash'])
def test_current_input_movement_invalidates_acceptance(case, field):
    case[field] = 'a'*64
    with pytest.raises(PermissionError, match='exact current inputs'):
        verify_semantic_acceptance(**case)


def test_mutating_candidate_or_coverage_map_cannot_preserve_acceptance(case):
    case['object_evidence'] = {'approval-step': ()}
    with pytest.raises(PermissionError, match='exact current inputs'):
        verify_semantic_acceptance(**case)


def test_expired_admission_or_same_implementer_denied(case):
    case['now'] = case['admission'].expires_at
    with pytest.raises(PermissionError, match='expired'):
        verify_semantic_acceptance(**case)
    case['now'] -= timedelta(seconds=1)
    case['admission'] = case['admission'].model_copy(update={'implementer_actor': case['admission'].assessor_actor})
    reseal(case)
    with pytest.raises(PermissionError, match='own work'):
        verify_semantic_acceptance(**case)


def test_model_derived_inventory_cannot_claim_blinded_freeze(case):
    case['census'] = case['census'].model_copy(update={'frozen_at': case['candidate_created_at']})
    reseal(case)
    with pytest.raises(PermissionError, match='frozen before'):
        verify_semantic_acceptance(**case)


def test_source_access_checked_before_read_and_again_before_return(case):
    calls = []
    def permission(*args):
        calls.append(1)
        return len(calls) == 1
    case['can_read'] = permission
    with pytest.raises(PermissionError, match='source access denied'):
        verify_semantic_acceptance(**case)
    assert len(calls) == 2
    case['can_read'] = lambda *args: False
    case['current_source'] = lambda *args: pytest.fail('forbidden original opened')
    with pytest.raises(PermissionError, match='source access denied'):
        verify_semantic_acceptance(**case)


def test_original_revision_changed_or_withdrawn_denied(case):
    case['current_source'] = lambda *args: None
    with pytest.raises(PermissionError, match='changed or withdrawn'):
        verify_semantic_acceptance(**case)


def test_essential_approval_cannot_be_reclassified_unresolved(case):
    row = case['assessment'].coverage[0].model_copy(update={'disposition': 'unresolved'})
    case['assessment'] = case['assessment'].model_copy(update={'coverage': (row,)})
    reseal(case)
    with pytest.raises(ValueError, match='essential obligation omitted'):
        verify_semantic_acceptance(**case)


def test_unread_source_region_interval_is_failure(case):
    region = case['source_regions'][0]
    evidence = region.evidence.model_copy(update={'start': 1, 'quote': region.evidence.quote[1:]})
    region = region.model_copy(update={'evidence': evidence})
    case['source_regions'] = (region,)
    # An admitted census can still be malformed. Omit the original's first char.
    obligation = case['census'].obligations[0].model_copy(update={'evidence': evidence})
    case['census'] = case['census'].model_copy(update={'regions': (region,), 'obligations': (obligation,)})
    reseal(case)
    with pytest.raises(ValueError, match='unread interval'):
        verify_semantic_acceptance(**case)


def test_census_cannot_omit_an_original_or_change_source_population(case):
    case['candidate'] = {**case['candidate'], 'source_refs': []}
    reseal(case)
    with pytest.raises(ValueError, match='source population'):
        verify_semantic_acceptance(**case)


@pytest.mark.parametrize('change, message', [
    ({'criterion': 'invented'}, 'unknown semantic criterion'),
    ({'verdict': 'fail'}, 'rejected semantic criterion'),
    ({'evidence': (), 'absence_inventory_hash': None}, 'lacks original support'),
    ({'evidence': (), 'absence_inventory_hash': 'a'*64}, 'complete independent inventory'),
    ({'object_ids': ('invented-step',)}, 'absent model object'),
])
def test_assessor_cannot_omit_controls_or_invent_absence(case, change, message):
    criteria = list(case['assessment'].criteria)
    criteria[0] = criteria[0].model_copy(update=change)
    case['assessment'] = case['assessment'].model_copy(update={'criteria': tuple(criteria)})
    reseal(case)
    with pytest.raises(ValueError, match=message):
        verify_semantic_acceptance(**case)


def test_same_model_assessor_cannot_claim_independence(case):
    raw = case['assessment'].model_dump(mode='json')
    raw['assessor_model'] = 'openai/gpt-6.1-sol'
    with pytest.raises(ValueError):
        IndependentAssessment.model_validate_json(__import__('json').dumps(raw))


def test_detail_gap_requires_visible_disposition_and_named_owner(case):
    detail = case['census'].obligations[0].model_copy(update={
        'obligation_id': 'detail-time', 'priority': 'detail', 'expected': 'unsupported'})
    case['census'] = case['census'].model_copy(update={'obligations': (*case['census'].obligations, detail)})
    row = CoverageRecord(obligation_id='detail-time', disposition='unsupported',
                         object_ids=(), reason='Detail is not supplied; do not invent timing')
    case['assessment'] = case['assessment'].model_copy(update={
        'coverage': (*case['assessment'].coverage, row), 'detail_gap_ids': ('detail-time',)})
    reseal(case)
    with pytest.raises(ValueError, match='named disposition owners'):
        verify_semantic_acceptance(**case)
    case['assessment'] = case['assessment'].model_copy(update={'detail_gap_owners': {'detail-time': UUID(int=3)}})
    reseal(case)
    assert verify_semantic_acceptance(**case)['detail_gap_count'] == 1


def test_missing_essential_is_not_excused_by_not_applicable_or_zero_denominator(case):
    obligation = case['census'].obligations[0].model_copy(update={'expected': 'not_applicable'})
    case['census'] = case['census'].model_copy(update={'obligations': (obligation,)})
    reseal(case)
    with pytest.raises(ValueError, match='essential obligations cannot'):
        verify_semantic_acceptance(**case)
    obligation = obligation.model_copy(update={'priority': 'detail'})
    case['census'] = case['census'].model_copy(update={'obligations': (obligation,)})
    reseal(case)
    with pytest.raises(ValueError, match='no essential obligations'):
        verify_semantic_acceptance(**case)


def test_pure_refactor_preserves_legacy_canonical_output_and_actual_assessor_boundary(case):
    calls=[];original=case['current_source'];assessor=case['admission'].assessor_actor
    def permission(workspace,actor,source):
        calls.append(('permission',actor));return actor==assessor
    def reading(workspace,source):
        assert calls[-1]==('permission',assessor)
        calls.append(('reading',source));return original(workspace,source)
    case.update(can_read=permission,current_source=reading)
    result=verify_semantic_acceptance(**case)
    # Recorded from the unchanged legacy implementation before pure factoring.
    assert digest(result)=='b3a1cf4d864ffbc8da2e9ace67bfb776085bf823c6a309d5bdf5de1abf2ea9c8'
    assert [actor for kind,actor in calls if kind=='permission']==[assessor,assessor]
