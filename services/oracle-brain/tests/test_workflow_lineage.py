from uuid import UUID,uuid4
from hashlib import sha256
import psycopg
import pytest
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.lineage import invalidate,appoint_steward,recompute_one
from oracle_brain.authz import appoint_owner,delegate
from oracle_brain.operating_model.source_receipts import SourceRef,SourceReceipt

W=UUID(int=10)
def test_revision_invalidates_findings_workflow_metrics_and_advice(admin_url,tmp_path):
 W=uuid4()
 with psycopg.connect(admin_url,autocommit=True) as c: c.execute((__import__('pathlib').Path(__file__).parents[1]/'sql/004_workflow_integrity.sql').read_text())
 text='lineage'; r=SourceReceipt(ref=SourceRef(workspace_id=W,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'),reading=text,display_revision='r1')
 db=Ledger(admin_url,FileBlobStore(tmp_path),principal=W,can_read=lambda *_:True,current_source=lambda *_:r); ids=[uuid4() for _ in range(4)]; payload={'source_refs':[r.ref.model_dump(mode='json')]}
 for i,aid in enumerate(ids): db.persist(workspace_id=W,artifact_id=aid,version=1,kind='workflow',payload=payload,refs=(r.ref,),permission_digest='b'*64,compiler_digest='c'*64,dependencies=() if i==0 else (('artifact',str(ids[i-1]),'1'),))
 assert invalidate(admin_url,workspace_id=W,upstream_kind='source',upstream_id=str(r.ref.source_id),reason='revoked')==4
 with psycopg.connect(admin_url) as c: assert c.execute('SELECT count(*) FROM oracle2.artifact_invalidations WHERE workspace_id=%s',(W,)).fetchone()[0]>=3
def test_source_revocation_denies_serving_before_recompute(admin_url,tmp_path):
 W=uuid4()
 text='drift'; ref=SourceRef(workspace_id=W,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'); first=SourceReceipt(ref=ref,reading=text,display_revision='r1'); current={'receipt':first}
 db=Ledger(admin_url,FileBlobStore(tmp_path),principal=W,can_read=lambda *_:True,current_source=lambda *_:current['receipt']); aid=uuid4(); payload={'source_refs':[ref.model_dump(mode='json')]}
 db.persist(workspace_id=W,artifact_id=aid,version=1,kind='workflow',payload=payload,refs=(ref,),permission_digest='b'*64,compiler_digest='c'*64)
 changed='drift changed'; current['receipt']=SourceReceipt(ref=ref.model_copy(update={'revision':2,'reading_sha256':sha256(changed.encode()).hexdigest()}),reading=changed,display_revision='r2')
 with pytest.raises((PermissionError,ValueError)): db.read(W,aid,1)
def test_summary_revocation_denies_serving(admin_url,tmp_path):
 W=uuid4()
 text='summary'; r=SourceReceipt(ref=SourceRef(workspace_id=W,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'),reading=text,display_revision='r1'); db=Ledger(admin_url,FileBlobStore(tmp_path),principal=W,can_read=lambda *_:True,current_source=lambda *_:r); aid=uuid4(); db.persist(workspace_id=W,artifact_id=aid,version=1,kind='summary',payload={'source_refs':[r.ref.model_dump(mode='json')]},refs=(r.ref,),permission_digest='b'*64,compiler_digest='c'*64)
 invalidate(admin_url,workspace_id=W,upstream_kind='source',upstream_id=str(r.ref.source_id),reason='summary revoked')
 with pytest.raises(PermissionError): db.read(W,aid,1)

def test_dependency_cycle_and_missing_upstream_rejected(admin_url,tmp_path):
 W=uuid4()
 text='cycle'; r=SourceReceipt(ref=SourceRef(workspace_id=W,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'),reading=text,display_revision='r1'); db=Ledger(admin_url,FileBlobStore(tmp_path),principal=W,can_read=lambda *_:True,current_source=lambda *_:r); payload={'source_refs':[r.ref.model_dump(mode='json')]}
 aid=uuid4()
 with pytest.raises(ValueError,match='upstream|cycle'):
  db.persist(workspace_id=W,artifact_id=aid,version=1,kind='workflow',payload=payload,refs=(r.ref,),permission_digest='b'*64,compiler_digest='c'*64,dependencies=(('artifact',str(uuid4()),'1'),))
 with pytest.raises(ValueError,match='cycle'):
  db.persist(workspace_id=W,artifact_id=aid,version=1,kind='workflow',payload=payload,refs=(r.ref,),permission_digest='b'*64,compiler_digest='c'*64,dependencies=(('artifact',str(aid),'1'),))

def test_current_rooted_steward_required(admin_url,tmp_path,monkeypatch):
 W=uuid4()
 text='steward'; sid=uuid4(); r=SourceReceipt(ref=SourceRef(workspace_id=W,source_id=sid,revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'),reading=text,display_revision='r1'); actor=uuid4(); db=Ledger(admin_url,FileBlobStore(tmp_path),principal=actor,can_read=lambda *_:True,current_source=lambda *_:r)
 with pytest.raises(PermissionError): appoint_steward(db,workspace_id=W,source_id=sid,steward_id=actor)
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
 from cryptography.hazmat.primitives import serialization
 owner=uuid4(); steward=uuid4(); appointment=uuid4(); key=Ed25519PrivateKey.generate(); monkeypatch.setenv('ORACLE2_OWNER_PUBLIC_KEY',key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex())
 signature=key.sign(f'oracle2-owner-appointment-v1:{W}:{owner}:{appointment}'.encode()).hex()
 appoint_owner(admin_url,workspace_id=W,owner_id=owner,appointed_by=uuid4(),appointment_id=appointment,owner_signature_hex=signature);delegate(admin_url,workspace_id=W,grantor_id=owner,actor_id=steward,scope='source-steward:'+str(sid));db.principal=owner
 assert appoint_steward(db,workspace_id=W,source_id=sid,steward_id=steward)
 with pytest.raises(PermissionError): appoint_steward(db,workspace_id=W,source_id=sid,steward_id=actor)

def test_invalidation_replay_and_blocked_recompute(admin_url,tmp_path):
 W=uuid4()
 text='recompute'; r=SourceReceipt(ref=SourceRef(workspace_id=W,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'),reading=text,display_revision='r1'); db=Ledger(admin_url,FileBlobStore(tmp_path),principal=W,can_read=lambda *_:True,current_source=lambda *_:r); aid=uuid4(); db.persist(workspace_id=W,artifact_id=aid,version=1,kind='workflow',payload={'source_refs':[r.ref.model_dump(mode='json')]},refs=(r.ref,),permission_digest='b'*64,compiler_digest='c'*64)
 event=uuid4(); invalidate(admin_url,workspace_id=W,upstream_kind='source',upstream_id=str(r.ref.source_id),reason='revoked',event_id=event); invalidate(admin_url,workspace_id=W,upstream_kind='source',upstream_id=str(r.ref.source_id),reason='revoked',event_id=event)
 with psycopg.connect(admin_url) as conn:assert conn.execute('SELECT count(*) FROM oracle2.operating_recompute_requests WHERE workspace_id=%s AND artifact_id=%s',(W,aid)).fetchone()[0]==1
 with pytest.raises(PermissionError): db.read(W,aid,1)
 result=recompute_one(db,workspace_id=W,rebuild=lambda *_: (_ for _ in ()).throw(PermissionError('denied')),verify_projection=lambda *_:None); assert result['state']=='blocked'

def test_successful_recompute_rebuilds_new_version_and_keeps_old_denied(admin_url,tmp_path):
 W=uuid4()
 text='recompute success'; r=SourceReceipt(ref=SourceRef(workspace_id=W,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256=sha256(text.encode()).hexdigest(),parser_id='p'),reading=text,display_revision='r1'); db=Ledger(admin_url,FileBlobStore(tmp_path),principal=W,can_read=lambda *_:True,current_source=lambda *_:r); old=uuid4(); payload={'source_refs':[r.ref.model_dump(mode='json')]}; db.persist(workspace_id=W,artifact_id=old,version=1,kind='workflow',payload=payload,refs=(r.ref,),permission_digest='b'*64,compiler_digest='c'*64)
 invalidate(admin_url,workspace_id=W,upstream_kind='source',upstream_id=str(r.ref.source_id),reason='replace',event_id=uuid4())
 new=uuid4(); seen={}
 def rebuild(*_):
  manifest=db.persist(workspace_id=W,artifact_id=new,version=1,kind='workflow',payload=payload,refs=(r.ref,),permission_digest='b'*64,compiler_digest='c'*64); return manifest
 def verify(manifest,current): seen['manifest']=manifest.content_hash; seen['payload']=current
 result=recompute_one(db,workspace_id=W,rebuild=rebuild,verify_projection=verify)
 assert result['artifact_id']==str(new)
 assert result['state']=='rebuilt' and result['content_hash']==seen['manifest'] and seen['payload']==payload
 with pytest.raises(PermissionError): db.read(W,old,1)
 assert recompute_one(db,workspace_id=W,rebuild=rebuild,verify_projection=verify) is None
