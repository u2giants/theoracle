import json
from uuid import uuid4
from test_business_operating_model import observation,model
from oracle_brain.operating_model.pipeline import persist_assembly
from oracle_brain.operating_model.coverage import Obligation,CoverageRecord
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.source_receipts import SourceReceipt
from oracle_brain.operating_model.pipeline import dispatch_source
from hashlib import sha256
import pytest,psycopg
from pathlib import Path

def inputs(admin_url,tmp_path):
    with psycopg.connect(admin_url) as c:c.execute((Path(__file__).parents[1]/'sql/004_workflow_integrity.sql').read_text())
    a,b=observation(4,'Design sends ART'),observation(5,'Supplier receives packet')
    receipts={o.ref.source_id:SourceReceipt(ref=o.ref,reading=o.value,display_revision='r1') for o in (a,b)}
    ledger=Ledger(admin_url,FileBlobStore(tmp_path),principal=a.ref.workspace_id,can_read=lambda *_:True,current_source=lambda _,sid:receipts[sid])
    extractions=[]
    for o in (a,b):
        aid=uuid4();payload={'source_refs':[o.ref.model_dump(mode='json')],'observations':[o.model_dump(mode='json')],'findings':[]}
        ledger.persist(workspace_id=o.ref.workspace_id,artifact_id=aid,version=1,kind='extraction',payload=payload,refs=(o.ref,),permission_digest='a'*64,compiler_digest='b'*64)
        extractions.append((aid,1))
    obligations=tuple(Obligation(obligation_id='o'+str(i),priority='essential',expected='represented',evidence=o.evidence[0],reason='invented source process') for i,o in enumerate((a,b)))
    records=tuple(CoverageRecord(obligation_id=o.obligation_id,disposition='represented',object_ids=('p'+str(i+1),),reason='exact process support') for i,o in enumerate(obligations))
    return ledger,model((a,b)),extractions,obligations,records

def call(ledger,model,extractions,obligations,records,artifact):
    return persist_assembly(ledger,model.model_dump_json(),workspace_id=model.workspace_id,artifact_id=artifact,version=1,extractions=extractions,obligations=obligations,coverage_records=records,inventory_hash=digest({'obligations':[o.model_dump(mode='json') for o in obligations]}),permission_digest='a'*64,compiler_digest='b'*64)

def test_current_extractions_assemble_durably_with_lineage(admin_url,tmp_path):
    ledger,model,extractions,obligations,records=inputs(admin_url,tmp_path);artifact=uuid4()
    manifest=call(ledger,model,extractions,obligations,records,artifact)
    payload=ledger.read(model.workspace_id,artifact,1)
    assert manifest.kind=='operating_model' and payload['raw_response']==model.model_dump_json()
    assert payload['coverage']['essential_represented']==2 and payload['operating_models'][0]['processes'][0]['process_id']=='p1'
    with psycopg.connect(admin_url) as c:assert c.execute("SELECT count(*) FROM oracle2.artifact_dependencies WHERE workspace_id=%s AND artifact_id=%s AND upstream_kind='artifact'",(model.workspace_id,artifact)).fetchone()[0]==2

def test_assembly_omission_retains_failure_and_never_projects(admin_url,tmp_path):
    ledger,model,extractions,obligations,records=inputs(admin_url,tmp_path);artifact=uuid4()
    with pytest.raises(ValueError,match='retained'):call(ledger,model,extractions,obligations,records[:-1],artifact)
    with psycopg.connect(admin_url) as c:
        row=c.execute('SELECT state FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',(model.workspace_id,artifact)).fetchone()
        assert row[0]=='failed'
        assert c.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND assertion_id=%s',(model.workspace_id,artifact)).fetchone()[0]==0
    with pytest.raises(PermissionError):ledger.read(model.workspace_id,artifact,1)

class Provider:
    def __init__(self, raw): self.raw=raw; self.calls=0
    def extract(self, **kwargs): self.calls+=1; return self.raw

def source_ledger(admin_url,tmp_path):
    text='source text'; ref=next(iter(inputs(admin_url,tmp_path)[0].current_source.__closure__ or ()),None)
    # Use a real receipt and a ledger whose current-source callback returns it.
    from uuid import UUID
    from oracle_brain.operating_model.source_receipts import SourceRef
    r=SourceReceipt(ref=SourceRef(workspace_id=UUID(int=900),source_id=UUID(int=901),revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'),reading=text,display_revision='r1')
    return Ledger(admin_url,FileBlobStore(tmp_path),principal=r.ref.workspace_id,can_read=lambda *_:True,current_source=lambda *_:r),r

def test_revoked_current_source_prevents_provider_call(admin_url,tmp_path):
    ledger,r=source_ledger(admin_url,tmp_path); provider=Provider('{}'); ledger.current_source=lambda *_: r.model_copy(update={'ref':r.ref.model_copy(update={'revision':2})})
    with pytest.raises((PermissionError,ValueError)): dispatch_source(ledger,provider,r,artifact_id=uuid4(),version=1,batch_id=uuid4(),permission_digest='a'*64,compiler_digest='b'*64)
    assert provider.calls==0

def test_admitted_typed_response_persists_exact_raw_response(admin_url,tmp_path):
    ledger,r=source_ledger(admin_url,tmp_path); raw=json.dumps({'schema_version':1,'source_id':str(r.ref.source_id),'source_revision':1,'complete':True,'observations':[],'findings':[],'unresolved_items':[]}); provider=Provider(raw); artifact=uuid4(); manifest=dispatch_source(ledger,provider,r,artifact_id=artifact,version=1,batch_id=uuid4(),permission_digest='a'*64,compiler_digest='b'*64); assert manifest.kind=='extraction' and ledger.read(r.ref.workspace_id,artifact,1)['raw_response']==raw

def test_invalid_provider_response_is_failed_without_outbox(admin_url,tmp_path):
    ledger,r=source_ledger(admin_url,tmp_path); artifact=uuid4();
    with pytest.raises(ValueError): dispatch_source(ledger,Provider('{"complete":false}'),r,artifact_id=artifact,version=1,batch_id=uuid4(),permission_digest='a'*64,compiler_digest='b'*64)
    with psycopg.connect(admin_url) as c: assert c.execute('SELECT state FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',(r.ref.workspace_id,artifact)).fetchone()[0]=='failed' and c.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND assertion_id=%s',(r.ref.workspace_id,artifact)).fetchone()[0]==0
