import hashlib,json,os,subprocess
from uuid import uuid4
from pathlib import Path
import psycopg,pytest
from oracle_brain.operating_model.source_receipts import SourceRef,SourceReceipt,EvidenceRef
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.extraction import persist_response

@pytest.fixture
def ready(admin_url,tmp_path):
    with psycopg.connect(admin_url) as c: c.execute((Path(__file__).parents[1]/'sql/004_workflow_integrity.sql').read_text())
    w,s=uuid4(),uuid4(); text='The shipping owner is not specified.'
    r=SourceReceipt(ref=SourceRef(workspace_id=w,source_id=s,revision=1,original_sha256=hashlib.sha256(text.encode()).hexdigest(),reading_sha256=hashlib.sha256(text.encode()).hexdigest(),parser_id='test'),reading=text,display_revision='r1')
    l=Ledger(admin_url,FileBlobStore(tmp_path),principal=w,can_read=lambda *_:True,current_source=lambda *_:r)
    return l,r

def response(r):
    evidence=EvidenceRef(ref=r.ref,start=0,end=len(r.reading),quote=r.reading).model_dump(mode='json')
    return {'schema_version':1,'source_id':str(r.ref.source_id),'source_revision':1,'complete':True,'observations':[],
     'findings':[{'finding_id':'missing-owner','kind':'missing_information','workspace_id':str(r.ref.workspace_id),
     'source_refs':[r.ref.model_dump(mode='json')],'scope':'shipping','text':'Shipping owner not specified',
     'origin':'source_reported','evidence_refs':[evidence]}],'unresolved_items':[]}

def test_findings_survive_fresh_interpreter(ready,admin_url,tmp_path):
    l,r=ready; aid=uuid4()
    persist_response(l,r,json.dumps(response(r)),artifact_id=aid,version=1,permission_digest='b'*64,compiler_digest='c'*64)
    config=tmp_path/'reload.json'; config.write_text(json.dumps({'receipt':r.model_dump(mode='json'),'workspace':str(r.ref.workspace_id),'artifact':str(aid)}));config.chmod(0o600)
    script='''import os,json
from pathlib import Path
from uuid import UUID
from oracle_brain.operating_model.source_receipts import SourceReceipt
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
p=Path(os.environ['RELOAD_ROOT']); d=json.loads((p/'reload.json').read_text());r=SourceReceipt.model_validate_json(json.dumps(d['receipt']))
l=Ledger(os.environ['ORACLE2_TEST_ADMIN_URL'],FileBlobStore(p),principal=r.ref.workspace_id,can_read=lambda *_:True,current_source=lambda *_:r)
a=l.read(UUID(d['workspace']),UUID(d['artifact']),1)
assert a['findings'][0]['finding_id']=='missing-owner'
assert a['findings'][0]['evidence_refs'][0]['quote']==r.reading
print('fresh interpreter preserved exact finding')'''
    env=dict(os.environ,ORACLE2_TEST_ADMIN_URL=admin_url,RELOAD_ROOT=str(tmp_path))
    run=subprocess.run([os.sys.executable,'-c',script],env=env,capture_output=True,text=True)
    assert run.returncode==0, 'fresh-process ledger reload failed'
    assert 'preserved exact finding' in run.stdout

def test_malformed_nonempty_list_persists_failed_receipt(ready):
    l,r=ready;aid=uuid4();raw=response(r);raw['findings']=['Owner unknown']
    with pytest.raises(ValueError): persist_response(l,r,json.dumps(raw),artifact_id=aid,version=1,permission_digest='b'*64,compiler_digest='c'*64)
    with pytest.raises(PermissionError):l.read(r.ref.workspace_id,aid,1)
    assert json.loads(l.read(r.ref.workspace_id,aid,1,include_failed=True)['raw_response'])['findings']==['Owner unknown']
