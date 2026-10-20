"""Invented injected outputs prove integration, never real model quality."""
import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from oracle_brain.ingest.originals import read_original
from oracle_brain.operating_model.documentary_journey import build_documentary_journey
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.source_receipts import SourceRef, SourceReceipt, EvidenceRef
from oracle_brain.operating_model.model import BusinessOperatingModel, ProcessRecord, BusinessRecord, Interface
from oracle_brain.operating_model.workflows.process_model import Support
from oracle_brain.operating_model.observations import Observation
from oracle_brain.operating_model.findings import Finding
from oracle_brain.operating_model.coverage import Obligation, CoverageRecord
from oracle_brain.operating_model.retrieval import QueryPlan
from oracle_brain.operating_model.summaries import serve_summary
from oracle_brain.operating_model.answer import answer_from_summary
from oracle_brain.operating_model.source_receipts import validate_evidence
from oracle_brain.operating_model.retrieval import build_pack
from oracle_brain.operating_model.extraction import validate_response, persist_response
from oracle_brain.operating_model.pipeline import assembly_inputs, assembly_candidate_payload
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest, authorize, dispatch


class InventedProvider:
    def __init__(self):
        self.calls = []

    def extract(self, **kwargs):
        original = json.loads(kwargs['messages'][1]['content'])
        ref = SourceRef.model_validate_json(json.dumps(original['source_ref']))
        text = original['reading']
        self.calls.append((ref.source_id, text))
        evidence = EvidenceRef(ref=ref, start=0, end=len(text), quote=text)
        missing = 'unknown' in text
        finding = Finding(
            finding_id='missing-owner' if missing else 'reported-timing-conflict',
            kind='missing_information' if missing else 'source_conflict',
            workspace_id=ref.workspace_id, source_refs=(ref,), scope='invented-handoff',
            text='Approval owner remains unknown.' if missing else 'Reported timing conflict remains unresolved.',
            origin='source_reported' if missing else 'reported_conflict_unverified',
            evidence_refs=(evidence,),
        )
        raw = json.dumps({
            'schema_version': 1, 'source_id': str(ref.source_id), 'source_revision': 1,
            'complete': True, 'unresolved_items': [],
            'observations': [{'occurrence_key': 'literal-handoff', 'kind': 'handoff',
                              'scope': 'invented-handoff', 'value': text,
                              'evidence': [evidence.model_dump(mode='json')]}],
            'findings': [finding.model_dump(mode='json')],
        })
        kwargs['response_validator'](raw)
        return raw


def assemble_invented(payloads):
    """Only injected output, built from actually persisted source observations."""
    observations = [Observation.model_validate_json(json.dumps(p['observations'][0])) for p in payloads]
    a, b = observations
    refs = tuple(o.ref for o in observations)
    model = BusinessOperatingModel(
        model_id=uuid4(), version=1, workspace_id=a.ref.workspace_id, source_refs=refs,
        declared_population='Exactly two fresh invented originals',
        processes=tuple(ProcessRecord(
            process_id=pid, label=label, scope=o.scope, source_ids=(o.ref.source_id,),
            observation_ids=(o.observation_id,), completeness='partial',
        ) for pid, label, o in (('design', 'Design', a), ('supplier', 'Supplier', b))),
        objects=(BusinessRecord(object_id='art', kind='artifact', label='ART', scope=a.scope,
                                support=Support(observation_ids=(a.observation_id,))),
                 BusinessRecord(object_id='design-role', kind='role', label='Design', scope=a.scope,
                                support=Support(observation_ids=(a.observation_id,))),
                 BusinessRecord(object_id='supplier-role', kind='role', label='Supplier', scope=b.scope,
                                support=Support(observation_ids=(b.observation_id,)))),
        interfaces=(Interface(interface_id='design-to-supplier', from_process='design', to_process='supplier',
                              artifact_id='art', scope=a.scope,
                              support=Support(observation_ids=(a.observation_id,)), status='supported'),),
        assembly_decisions=(), workflows=(),
        finding_ids=tuple(f['finding_id'] for p in payloads for f in p['findings']),
        completeness='partial',
    )
    return model.model_dump_json()


@pytest.fixture
def journey_inputs(admin_url, tmp_path):
    with psycopg.connect(admin_url) as connection:
        connection.execute((Path(__file__).parents[1] / 'sql/004_workflow_integrity.sql').read_text())
    workspace, assembly, summary, actor = uuid4(), uuid4(), uuid4(), uuid4()
    texts = ('Design sends ART to Supplier. Approval owner is unknown.',
             'Supplier receives ART. Review timing conflicts with the older schedule.')
    receipts = []
    def forbidden(*_):
        raise AssertionError('plain text reading must not call a visual provider')
    for text in texts:
        data = text.encode()
        seal = hashlib.sha256(data).hexdigest()
        original = read_original(data=data, content_type='text/plain', expected_hash=seal,
                                 reader=forbidden, reviewer=forbidden, reader_request=None,
                                 reviewer_request=None, approvals=[])
        ref = SourceRef(workspace_id=workspace, source_id=uuid4(), revision=1,
                        original_sha256=seal, reading_sha256=hashlib.sha256(original.normalized_text.encode()).hexdigest(),
                        parser_id=original.parser_identity)
        receipts.append(SourceReceipt(ref=ref, reading=original.normalized_text, display_revision='r1'))
    current = {r.ref.source_id: r for r in receipts}
    permissions = {r.ref.source_id: True for r in receipts}
    blobs = FileBlobStore(tmp_path)
    def reopen():
        return Ledger(admin_url, blobs, principal=actor,
                      can_read=lambda _w, _p, sid: permissions.get(sid, False),
                      current_source=lambda _w, sid: current[sid])
    ledger = reopen()
    obligations = tuple(Obligation(
        obligation_id=f'source-{i}', priority='essential', expected='represented',
        evidence=EvidenceRef(ref=r.ref, start=0, end=len(r.reading), quote=r.reading),
        reason='independent invented source inventory',
    ) for i, r in enumerate(receipts))
    records = tuple(CoverageRecord(obligation_id=o.obligation_id, disposition='represented',
                                  object_ids=(pid,), reason='exact source process support')
                    for o, pid in zip(obligations, ('design', 'supplier')))
    graph_url = os.environ.get('ORACLE2_OPERATING_TEST_GRAPH_URL')
    if not graph_url:
        pytest.fail('owned isolated actual SDK graph required')
    from test_operating_model_sdk import make_projection
    projection = make_projection(graph_url, workspace, assembly, uuid4())
    provider = InventedProvider()
    params = dict(expected_source_refs=tuple(r.ref for r in receipts), assemble=assemble_invented,
                  assembly_id=assembly, summary_id=summary, projection=projection,
                  plan=QueryPlan(view='company_overview', process_ids=(), question='invented documentary overview',
                                 max_bytes=131072, page=0, page_size=25),
                  obligations=obligations, coverage_records=records,
                  permission_digest='a'*64, compiler_digest='b'*64)
    return ledger, provider, receipts, params, reopen, current, permissions


def run(journey_inputs, **updates):
    ledger, provider, receipts, params, *_ = journey_inputs
    async def execute():
        try:
            return await build_documentary_journey(ledger, provider, receipts, **(params | updates))
        finally:
            await params['projection'].close()
    return asyncio.run(execute())


def test_fresh_originals_generate_once_project_reload_and_answer(journey_inputs):
    ledger, provider, receipts, params, reopen, _, _ = journey_inputs
    result = run(journey_inputs)
    assert len(provider.calls) == 2 and {sid for sid, _ in provider.calls} == {r.ref.source_id for r in receipts}
    fresh = reopen()
    payload = fresh.read(receipts[0].ref.workspace_id, result.assembly_id, 1)
    assert len(payload['observations']) == 2
    assert {o['ref']['source_id'] for o in payload['observations']} == {str(r.ref.source_id) for r in receipts}
    assert payload['operating_models'][0]['interfaces'][0]['status'] == 'supported'
    assert {o['kind'] for o in payload['operating_models'][0]['objects']} == {'role', 'artifact'}
    assert {f['kind'] for f in payload['findings']} == {'missing_information', 'source_conflict'}
    assert payload['coverage']['essential_represented'] == 2
    restored = serve_summary(fresh, receipts[0].ref.workspace_id, result.summary_id, 1)
    answer = answer_from_summary(fresh, restored, intent='interfaces', process_id='design')
    assert answer.state == 'answered' and answer.records[0]['to_process'] == 'supplier'
    assert len(answer.findings) == 2 and len(answer.citations) == 2
    assert any('unknown' in c for c in answer.caveats)
    assert any('conflict' in c for c in answer.caveats)
    # No old claims, preconfirmed drafts or accepted policy seeded by the journey.
    with psycopg.connect(ledger.url) as connection:
        assert connection.execute('SELECT count(*) FROM oracle2.drafts WHERE workspace_id=%s',
                                  (receipts[0].ref.workspace_id,)).fetchone()[0] == 0


@pytest.mark.parametrize('failure', ('denied', 'withdrawn', 'stale', 'omitted'))
def test_whole_inventory_authorized_before_any_generation(journey_inputs, failure):
    ledger, provider, receipts, params, reopen, current, permissions = journey_inputs
    updates = {}
    if failure == 'denied':
        permissions[receipts[1].ref.source_id] = False
    elif failure == 'withdrawn':
        del current[receipts[1].ref.source_id]
    elif failure == 'stale':
        original = receipts[1]
        current[original.ref.source_id] = original.model_copy(update={
            'ref': original.ref.model_copy(update={'revision': 2}), 'display_revision': 'r2'})
    else:
        updates['expected_source_refs'] = params['expected_source_refs'][:1]
    with pytest.raises((PermissionError, ValueError, KeyError)):
        run(journey_inputs, **updates)
    assert provider.calls == []


def test_correction_or_access_change_invalidates_persisted_answer(journey_inputs):
    _, _, receipts, _, reopen, current, permissions = journey_inputs
    result = run(journey_inputs)
    workspace = receipts[0].ref.workspace_id
    original = current[receipts[0].ref.source_id]
    current[original.ref.source_id] = original.model_copy(update={
        'ref': original.ref.model_copy(update={'revision': 2,
                'reading_sha256': hashlib.sha256((original.reading + ' Corrected source.').encode()).hexdigest(),
                'original_sha256': hashlib.sha256((original.reading + ' Corrected source.').encode()).hexdigest()}),
        'reading': original.reading + ' Corrected source.', 'display_revision': 'r2'})
    with pytest.raises((PermissionError, ValueError)):
        serve_summary(reopen(), workspace, result.summary_id, 1)
    current[original.ref.source_id] = original
    permissions[receipts[1].ref.source_id] = False
    with pytest.raises(PermissionError):
        serve_summary(reopen(), workspace, result.summary_id, 1)


def test_assembly_cannot_omit_generated_source_or_hide_failed_response(journey_inputs):
    ledger, provider, receipts, params, *_ = journey_inputs
    def omitted(payloads):
        raw = json.loads(assemble_invented(payloads))
        raw['source_refs'] = raw['source_refs'][:1]
        return json.dumps(raw)
    with pytest.raises(ValueError, match='assembly rejected'):
        run(journey_inputs, assemble=omitted)
    assert len(provider.calls) == 2
    with psycopg.connect(ledger.url) as connection:
        row = connection.execute(
            'SELECT kind,state FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',
            (receipts[0].ref.workspace_id, params['assembly_id'])).fetchone()
        assert row == ('failed_assembly', 'failed')
        assert connection.execute(
            'SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',
            (receipts[0].ref.workspace_id, params['summary_id'])).fetchone()[0] == 0


def test_sdk_failure_never_falls_back_to_original_quotes(journey_inputs, monkeypatch):
    ledger, provider, receipts, params, *_ = journey_inputs
    async def unavailable(*_):
        raise RuntimeError('actual SDK unavailable')
    monkeypatch.setattr(params['projection'], 'build', unavailable)
    with pytest.raises(RuntimeError, match='actual SDK unavailable'):
        run(journey_inputs)
    assert len(provider.calls) == 2
    with psycopg.connect(ledger.url) as connection:
        assert connection.execute(
            'SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',
            (receipts[0].ref.workspace_id, params['summary_id'])).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# §9 named adversarial tests (plan_oracle_replacement_documentary_journey.md)
# Hostile input × required behavior. Pure validators run without stores;
# journey-integration cases use the existing journey_inputs fixture.
# ---------------------------------------------------------------------------


def test_replacement_refuses_changed_population(journey_inputs):
    """Duplicate/mixed-workspace or omitted original is refused before any dispatch."""
    ledger, provider, receipts, params, reopen, current, permissions = journey_inputs
    # Duplicate source id inside the receipt population.
    with pytest.raises(ValueError, match='exact distinct multi-original source population'):
        run(journey_inputs, expected_source_refs=params['expected_source_refs'] + (receipts[0].ref,))
    # Mixed workspace: second receipt forged into another workspace.
    foreign = receipts[1].model_copy(update={
        'ref': receipts[1].ref.model_copy(update={'workspace_id': uuid4()})})
    with pytest.raises(ValueError, match='exact distinct multi-original source population'):
        run(journey_inputs, expected_source_refs=(receipts[0].ref, foreign.ref))
    # Omitted original: expected refs shorter than receipts.
    with pytest.raises(ValueError, match='exact distinct multi-original source population'):
        run(journey_inputs, expected_source_refs=params['expected_source_refs'][:1])
    assert provider.calls == []


def test_replacement_rejects_forged_evidence():
    """Hash or exact-span mismatch is denied before the observation is created."""
    from oracle_brain.operating_model.source_receipts import SourceReceipt, SourceRef, EvidenceRef
    text = 'Design sends ART to Supplier.'
    ref = SourceRef(workspace_id=uuid4(), source_id=uuid4(), revision=1,
                    original_sha256='a' * 64,
                    reading_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    parser_id='p' * 64)
    receipt = SourceReceipt(ref=ref, reading=text, display_revision='r1')
    good = EvidenceRef(ref=ref, start=0, end=len(text), quote=text)
    assert validate_evidence(receipt, good) is good
    # Forged quote that does not match the reading span.
    forged = EvidenceRef(ref=ref, start=0, end=len(text), quote='INVENTED QUOTE')
    with pytest.raises(ValueError, match='evidence quote does not match'):
        validate_evidence(receipt, forged)
    # Span outside the reading.
    outside = EvidenceRef(ref=ref, start=0, end=len(text) + 10, quote=text + 'x' * 10)
    with pytest.raises(ValueError, match='outside the reading'):
        validate_evidence(receipt, outside)
    # Evidence bound to a different source revision.
    other = ref.model_copy(update={'revision': 2})
    wrong_revision = EvidenceRef(ref=other, start=0, end=len(text), quote=text)
    with pytest.raises(ValueError, match='different source revision'):
        validate_evidence(receipt, wrong_revision)


def test_replacement_preserves_failed_generation():
    """Invalid JSON / incomplete extraction is retained as a failed receipt, not dropped."""
    class StubLedger:
        reviewed_inventories = {}
        def __init__(self):
            self.persisted = []
        def persist(self, **kwargs):
            self.persisted.append(kwargs)
            return kwargs
    text = 'Invented source text for failed generation.'
    ref = SourceRef(workspace_id=uuid4(), source_id=uuid4(), revision=1,
                    original_sha256='b' * 64,
                    reading_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    parser_id='p' * 64)
    receipt = SourceReceipt(ref=ref, reading=text, display_revision='r1')
    ledger = StubLedger()
    # Invalid JSON body is preserved as failed_extraction.
    with pytest.raises(ValueError, match='invalid extraction preserved in failed receipt'):
        persist_response(ledger, receipt, '{not json', artifact_id=uuid4(), version=1,
                         permission_digest='a' * 64, compiler_digest='b' * 64)
    assert len(ledger.persisted) == 1 and ledger.persisted[0]['kind'] == 'failed_extraction'
    assert ledger.persisted[0]['failed'] is True
    # Structurally valid but incomplete extraction is also preserved as failed.
    incomplete = json.dumps({
        'schema_version': 1, 'source_id': str(ref.source_id), 'source_revision': 1,
        'complete': False, 'unresolved_items': ['still working'],
        'observations': [], 'findings': [],
    })
    with pytest.raises(ValueError, match='invalid extraction preserved in failed receipt'):
        persist_response(ledger, receipt, incomplete, artifact_id=uuid4(), version=1,
                         permission_digest='a' * 64, compiler_digest='b' * 64)
    assert len(ledger.persisted) == 2
    assert all(p['kind'] == 'failed_extraction' and p['failed'] for p in ledger.persisted)


def test_replacement_refuses_incomplete_assembly():
    """Omitted essential obligation / invented cross-document edge is rejected."""
    workspace = uuid4()
    text = 'Design sends ART to Supplier.'
    ref = SourceRef(workspace_id=workspace, source_id=uuid4(), revision=1,
                    original_sha256='c' * 64,
                    reading_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    parser_id='p' * 64)
    receipt = SourceReceipt(ref=ref, reading=text, display_revision='r1')
    evidence = EvidenceRef(ref=ref, start=0, end=len(text), quote=text)
    observation = Observation(
        observation_id='o1', ref=ref, occurrence_key='k1', kind='handoff',
        scope='invented', value=text, evidence=(evidence,))
    payloads = [{'source_refs': [ref.model_dump(mode='json')],
                 'observations': [observation.model_dump(mode='json')],
                 'findings': []}]
    refs, observations, findings = assembly_inputs(payloads)
    # Invented cross-document edge: process whose support observation is absent.
    raw = json.dumps({
        'model_id': str(uuid4()), 'version': 1, 'workspace_id': str(workspace),
        'source_refs': [ref.model_dump(mode='json')],
        'declared_population': 'invented',
        'processes': [{'process_id': 'p1', 'label': 'P1', 'scope': 'invented',
                       'source_ids': [str(ref.source_id)],
                       'observation_ids': ['absent-observation'],
                       'completeness': 'partial'}],
        'objects': [], 'interfaces': [],
        'assembly_decisions': [], 'workflows': [], 'finding_ids': [],
        'completeness': 'partial',
    })
    with pytest.raises(ValueError, match='unsupported or cross-scope assembly support|assembly must account'):
        assembly_candidate_payload(raw, workspace_id=workspace, refs=refs,
                                   observations=observations, findings=findings)


def test_replacement_stale_source_denied(journey_inputs):
    """A source revision changed after extraction invalidates the persisted answer."""
    _, _, receipts, _, reopen, current, permissions = journey_inputs
    result = run(journey_inputs)
    workspace = receipts[0].ref.workspace_id
    original = current[receipts[0].ref.source_id]
    # Stale revision: the receipt the journey used is no longer current.
    current[original.ref.source_id] = original.model_copy(update={
        'ref': original.ref.model_copy(update={'revision': 2}),
        'display_revision': 'r2'})
    with pytest.raises((PermissionError, ValueError)):
        serve_summary(reopen(), workspace, result.summary_id, 1)
    current[original.ref.source_id] = original


def test_replacement_revoked_access_denied(journey_inputs):
    """A revoked source read grant denies serving before any recompute."""
    _, _, receipts, _, reopen, current, permissions = journey_inputs
    result = run(journey_inputs)
    workspace = receipts[0].ref.workspace_id
    permissions[receipts[1].ref.source_id] = False
    with pytest.raises(PermissionError):
        serve_summary(reopen(), workspace, result.summary_id, 1)
    permissions[receipts[1].ref.source_id] = True


def test_replacement_review_scope_denied(journey_inputs):
    """A forged or out-of-scope review actor cannot authorize the population."""
    ledger, provider, receipts, params, reopen, current, permissions = journey_inputs
    # The journey principal is bound at Ledger construction; a foreign principal
    # that lacks can_read on the population is denied before any generation.
    foreign_ledger = Ledger(ledger.url, ledger.blobs, principal=uuid4(),
                            can_read=lambda *_: False,
                            current_source=lambda _w, sid: current[sid])
    with pytest.raises(PermissionError):
        foreign_ledger.authorize_refs(tuple(r.ref for r in receipts),
                                      receipts[0].ref.workspace_id)
    assert provider.calls == []


def test_replacement_unknowns_not_promoted(journey_inputs):
    """Conflicting timing / absent fact stay findings; they never become policy."""
    ledger, provider, receipts, params, *_ = journey_inputs
    result = run(journey_inputs)
    answer = result.answer
    # Unknown/conflict text is carried as caveats, not as established records.
    assert any('unknown' in c.lower() or 'conflict' in c.lower() for c in answer.caveats)
    # No accepted drafts / company policy may be seeded by the journey.
    with psycopg.connect(ledger.url) as connection:
        assert connection.execute(
            'SELECT count(*) FROM oracle2.drafts WHERE workspace_id=%s',
            (receipts[0].ref.workspace_id,)).fetchone()[0] == 0
    # Findings are reported, not resolved by model output.
    for finding in answer.findings:
        assert finding.get('status') != 'resolved_by_authorized_review'


def test_replacement_graph_reload_bound(journey_inputs, monkeypatch):
    """SDK snapshot must match the sealed assembly exactly on reload."""
    ledger, provider, receipts, params, *_ = journey_inputs

    async def drifted(ledger_, workspace, artifact_id, version):
        payload = await params['projection'].load(ledger_, workspace, artifact_id, version)
        return dict(payload, drifted=True)

    monkeypatch.setattr(params['projection'], 'load', drifted)
    with pytest.raises(ValueError, match='SDK projection does not match sealed assembly'):
        run(journey_inputs)


def test_replacement_partial_pack_caveated():
    """A partial/continuation pack is never presented as the whole population."""
    workspace = uuid4()
    text = 'Partial invented source.'
    ref = SourceRef(workspace_id=workspace, source_id=uuid4(), revision=1,
                    original_sha256='d' * 64,
                    reading_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    parser_id='p' * 64)
    evidence = {'ref': ref.model_dump(mode='json'), 'start': 0, 'end': len(text), 'quote': text}
    payload = {
        'source_refs': [ref.model_dump(mode='json')],
        'observations': [{'observation_id': 'o1', 'ref': ref.model_dump(mode='json'),
                          'occurrence_key': 'k', 'kind': 'step', 'scope': 's',
                          'value': text, 'evidence': [evidence]}],
        'findings': [],
        'operating_models': [{
            'model_id': str(uuid4()), 'version': 1, 'workspace_id': str(workspace),
            'source_refs': [ref.model_dump(mode='json')],
            'declared_population': 'exactly two invented originals',
            'processes': [
                {'process_id': 'p1', 'label': 'P1', 'scope': 's',
                 'source_ids': [str(ref.source_id)], 'observation_ids': ['o1'],
                 'completeness': 'partial'},
                {'process_id': 'p2', 'label': 'P2', 'scope': 's',
                 'source_ids': [str(ref.source_id)], 'observation_ids': ['o1'],
                 'completeness': 'partial'},
                {'process_id': 'p3', 'label': 'P3', 'scope': 's',
                 'source_ids': [str(ref.source_id)], 'observation_ids': ['o1'],
                 'completeness': 'partial'}],
            'objects': [], 'interfaces': [], 'assembly_decisions': [], 'workflows': [],
            'finding_ids': [], 'completeness': 'partial',
        }],
        'workflows': [],
    }
    plan = QueryPlan(view='company_overview', process_ids=(), question='invented overview',
                     max_bytes=131072, page=0, page_size=1)
    pack = build_pack(payload, plan)
    assert pack['continuation'] is not None
    assert pack['declared_population_fully_paged'] is False
    assert pack['coverage_state'] == 'partial'


def test_replacement_never_dispatches_external_provider(journey_inputs, monkeypatch):
    """Expired/unapproved exact provider scope never reaches an external endpoint."""
    import socket
    ledger, provider, receipts, params, *_ = journey_inputs
    # Block every outbound socket: the journey must complete on the injected provider alone.
    def blocked(*_args, **_kwargs):
        raise AssertionError('replacement journey must not open an external socket')
    monkeypatch.setattr(socket, 'socket', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    result = run(journey_inputs)
    assert result.assembly_id
    assert {sid for sid, _ in provider.calls} == {r.ref.source_id for r in receipts}
    # Unapproved exact provider scope is denied before any sender runs.
    request = ProcessingRequest(provider='external', account='prod', endpoint='https://real.example',
                                data_classes=frozenset({'company'}), purpose='replacement',
                                terms_hash='a' * 64)
    sent = []
    with pytest.raises(PermissionError):
        dispatch(request, [], lambda: sent.append(1))
    assert sent == []
    # Expired approval for an otherwise exact scope is likewise denied.
    approval = ProcessingApproval(**request.model_dump(), register_ref='test',
                                  expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(PermissionError):
        authorize(request, [approval])
