"""Fixed public invented source fixture; no employee/company inputs or provider."""
import hashlib,json
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

def fixture(runtime_hash,review_hash):
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
