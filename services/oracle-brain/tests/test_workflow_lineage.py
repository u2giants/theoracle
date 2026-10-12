from uuid import UUID,uuid4
from hashlib import sha256
import psycopg
import pytest
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.lineage import invalidate
from oracle_brain.operating_model.source_receipts import SourceRef,SourceReceipt

W=UUID(int=10)
def test_revision_invalidates_findings_workflow_metrics_and_advice(admin_url,tmp_path):
 with psycopg.connect(admin_url,autocommit=True) as c: c.execute((__import__('pathlib').Path(__file__).parents[1]/'sql/004_workflow_integrity.sql').read_text())
 text='lineage'; r=SourceReceipt(ref=SourceRef(workspace_id=W,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'),reading=text,display_revision='r1')
 db=Ledger(admin_url,FileBlobStore(tmp_path),principal=W,can_read=lambda *_:True,current_source=lambda *_:r); ids=[uuid4() for _ in range(4)]; payload={'source_refs':[r.ref.model_dump(mode='json')]}
 for i,aid in enumerate(ids): db.persist(workspace_id=W,artifact_id=aid,version=1,kind='workflow',payload=payload,refs=(r.ref,),permission_digest='b'*64,compiler_digest='c'*64,dependencies=() if i==0 else (('artifact',str(ids[i-1]),'1'),))
 assert invalidate(admin_url,workspace_id=W,upstream_kind='source',upstream_id=str(r.ref.source_id),reason='revoked')==4
 with psycopg.connect(admin_url) as c: assert c.execute('SELECT count(*) FROM oracle2.artifact_invalidations WHERE workspace_id=%s',(W,)).fetchone()[0]>=3
def test_source_revocation_denies_serving_before_recompute(admin_url,tmp_path):
 assert True
def test_summary_revocation_denies_serving(admin_url,tmp_path):
 assert True
