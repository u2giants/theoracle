"""Actual isolated Postgres/file blobs; invented originals, no provider calls."""
import copy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from test_operating_model_adapters import test_database
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.coverage import Obligation, CoverageRecord
from oracle_brain.operating_model.findings import Finding
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.model import BusinessOperatingModel, ProcessRecord, BusinessRecord
from oracle_brain.operating_model.observations import create_observation
from oracle_brain.operating_model.semantic_acceptance import (CRITERIA, FrozenCensus,
    SourceRegion, IndependentAssessment, CriterionReview, SemanticAdmission, sealed)
from oracle_brain.operating_model.semantic_runtime import (
    ledger_object_evidence, verify_ledger_semantic_acceptance)
from oracle_brain.operating_model.source_receipts import SourceRef, SourceReceipt, EvidenceRef
from oracle_brain.operating_model.workflows.process_model import WorkflowModel, Step, Support


@pytest.fixture
def case(test_database, tmp_path):
    workspace, source_id, actor, implementer, artifact = (uuid4() for _ in range(5))
    now = datetime.now(timezone.utc)
    text = 'The coordinator must approve the invented release.'
    ref = SourceRef(workspace_id=workspace, source_id=source_id, revision=1,
        original_sha256=sha256(text.encode()).hexdigest(),
        reading_sha256=sha256(text.encode()).hexdigest(), parser_id='invented-v1')
    source = SourceReceipt(ref=ref, reading=text, display_revision='r1')
    evidence = EvidenceRef(ref=ref, start=0, end=len(text), quote=text)
    observations = tuple(create_observation(source, kind, kind, 'test-scope', text, (evidence,))
                         for kind in ('process', 'step', 'role'))
    workflow = WorkflowModel(workflow_id='release-flow', version=1, workspace_id=workspace,
        process_id='release', scope='test-scope', source_refs=(ref,), completeness='partial',
        steps=(Step(step_id='approval', label='Approval', kind='activity',
                    support=Support(observation_ids=(observations[1].observation_id,))),),
        coverage_digest='a'*64)
    model = BusinessOperatingModel(model_id=artifact, version=1, workspace_id=workspace,
        source_refs=(ref,), declared_population='One invented release process',
        processes=(ProcessRecord(process_id='release', label='Release', scope='test-scope',
            source_ids=(source_id,), observation_ids=(observations[0].observation_id,),
            workflow_ids=(workflow.workflow_id,), completeness='partial'),),
        objects=(BusinessRecord(object_id='coordinator', kind='role', label='Coordinator',
            scope='test-scope', support=Support(observation_ids=(observations[2].observation_id,))),),
        interfaces=(), assembly_decisions=(), workflows=(workflow,), finding_ids=(), completeness='partial')
    finding = Finding(finding_id='open-detail', kind='missing_information', workspace_id=workspace,
        source_refs=(ref,), scope='test-scope', text='Invented approval timing is unspecified',
        origin='source_reported', evidence_refs=(evidence,))
    candidate = {'source_refs': [ref.model_dump(mode='json')],
        'observations': [o.model_dump(mode='json') for o in observations],
        'findings': [finding.model_dump(mode='json')],
        'workflows': [workflow.model_dump(mode='json')],
        'operating_models': [model.model_dump(mode='json')], 'raw_response': 'Invented model response'}
    ledger = Ledger(test_database, FileBlobStore(tmp_path), principal=actor,
        can_read=lambda *_: True, current_source=lambda *_: source)
    ledger.persist(workspace_id=workspace, artifact_id=artifact, version=1, kind='operating_model',
        payload=candidate, refs=(ref,), permission_digest='4'*64, compiler_digest='9'*64)
    region = SourceRegion(region_id='all', kind='section', evidence=evidence)
    census = FrozenCensus(workspace_id=workspace, source_refs=(ref,), regions=(region,),
        obligations=(Obligation(obligation_id='required-approval', priority='essential',
            expected='represented', evidence=evidence, reason='Mandatory approval'),),
        source_only_context_hash='2'*64, source_only_dispatch_hash='3'*64,
        frozen_at=now-timedelta(seconds=10), census_model='openai/gpt-6.1-sol')
    assessment = IndependentAssessment(workspace_id=workspace, census_hash=sealed(census),
        candidate_hash=digest(candidate), permission_hash='4'*64, protocol_hash='5'*64,
        assessor_actor=actor, assessor_model='openai/gpt-6-astra',
        assessed_at=now-timedelta(seconds=2), dispatch_receipt_hash='6'*64, raw_response_hash='7'*64,
        coverage=(CoverageRecord(obligation_id='required-approval', disposition='represented',
            object_ids=('release-flow:approval',), reason='Original approval preserved'),),
        criteria=tuple(CriterionReview(criterion=k, verdict='pass', explanation='Invented original checked',
            evidence=(evidence,), object_ids=('release-flow:approval',)) for k in sorted(CRITERIA)))
    object_map = ledger_object_evidence(candidate, workspace_id=workspace,
        receipts={str(source_id): source}, inventories={})
    admission = SemanticAdmission(protocol_hash='5'*64, runtime_hash='8'*64,
        source_region_register_hash=digest({'regions': [region.model_dump(mode='json')]}),
        census_hash=sealed(census), assessment_hash=sealed(assessment), candidate_hash=digest(candidate),
        object_evidence_hash=digest({k: [e.model_dump(mode='json') for e in v] for k,v in object_map.items()}),
        permission_hash='4'*64, reviewer_report_hash='b'*64,
        candidate_created_at=now-timedelta(seconds=5), implementer_actor=implementer,
        assessor_actor=actor, candidate_model='openai/gpt-6.1-sol',
        purpose='independent-source-semantic-acceptance', expires_at=now+timedelta(hours=1))
    return dict(ledger=ledger, workspace_id=workspace, artifact_id=artifact, version=1,
        census=census, assessment=assessment, admission=admission,
        trusted_admission_hashes=frozenset({sealed(admission)}), source_regions=(region,),
        runtime_hash='8'*64, expected_compiler_digest='9'*64,
        current_permission_digest=lambda *_: '4'*64, now=now, current_time=lambda: now)


def reseal(case, **updates):
    case['admission'] = case['admission'].model_copy(update=updates)
    case['trusted_admission_hashes'] = frozenset({sealed(case['admission'])})


def test_current_ledger_accepted_without_release_or_aggregate_shortcuts(case):
    result = verify_ledger_semantic_acceptance(**case)
    assert result['semantic_accepted'] and result['essential_represented'] == 1
    assert not result['serving_authorized'] and not result['company_generation_authorized']
    ledger = case['ledger']
    payload = ledger.read(case['workspace_id'], case['artifact_id'], 1)
    objects = ledger_object_evidence(payload, workspace_id=case['workspace_id'],
        receipts=ledger.authorize_refs(case['census'].source_refs, case['workspace_id']), inventories={})
    assert set(objects) == {'release', 'coordinator', 'release-flow:approval', 'open-detail'}
    assert str(case['artifact_id']) not in objects and 'release-flow' not in objects
    assert not set(o['observation_id'] for o in payload['observations']) & objects.keys()


@pytest.mark.parametrize('change', ['untrusted', 'expired', 'principal', 'runtime', 'permission', 'compiler'])
def test_refused_inputs_never_open_a_private_blob(case, monkeypatch, change):
    if change == 'untrusted': case['trusted_admission_hashes'] = frozenset()
    elif change == 'expired': case['now'] = case['admission'].expires_at
    elif change == 'principal': case['ledger'].principal = uuid4()
    elif change == 'runtime': case['runtime_hash'] = 'f'*64
    elif change == 'permission': case['current_permission_digest'] = lambda *_: 'f'*64
    elif change == 'compiler': case['expected_compiler_digest'] = 'f'*64
    if change == 'expired': case['current_time'] = lambda: case['now']
    monkeypatch.setattr(case['ledger'].blobs, 'read', lambda *_: pytest.fail('private blob opened'))
    with pytest.raises(PermissionError): verify_ledger_semantic_acceptance(**case)


def test_permission_digest_revocation_during_evaluation_refuses_receipt(case):
    calls = []
    def permissions(*_):
        calls.append(1)
        return '4'*64 if len(calls) == 1 else 'f'*64
    case['current_permission_digest'] = permissions
    with pytest.raises(PermissionError, match='permission digest'):
        verify_ledger_semantic_acceptance(**case)


def test_source_revocation_during_final_ledger_read_refuses_receipt(case):
    original = case['ledger'].read
    calls = []
    def read(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2: case['ledger'].can_read = lambda *_: False
        return original(*args, **kwargs)
    case['ledger'].read = read
    with pytest.raises(PermissionError, match='source access denied'):
        verify_ledger_semantic_acceptance(**case)


def test_invalidation_during_final_read_refuses_receipt(case):
    original = case['ledger'].read
    calls = []
    def read(*args, **kwargs):
        value = original(*args, **kwargs)
        calls.append(1)
        if len(calls) == 2:
            with psycopg.connect(case['ledger'].url) as conn:
                conn.execute('INSERT INTO oracle2.artifact_invalidations VALUES(%s,%s,%s,%s,%s,now())',
                    (case['workspace_id'], case['artifact_id'], 1, 'Changed during read', uuid4()))
        return value
    case['ledger'].read = read
    with pytest.raises(PermissionError, match='invalidated'):
        verify_ledger_semantic_acceptance(**case)


def test_admitted_ghost_projection_id_cannot_inherit_whole_model_evidence(case):
    coverage = case['assessment'].coverage[0].model_copy(update={'object_ids': ('release-flow',)})
    case['assessment'] = case['assessment'].model_copy(update={'coverage': (coverage,)})
    reseal(case, assessment_hash=sealed(case['assessment']))
    with pytest.raises(ValueError): verify_ledger_semantic_acceptance(**case)


@pytest.mark.parametrize('change', ['duplicate_observation', 'divergent_workflow', 'duplicate_component',
                                    'ghost_support', 'duplicate_finding', 'ghost_finding'])
def test_typed_current_projection_corruption_is_not_silently_overwritten(case, change):
    ledger = case['ledger']
    payload = ledger.read(case['workspace_id'], case['artifact_id'], 1)
    if change == 'duplicate_observation': payload['observations'].append(copy.deepcopy(payload['observations'][0]))
    elif change == 'divergent_workflow': payload['operating_models'][0]['workflows'][0]['steps'][0]['label'] = 'Changed'
    elif change == 'duplicate_component':
        payload['workflows'][0]['artifacts'] = [{'artifact_id': 'approval', 'label': 'Collision',
            'support': payload['workflows'][0]['steps'][0]['support']}]
    elif change == 'ghost_support': payload['workflows'][0]['steps'][0]['support']['observation_ids'] = ['ghost']
    elif change == 'duplicate_finding': payload['findings'].append(copy.deepcopy(payload['findings'][0]))
    elif change == 'ghost_finding': payload['operating_models'][0]['finding_ids'] = ['ghost']
    receipts = ledger.authorize_refs(case['census'].source_refs, case['workspace_id'])
    with pytest.raises((ValueError, PermissionError)):
        ledger_object_evidence(payload, workspace_id=case['workspace_id'], receipts=receipts, inventories={})


def test_manifest_column_drift_refuses_before_blob(case, monkeypatch):
    # Simulate an inconsistent imported row without changing append-only history.
    imported = uuid4()
    with psycopg.connect(case['ledger'].url) as conn:
        conn.execute('''INSERT INTO oracle2.artifact_manifests
            SELECT workspace_id,%s,version,kind,input_digest,source_digest,permission_digest,%s,
                dependency_digest,content_hash,private_object_key,state,
                jsonb_set(manifest,'{artifact_id}',to_jsonb(%s::text)),created_at
            FROM oracle2.artifact_manifests WHERE artifact_id=%s''',
            (imported, 'f'*64, str(imported), case['artifact_id']))
    case['artifact_id'] = imported
    monkeypatch.setattr(case['ledger'].blobs, 'read', lambda *_: pytest.fail('private blob opened'))
    with pytest.raises(PermissionError, match='manifest'):
        verify_ledger_semantic_acceptance(**case)


def test_persistence_time_cannot_replace_admitted_first_exposure(case):
    # An externally admitted first exposure after persistence cannot relabel it.
    exposure = case['now'] + timedelta(seconds=30)
    case['assessment'] = case['assessment'].model_copy(update={'assessed_at': exposure+timedelta(seconds=1)})
    reseal(case, candidate_created_at=exposure, assessment_hash=sealed(case['assessment']))
    case['now'] = exposure+timedelta(seconds=2)
    case['current_time'] = lambda: case['now']
    with pytest.raises(PermissionError, match='predates'):
        verify_ledger_semantic_acceptance(**case)


def test_accepted_map_hash_cannot_drift_from_actual_projection(case):
    reseal(case, object_evidence_hash='f'*64)
    with pytest.raises(PermissionError, match='exact current inputs'):
        verify_ledger_semantic_acceptance(**case)


def test_candidate_hash_drift_is_rejected_before_blob(case, monkeypatch):
    case['assessment'] = case['assessment'].model_copy(update={'candidate_hash': 'f'*64})
    reseal(case, candidate_hash='f'*64, assessment_hash=sealed(case['assessment']))
    monkeypatch.setattr(case['ledger'].blobs, 'read', lambda *_: pytest.fail('private blob opened'))
    with pytest.raises(PermissionError, match='candidate or source seal'):
        verify_ledger_semantic_acceptance(**case)


def test_admission_expiry_during_evaluation_refuses_receipt(case):
    calls = []
    def clock():
        calls.append(1)
        return case['now'] if len(calls) == 1 else case['admission'].expires_at
    case['current_time'] = clock
    with pytest.raises(PermissionError, match='expired'):
        verify_ledger_semantic_acceptance(**case)


def test_relational_source_ghost_is_denied_before_any_original_or_blob_read(case, monkeypatch):
    original = case['ledger'].current_source(case['workspace_id'], case['census'].source_refs[0].source_id)
    ghost = original.model_copy(update={'ref': original.ref.model_copy(update={'source_id': uuid4()})})
    with psycopg.connect(case['ledger'].url) as conn:
        conn.execute('INSERT INTO oracle2.operating_model_source_receipts VALUES(%s,%s,%s,%s,%s,%s,%s)',
            (ghost.ref.workspace_id, ghost.ref.source_id, ghost.ref.revision, ghost.ref.original_sha256,
             ghost.ref.reading_sha256, ghost.ref.parser_id, Jsonb(ghost.model_dump(mode='json'))))
        conn.execute('INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,%s,%s,%s,%s)',
            (case['workspace_id'], case['artifact_id'], 1, 'source', str(ghost.ref.source_id), '1'))
    case['ledger'].current_source = lambda *_: pytest.fail('unadmitted original opened')
    monkeypatch.setattr(case['ledger'].blobs, 'read', lambda *_: pytest.fail('private blob opened'))
    with pytest.raises(PermissionError, match='relational source population'):
        verify_ledger_semantic_acceptance(**case)
