"""Fixed public invented source fixture; no employee/company inputs or provider."""
import hashlib,json,re
from uuid import UUID
from oracle_brain.operating_model.contracts import ArtifactManifest,canonical_bytes,digest
from oracle_brain.operating_model.source_receipts import SourceRef,SourceReceipt,EvidenceRef
from oracle_brain.operating_model.observations import create_observation
from oracle_brain.operating_model.sdk_projection import SDKProjection
from oracle_brain.operating_model.release_manifest import ReleaseManifest

WORKSPACE=UUID('11111111-1111-4111-8111-111111111111')
ACTOR=UUID('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
OWNER=UUID('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
ARTIFACT=UUID('44444444-4444-4444-8444-444444444444')
GENERATION=UUID('55555555-5555-4555-8555-555555555555')
RELEASE=UUID('66666666-6666-4666-8666-666666666666')
RUN=UUID('77777777-7777-4777-8777-777777777777')
PARSER=hashlib.sha256(b'oracle-public-invented-native-fixture/v1').hexdigest()
SOURCES=((UUID('22222222-2222-4222-8222-222222222222'),'Invented Harbor sends blue cards to Invented Meadow.'),
         (UUID('33333333-3333-4333-8333-333333333333'),'Invented Meadow counts the blue cards received from Invented Harbor.'))

from dataclasses import dataclass

LEGACY_SCENARIO='public-invented-v1'
FORWARD_SCENARIO='public-invented-forward-v2'
NATIVE_TRIGGER_SCENARIO='public-invented-trigger-v1'

@dataclass(frozen=True)
class FixedScenario:
    scenario_id: str
    workspace: UUID
    actor: UUID
    owner: UUID
    artifact: UUID
    generation: UUID
    release: UUID
    run: UUID
    parser: str
    sources: tuple
    root_appointment: UUID
    grantor: UUID
    draft_ids: tuple
    appointment_ids: tuple
    block_ids: tuple
    seed_marker: str
    worker_uri: str

    def seal(self):
        from dataclasses import asdict
        return digest(json.loads(json.dumps(asdict(self),default=str)))


def fixed_scenario(scenario_id=LEGACY_SCENARIO):
    if scenario_id==LEGACY_SCENARIO:
        # Keep dynamic legacy constants for existing isolated qualification.
        return FixedScenario(scenario_id,WORKSPACE,ACTOR,OWNER,ARTIFACT,GENERATION,RELEASE,RUN,PARSER,SOURCES,
            UUID('88888888-8888-4888-8888-888888888888'),UUID('99999999-9999-4999-8999-999999999999'),
            tuple(UUID(int=100+i) for i in range(2)),tuple(UUID(int=200+i) for i in range(2)),
            tuple(UUID(int=300+i) for i in range(4)),'public-invented-remote-v1','spiffe://oracle/synthetic-worker')
    if scenario_id==NATIVE_TRIGGER_SCENARIO:
        # Separately owner-authorized October 18 live test. No historical
        # scenario/job/source/root identifier or issuer CLI is changed.
        return FixedScenario(scenario_id,
            UUID('6426980e-6287-4f58-9e94-d1cb49b5cd5d'),UUID('ca80de21-6773-4975-87dd-2c2802114028'),
            UUID('c4892a10-e3b7-46b6-b772-22a6157ff849'),UUID('992fa7e3-138e-443a-99fd-a466205b2fde'),
            UUID('b30a0da3-5a5b-4a97-9c51-733e383aa21e'),UUID('0b7f159f-3953-44bb-9a24-2b641d99cebc'),
            UUID('9c9c7424-8e16-4f71-be10-c935160e16c7'),
            hashlib.sha256(b'oracle-public-invented-trigger-fixture/v1').hexdigest(),
            ((UUID('274d32b6-f440-4a48-88d7-ea44dde3f830'),'Invented Alder sends violet envelopes to Invented Maple.'),
             (UUID('6a359163-cbb5-4678-b336-7402c5e85e5d'),'Invented Maple counts the violet envelopes received from Invented Alder.')),
            UUID('62b4902e-9865-4fb3-8d30-872c76cf06c4'),UUID('08561c51-7a66-4996-9bcb-0acd3674d8ec'),
            tuple(UUID(int=2000100+i) for i in range(2)),tuple(UUID(int=2000200+i) for i in range(2)),
            tuple(UUID(int=2000300+i) for i in range(4)),'public-invented-trigger-v1','spiffe://oracle/synthetic-trigger-worker-v1')
    if scenario_id!=FORWARD_SCENARIO:raise PermissionError('fixed public invented scenario required')
    return FixedScenario(scenario_id,
        UUID('21111111-1111-4111-8111-111111111111'),UUID('2aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
        UUID('2bbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),UUID('24444444-4444-4444-8444-444444444444'),
        UUID('25555555-5555-4555-8555-555555555555'),UUID('26666666-6666-4666-8666-666666666666'),
        UUID('27777777-7777-4777-8777-777777777777'),
        hashlib.sha256(b'oracle-public-invented-native-forward-fixture/v2').hexdigest(),
        ((UUID('22222222-2222-4222-8222-222222222223'),'Invented Birch records amber parcels sent to Invented Cedar.'),
         (UUID('23333333-3333-4333-8333-333333333333'),'Invented Cedar checks the amber parcels received from Invented Birch.')),
        UUID('28888888-8888-4888-8888-888888888888'),UUID('29999999-9999-4999-8999-999999999999'),
        tuple(UUID(int=1000100+i) for i in range(2)),tuple(UUID(int=1000200+i) for i in range(2)),
        tuple(UUID(int=1000300+i) for i in range(4)),'public-invented-remote-forward-v2','spiffe://oracle/synthetic-forward-worker-v2')

def graph_acl_users(graph,executor_password,projector_password):
    """Seal projector writes and executor reads to the exact data and ontology pair."""
    from importlib.metadata import version
    from graphrag_sdk.storage.ontology_store import OntologyStore
    if version('graphrag-sdk')!='1.4.0' or OntologyStore.ONTOLOGY_GRAPH_SUFFIX!='__ontology':
        raise PermissionError('native ontology namespace requires requalification')
    if not re.fullmatch(r'oracle_operating_model_v1_[0-9a-f]{32}_[0-9a-f]{32}_1_[0-9a-f]{32}',graph):
        raise PermissionError('exact fixed artifact graph required')
    if any(not re.fullmatch('[0-9a-f]{64}',value) for value in (executor_password,projector_password)):
        raise PermissionError('fixed strong synthetic graph credentials required')
    return ('user default off\n'
        f'user oracle_executor on >{executor_password} ~{graph} ~{graph}__ontology +graph.ro_query +ping +hello +info|server\n'
        f'user oracle_projector on >{projector_password} ~{graph} ~{graph}__ontology +graph.query +graph.ro_query +ping +hello +info|server\n')

def fixture(runtime_hash,review_hash,scenario_id=LEGACY_SCENARIO):
    scenario=fixed_scenario(scenario_id)
    WORKSPACE,ACTOR,ARTIFACT,GENERATION,RELEASE,PARSER,SOURCES=(scenario.workspace,scenario.actor,scenario.artifact,scenario.generation,scenario.release,scenario.parser,scenario.sources)
    receipts=[];observations=[];metadata=[]
    for index,(source,text) in enumerate(SOURCES):
        seal=hashlib.sha256(text.encode()).hexdigest()
        ref=SourceRef(workspace_id=WORKSPACE,source_id=source,revision=1,original_sha256=seal,reading_sha256=seal,parser_id=PARSER)
        receipt=SourceReceipt(ref=ref,reading=text,display_revision='r1')
        evidence=EvidenceRef(ref=ref,start=0,end=len(text),quote=text)
        observation=create_observation(receipt,f'invented-{index}','assertion','public-invented-boundary',text,[evidence])
        receipts.append(receipt);observations.append(observation.model_dump(mode='json'))
        metadata.append({'original_hash':seal,'content_hash':seal,'parser_identity':PARSER,'content_type':'text/plain','evidence_kind':'native_text','page_count':1,'review_receipt':PARSER})
    refs=[r.ref.model_dump(mode='json') for r in receipts]
    payload={'source_refs':refs,'observations':observations,'findings':[],'workflows':[],'operating_models':[]}
    content=digest(payload);source_digest=digest({'refs':refs})
    manifest=ArtifactManifest(workspace_id=WORKSPACE,artifact_id=ARTIFACT,version=1,kind='extraction',input_digest=source_digest,source_digest=source_digest,
        permission_digest=PARSER,compiler_digest=runtime_hash,dependency_digest=digest({'dependencies':[]}),content_hash=content,
        private_object_key=f'operating-model/{WORKSPACE}/{content}.json',state='ready')
    # The fixed sources/drafts/appointments create 11 change-log entries. The
    # bootstrap asserts this exact watermark before admitting the fixture job.
    release=ReleaseManifest(release_id=RELEASE,workspace_id=WORKSPACE,artifact_id=ARTIFACT,artifact_version=1,artifact_content_hash=content,
        runtime_digest=runtime_hash,permission_digest=PARSER,source_refs=tuple(r.ref for r in receipts),graph_generation=GENERATION,
        graph_name=f'oracle_operating_model_v1_{WORKSPACE.hex}_{ARTIFACT.hex}_1_{GENERATION.hex}',graph_record_digest=digest({'records':SDKProjection.records(payload)}),
        acceptance_state='synthetic',independent_review_hash=review_hash,documentary_gate_hash=PARSER,source_inventory_hash=digest({'invented_sources':refs}),ledger_watermark=11)
    return receipts,metadata,payload,manifest,release
