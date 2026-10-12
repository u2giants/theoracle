import hashlib
import json
import os
import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import psycopg
from graphrag_sdk.core.providers import Embedder, LLMInterface

from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.findings import Finding, import_legacy
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.observations import create_observation
from oracle_brain.operating_model.sdk_projection import SDKProjection
from oracle_brain.operating_model.source_receipts import EvidenceRef, SourceReceipt, SourceRef
from oracle_brain.operating_model.workflows.process_model import WorkflowModel,Step,Support,Transition,Gateway
from oracle_brain.operating_model.process_analysis.compiler import compile_contract
from oracle_brain.operating_model.model import BusinessOperatingModel,ProcessRecord
from oracle_brain.operating_model.process_analysis.compiler import compile_contract
from oracle_brain.operating_model.model import BusinessOperatingModel,ProcessRecord
from oracle_brain.operating_model.workflows.process_model import WorkflowModel, Step, Gateway, Transition, Support


class NoCallLLM(LLMInterface):
    def __init__(self):
        super().__init__('synthetic-no-call', max_concurrency=1)
    def invoke(self, prompt: str, **kwargs):
        raise AssertionError('SDK projection attempted a second extraction')


class FixedEmbedder(Embedder):
    model_name = 'synthetic-fixed-8'
    def embed_query(self, text: str, **kwargs):
        return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


@pytest.fixture
def projection_inputs(tmp_path):
    graph_url = os.environ.get('ORACLE2_OPERATING_TEST_GRAPH_URL')
    postgres_url = os.environ.get('ORACLE2_TEST_ADMIN_URL')
    if not graph_url or not postgres_url:
        pytest.fail('operating-model SDK integration URLs are required; missing proof is not a pass')
    with psycopg.connect(postgres_url) as conn:
        for migration in ('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql'):
            conn.execute((Path(__file__).parents[1]/'sql'/migration).read_text())
    workspace, artifact, source = uuid4(), uuid4(), uuid4()
    text = 'Intake Lead sends the packet. The approval owner is missing.'
    ref = SourceRef(workspace_id=workspace, source_id=source, revision=1,
                    original_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    reading_sha256=hashlib.sha256(text.encode()).hexdigest(), parser_id='synthetic-parser')
    receipt = SourceReceipt(ref=ref, reading=text, display_revision='r1')
    e1 = EvidenceRef(ref=ref, start=0, end=28, quote=text[:28])
    e2 = EvidenceRef(ref=ref, start=39, end=len(text), quote=text[39:])
    obs1 = create_observation(receipt, 'first-occurrence', 'process', 'workflow', 'Intake Lead sends the packet', (e1,))
    obs2 = create_observation(receipt, 'second-occurrence', 'process', 'workflow', 'Intake Lead sends the packet', (e1,))
    missing = Finding(finding_id='reported-missing-owner', kind='missing_information', workspace_id=workspace,
                      source_refs=(ref,), scope='workflow', text='approval owner is missing', origin='source_reported', evidence_refs=(e2,))
    legacy = import_legacy(workspace_id=workspace, refs=(ref,), scope='workflow', texts=['legacy gap'])[0]
    payload = {'source_refs': [ref.model_dump(mode='json')], 'observations': [obs1.model_dump(mode='json'), obs2.model_dump(mode='json')],
               'findings': [missing.model_dump(mode='json'), legacy.model_dump(mode='json')]}
    support=Support(observation_ids=(obs1.observation_id,))
    workflow=WorkflowModel(workflow_id='synthetic-occurrences',version=1,workspace_id=workspace,process_id='intake',scope='workflow',source_refs=(ref,),completeness='partial',coverage_digest='c'*64,steps=(Step(step_id='first',label='Reviewer',kind='start',support=support),Step(step_id='second',label='Reviewer',kind='end',support=support)),transitions=(Transition(transition_id='explicit-handoff',from_id='first',to_id='second',support=support),))
    payload['workflows']=[workflow.model_dump(mode='json')]
    model=BusinessOperatingModel(model_id=uuid4(),version=1,workspace_id=workspace,source_refs=(ref,),declared_population='Invented Intake only',processes=(ProcessRecord(process_id='intake',label='Intake',scope='workflow',source_ids=(source,),observation_ids=(obs1.observation_id,obs2.observation_id),completeness='partial'),),objects=(),interfaces=(),assembly_decisions=(),workflows=(workflow,),finding_ids=(missing.finding_id,legacy.finding_id),completeness='partial')
    payload['operating_models']=[model.model_dump(mode='json')]
    ledger = Ledger(postgres_url, FileBlobStore(tmp_path), principal=workspace,
                    can_read=lambda *_: True, current_source=lambda *_: receipt)
    ledger.persist(workspace_id=workspace, artifact_id=artifact, version=1, kind='extraction', payload=payload,
                   refs=(ref,), permission_digest='a'*64, compiler_digest='b'*64)
    return graph_url, ledger, workspace, artifact, payload


def make_projection(graph_url, workspace, artifact, generation):
    return SDKProjection(graph_url, workspace_id=workspace, artifact_id=artifact, artifact_version=1,
                          generation=generation, llm=NoCallLLM(), embedder=FixedEmbedder(), dimensions=8)


def test_new_projection_survives_real_sdk_finalize_reload(projection_inputs):
    async def run():
        graph, ledger, workspace, artifact, payload = projection_inputs
        generation = uuid4(); first = make_projection(graph, workspace, artifact, generation)
        built = await first.build(ledger, workspace, artifact, 1); await first.close()
        second = make_projection(graph, workspace, artifact, generation)
        loaded = await second.load(ledger, workspace, artifact, 1); await second.close()
        assert built['graph_name'] == second.graph_name and loaded == payload
    asyncio.run(run())


def test_graph_loss_cannot_pass_via_original_text_fallback(projection_inputs):
    async def run():
        graph, ledger, workspace, artifact, _ = projection_inputs
        generation = uuid4(); projection = make_projection(graph, workspace, artifact, generation)
        await projection.build(ledger, workspace, artifact, 1)
        await projection.connection.query("MATCH (n:OperatingModelRecord {id:'reported-missing-owner'}) DETACH DELETE n")
        with pytest.raises(ValueError, match='projection lost'):
            await projection.load(ledger, workspace, artifact, 1)
        await projection.close()
    asyncio.run(run())


def test_sdk_rebuild_from_ledger(projection_inputs):
    async def run():
        graph, ledger, workspace, artifact, payload = projection_inputs
        first = make_projection(graph, workspace, artifact, uuid4()); await first.build(ledger, workspace, artifact, 1); await first.close()
        rebuilt = make_projection(graph, workspace, artifact, uuid4())
        assert await rebuilt.build(ledger, workspace, artifact, 1) and payload == await rebuilt.load(ledger, workspace, artifact, 1)
        await rebuilt.close()
    asyncio.run(run())

def compiler_model(**changes):
    ref=SourceRef(workspace_id=UUID(int=9),source_id=UUID(int=10),revision=1,original_sha256='a'*64,reading_sha256='b'*64,parser_id='p')
    s=Support(observation_ids=('o',)); base=dict(workflow_id='w',version=1,workspace_id=UUID(int=9),process_id='p',scope='s',source_refs=(ref,),completeness='complete',coverage_digest='c'*64,steps=(Step(step_id='start',label='A',kind='start',support=s),Step(step_id='end',label='A',kind='end',support=s)),transitions=(Transition(transition_id='t',from_id='start',to_id='end',support=s),))
    base.update(changes); return WorkflowModel(**base)

def test_petri_compiler_linear_and_rework_identity():
    result=compile_contract(compiler_model()); assert result['state']=='compiled' and result['step_map']['start']=='step:start'
    rework=compile_contract(compiler_model(transitions=(Transition(transition_id='t',from_id='start',to_id='end',support=Support(observation_ids=('o',)),rework=True),)))
    assert rework['transition_map']['t']=='edge:t'

def test_petri_compiler_explicit_and_xor_preserves_partial_map():
    s=Support(observation_ids=('o',)); split=Gateway(gateway_id='g',kind='parallel_split',support=s); join=Gateway(gateway_id='j',kind='parallel_join',support=s)
    m=compiler_model(steps=(Step(step_id='start',label='A',kind='start',support=s),Step(step_id='x',label='X',kind='activity',support=s),Step(step_id='y',label='Y',kind='activity',support=s),Step(step_id='end',label='Z',kind='end',support=s)),gateways=(split,join),transitions=(Transition(transition_id='a',from_id='start',to_id='g',support=s),Transition(transition_id='b',from_id='g',to_id='x',support=s),Transition(transition_id='c',from_id='g',to_id='y',support=s),Transition(transition_id='d',from_id='x',to_id='j',support=s),Transition(transition_id='e',from_id='y',to_id='j',support=s),Transition(transition_id='f',from_id='j',to_id='end',support=s)))
    assert compile_contract(m)['state']=='compiled'
    assert compile_contract(compiler_model(gateways=(Gateway(gateway_id='u',kind='unsupported',support=s),)))['state']=='not_analyzable'


def test_graph_lineage_loss_denies_serving(projection_inputs):
    async def run():
        graph,ledger,workspace,artifact,payload=projection_inputs
        projection=make_projection(graph,workspace,artifact,uuid4())
        await projection.build(ledger,workspace,artifact,1)
        await projection.connection.query('MATCH ()-[r:SUPPORTED_BY]->() DELETE r')
        with pytest.raises(ValueError,match='finding lineage'):await projection.load(ledger,workspace,artifact,1)
        await projection.close()
    asyncio.run(run())

def test_operating_outbox_signed_projection_replay_and_stale_denial(projection_inputs):
    from oracle_brain.outbox import lease_next
    from oracle_brain.operating_model.projection_delivery import project_event,mark_delivered
    async def run():
        graph,ledger,workspace,artifact,payload=projection_inputs
        event=lease_next(ledger.url,allowed_workspaces=frozenset({str(workspace)}),namespace='oracle_operating_model_v1')
        assert event and event.assertion_id==artifact
        projection=make_projection(graph,workspace,artifact,uuid4());secret=b'invented-synthetic-signing-key-32bytes'
        first=await project_event(ledger,event,projection,secret=secret,projector_id='invented-worker')
        assert await project_event(ledger,event,projection,secret=secret,projector_id='invented-worker')==first
        with psycopg.connect(ledger.url) as conn:
            assert conn.execute('SELECT count(*) FROM oracle2.operating_projection_receipts WHERE event_id=%s',(event.event_id,)).fetchone()[0]==1
            assert conn.execute('SELECT delivered_at IS NOT NULL FROM oracle2.outbox WHERE event_id=%s',(event.event_id,)).fetchone()[0]
        unsigned={k:v for k,v in first.items() if k!='signature'}
        with pytest.raises(PermissionError,match='forged'):mark_delivered(ledger,event,unsigned,'0'*64,secret=secret)
        with pytest.raises(psycopg.errors.RaiseException,match='immutable'):
            with psycopg.connect(ledger.url) as conn:conn.execute("UPDATE oracle2.outbox SET payload=jsonb_set(payload,'{namespace}','\"tampered\"') WHERE event_id=%s",(event.event_id,))
        refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in payload['source_refs'])
        ledger.persist(workspace_id=workspace,artifact_id=artifact,version=2,kind='operating_model',payload=payload,refs=refs,permission_digest='d'*64,compiler_digest='e'*64)
        with pytest.raises(PermissionError,match='stale'):await project_event(ledger,event,projection,secret=secret,projector_id='invented-worker')
        await projection.close()
    asyncio.run(run())
