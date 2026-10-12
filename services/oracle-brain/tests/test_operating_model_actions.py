import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import psycopg
import pytest
from oracle_brain.operating_model.action_jobs import execute_event
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger

def install(admin_url):
    with psycopg.connect(admin_url, autocommit=True) as c: c.execute((Path(__file__).parents[1]/'sql/004_workflow_integrity.sql').read_text())

def insert_job(url, workspace, actor, payload=None, release_id=None, release_hash='a'*64):
    run=uuid4(); payload=payload or {}; release_id=release_id or uuid4()
    with psycopg.connect(url) as c: c.execute('INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(run,workspace,actor,'event_import',json.dumps(payload),release_id,release_hash,'pending',datetime.now(timezone.utc)+timedelta(minutes=5)))
    return run

def test_actor_mismatch_denied_before_write(admin_url, tmp_path):
    install(admin_url); workspace, actor, other=uuid4(),uuid4(),uuid4(); run=insert_job(admin_url,workspace,actor)
    ledger=Ledger(admin_url,FileBlobStore(tmp_path),principal=other,can_read=lambda *_:True,current_source=lambda *_:None)
    with pytest.raises(PermissionError,match='actor'): execute_event(admin_url,run,workspace,ledger,True)
    with psycopg.connect(admin_url) as c: assert c.execute('SELECT status FROM oracle2.operating_action_runs WHERE run_id=%s',(run,)).fetchone()[0]=='pending'

def test_expired_job_denied(admin_url, tmp_path):
    install(admin_url); workspace,actor=uuid4(),uuid4(); run=uuid4()
    with psycopg.connect(admin_url) as c: c.execute('INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(run,workspace,actor,'event_import','{}',uuid4(),'a'*64,'pending',datetime.now(timezone.utc)-timedelta(minutes=1)))
    ledger=Ledger(admin_url,FileBlobStore(tmp_path),principal=actor,can_read=lambda *_:True,current_source=lambda *_:None)
    with pytest.raises(PermissionError,match='unavailable'): execute_event(admin_url,run,workspace,ledger,True)

from hashlib import sha256
from psycopg.types.json import Jsonb
from test_operating_model_pipeline import inputs,call
from test_operating_model_cutover import manifest
from oracle_brain.operating_model.source_receipts import SourceRef,SourceReceipt
from oracle_brain.operating_model.contracts import digest

def prepared(admin_url,tmp_path):
    l,m,ex,ob,rec=inputs(admin_url,tmp_path);aid=uuid4();call(l,m,ex,ob,rec,aid)
    raw=('id,case,activity,time\nE'+uuid4().hex+',C,Review,2026-01-01T00:00:00Z\n').encode();seal=sha256(raw).hexdigest()
    receipt=SourceReceipt(ref=SourceRef(workspace_id=m.workspace_id,source_id=uuid4(),revision=1,original_sha256=seal,reading_sha256=seal,parser_id='synthetic-csv'),reading=raw.decode(),display_revision='r1')
    prior=l.current_source;l.current_source=lambda w,s:receipt if s==receipt.ref.source_id else prior(w,s)
    with psycopg.connect(admin_url) as c:
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES(%s,%s,%s,'root',%s)",(uuid4(),m.workspace_id,l.principal,uuid4()))
        mark=c.execute('SELECT COALESCE(max(sequence),0) FROM oracle2.operating_model_change_log WHERE workspace_id=%s',(m.workspace_id,)).fetchone()[0]
    refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in l.read(m.workspace_id,aid,1)['source_refs'])
    release=manifest(workspace_id=m.workspace_id,artifact_id=aid,artifact_content_hash=digest(l.read(m.workspace_id,aid,1)),source_refs=refs,ledger_watermark=mark)
    with psycopg.connect(admin_url) as c:
        c.execute('INSERT INTO oracle2.operating_release_manifests(workspace_id,release_id,content_hash,payload) VALUES(%s,%s,%s,%s)',(m.workspace_id,release.release_id,release.content_hash(),Jsonb(release.model_dump(mode='json'))))
        c.execute('INSERT INTO oracle2.operating_release_selectors(workspace_id,release_id,generation,watermark) VALUES(%s,%s,1,%s) ON CONFLICT(workspace_id) DO UPDATE SET release_id=EXCLUDED.release_id,watermark=EXCLUDED.watermark',(m.workspace_id,release.release_id,mark))
    import base64
    payload={'process_id':'p1','mapping':{'columns':{'event_id':'id','case_id':'case','activity_id':'activity','timestamp':'time'},'source_system':'invented','process_id':'p1','scope':'scope-a','activity_map':{'Review':'review-step'}},'raw_export_base64':base64.b64encode(raw).decode(),'format':'csv','window_start':'2026-01-01T00:00:00+00:00','window_end':'2026-01-02T00:00:00+00:00','source_refs':[receipt.ref.model_dump(mode='json')]}
    run=insert_job(admin_url,m.workspace_id,l.principal,payload,release.release_id,release.content_hash())
    return l,m,run,receipt

def test_event_job_real_import_exactly_once_and_cached_result_rechecks_source(admin_url,tmp_path):
    l,m,run,receipt=prepared(admin_url,tmp_path)
    result=execute_event(admin_url,run,m.workspace_id,l,True)
    assert result['accepted_count']==1 and result['actual_data_acceptance']=='unavailable'
    assert execute_event(admin_url,run,m.workspace_id,l,True)==result
    with psycopg.connect(admin_url) as c:assert c.execute('SELECT count(*) FROM oracle2.operational_imports WHERE workspace_id=%s AND import_id=%s',(m.workspace_id,result['import_id'])).fetchone()[0]==1
    l.can_read=lambda *_:False
    with pytest.raises((PermissionError,ValueError)):execute_event(admin_url,run,m.workspace_id,l,True)

def test_event_job_environment_denied_before_import(admin_url,tmp_path):
    l,m,run,r=prepared(admin_url,tmp_path)
    with pytest.raises(PermissionError,match='admission'):execute_event(admin_url,run,m.workspace_id,l,False)

def test_event_job_source_revision_changed_denied(admin_url,tmp_path):
    l,m,run,r=prepared(admin_url,tmp_path);prior=l.current_source
    l.current_source=lambda w,s:r.model_copy(update={'ref':r.ref.model_copy(update={'revision':2})}) if s==r.ref.source_id else prior(w,s)
    with pytest.raises((PermissionError,ValueError)):execute_event(admin_url,run,m.workspace_id,l,True)

def test_event_job_input_immutable_in_real_database(admin_url,tmp_path):
    l,m,run,r=prepared(admin_url,tmp_path)
    with pytest.raises(psycopg.errors.RaiseException):
        with psycopg.connect(admin_url) as c:c.execute("UPDATE oracle2.operating_action_runs SET payload='{}' WHERE run_id=%s",(run,))


def test_event_job_unknown_declared_process_denied(admin_url,tmp_path):
    l,m,run,r=prepared(admin_url,tmp_path)
    with psycopg.connect(admin_url) as c:
        actor,payload,release_id,release_hash=c.execute('SELECT actor_id,payload,release_id,release_hash FROM oracle2.operating_action_runs WHERE run_id=%s',(run,)).fetchone()
    payload['process_id']='unknown';payload['mapping']['process_id']='unknown'
    new=insert_job(admin_url,m.workspace_id,actor,payload,release_id,release_hash)
    with pytest.raises(PermissionError,match='declared'):execute_event(admin_url,new,m.workspace_id,l,True)

def test_event_job_wrong_release_denied_before_import(admin_url,tmp_path):
    l,m,run,r=prepared(admin_url,tmp_path)
    with psycopg.connect(admin_url) as c:actor,payload=c.execute('SELECT actor_id,payload FROM oracle2.operating_action_runs WHERE run_id=%s',(run,)).fetchone()
    new=insert_job(admin_url,m.workspace_id,actor,payload,uuid4(),'0'*64)
    with pytest.raises(PermissionError,match='release'):execute_event(admin_url,new,m.workspace_id,l,True)
