"""Synthetic native result custody, exact receipt bytes and actual TLS boundary."""
from contextlib import contextmanager
import hashlib,json,time,threading,ssl,urllib.request,urllib.error,hmac
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.hosting.gateway import OpaqueGateway,OpaqueJob,ResultLease,server_tls,signature_message
from oracle_brain.hosting.custody import FileCustody
from oracle_brain.hosting.job_authority import PostgresJobAuthority
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.source_receipts import SourceRef
from test_hosting_boundary import certificates,KEY,WORKER
from test_hosting_job_authority import gateway_database

@pytest.fixture
def result_job(admin_url,gateway_database,tmp_path):
    scripts=Path(__file__).resolve().parents[1]/'sql'
    workspace,source,artifact,actor,root_actor,run,release=(uuid4() for _ in range(7))
    root_appointment,appointment=uuid4(),uuid4();reading='invented native original';rh=hashlib.sha256(reading.encode()).hexdigest()
    ref=SourceRef(workspace_id=workspace,source_id=source,revision=1,original_sha256='b'*64,reading_sha256=rh,parser_id='a'*64)
    with psycopg.connect(admin_url) as c:
        for file in ('007_hosting_candidate_permissions.sql','008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql'):c.execute((scripts/file).read_text())
        c.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented','text/plain','draft')",(source,workspace,actor))
        c.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'invented','confirmed')",(uuid4(),source,workspace,actor))
        for kind,text in [('original',reading),('original-metadata',json.dumps({'original_hash':'b'*64,'content_hash':rh,'parser_identity':'a'*64,'content_type':'text/plain','evidence_kind':'native_text','page_count':1,'review_receipt':'4'*64}))]:
            c.execute('INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) VALUES(%s,%s,%s,0,%s,%s,0,1)',(uuid4(),source,workspace,kind,text))
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES(%s,%s,%s,'root',%s)",(root_appointment,workspace,root_actor,uuid4()))
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id) VALUES(%s,%s,%s,%s,%s,%s)',(appointment,workspace,actor,'source-read:'+str(source),root_actor,root_appointment))
        c.execute('INSERT INTO oracle2.operating_model_source_receipts VALUES(%s,%s,1,%s,%s,%s,%s)',(workspace,source,'b'*64,rh,'a'*64,Jsonb({'invented':True})))
        c.execute("INSERT INTO oracle2.artifact_manifests(workspace_id,artifact_id,version,kind,input_digest,source_digest,permission_digest,compiler_digest,dependency_digest,content_hash,private_object_key,state,manifest) VALUES(%s,%s,1,'documentary',%s,%s,%s,%s,%s,%s,'invented','ready','{}')",(workspace,artifact,digest({}),digest({'refs':[ref.model_dump(mode='json')]}),'e'*64,'a'*64,digest({}),'d'*64))
        c.execute("INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,1,'source',%s,'1')",(workspace,artifact,str(source)))
        watermark=c.execute('SELECT max(sequence) FROM oracle2.operating_model_change_log WHERE workspace_id=%s',(workspace,)).fetchone()[0]
        m=ReleaseManifest(release_id=release,workspace_id=workspace,artifact_id=artifact,artifact_version=1,artifact_content_hash='d'*64,runtime_digest='a'*64,permission_digest='e'*64,source_refs=(ref,),graph_generation=uuid4(),graph_name='oracle_operating_model_v1_invented',graph_record_digest='f'*64,acceptance_state='synthetic',independent_review_hash='1'*64,documentary_gate_hash='2'*64,source_inventory_hash='3'*64,ledger_watermark=watermark)
        c.execute('INSERT INTO oracle2.operating_release_manifests VALUES(%s,%s,%s,%s,now())',(workspace,release,m.content_hash(),Jsonb(m.model_dump(mode='json'))));c.execute('INSERT INTO oracle2.operating_release_selectors VALUES(%s,%s,1,%s)',(workspace,release,watermark))
        c.execute("INSERT INTO oracle2.operating_view_runs(run_id,workspace_id,actor_id,query_plan,release_id,release_hash,status,source_refs) VALUES(%s,%s,%s,%s,%s,%s,'pending',%s)",(run,workspace,actor,Jsonb({'max_bytes':1024}),release,m.content_hash(),Jsonb([ref.model_dump(mode='json')])))
    auth=PostgresJobAuthority(gateway_database,runtime_hash='a'*64,synthetic=True,allowed_release_hashes=frozenset({m.content_hash()}))
    record={'worker_uri':WORKER,'runtime_hash':'a'*64,'active':True,'expires_at':int(time.time())+300,'allowed_release_hashes':[m.content_hash()]};registry=tmp_path/'registry';registry.write_text(json.dumps(record));spool=tmp_path/'spool';spool.mkdir()
    custody=FileCustody(registry=registry,spool=spool,trusted_registry_hash=digest(record),runtime_hash='a'*64,worker_uri=WORKER,job_authority=auth)
    job=OpaqueJob(str(run),'a'*64,'2'*64,str(uuid4()),int(time.time())+60)
    return custody,job,workspace,source,artifact,actor,release,appointment,registry

def complete(admin_url,f, *, override=None):
    raw=b'{"artifact_hash":"'+b'd'*64+b'","value":1.2300,"unicode":"\xe2\x98\x83"}'
    override=override or {}
    with psycopg.connect(admin_url) as c:
        c.execute('INSERT INTO oracle2.operating_view_pack_receipts(run_id,workspace_id,actor_id,release_id,release_hash,runtime_hash,canonical_pack,pack_hash) SELECT run_id,workspace_id,actor_id,release_id,release_hash,%s,%s,%s FROM oracle2.operating_view_runs WHERE run_id=%s',(override.get('runtime','a'*64),override.get('bytes',raw),override.get('hash',hashlib.sha256(raw).hexdigest()),f[1].job_id))
        c.execute("UPDATE oracle2.operating_view_runs SET status='completed',pack=%s WHERE run_id=%s",(Jsonb(json.loads(raw)),f[1].job_id))
    return raw

def test_pending_and_replay(result_job):
    store,job=result_job[:2]
    with store.result(job,WORKER) as lease: assert lease.status==202 and lease.body==b'{"state":"pending"}';lease.before_write()
    with pytest.raises(FileExistsError):
        with store.result(job,WORKER):pass

def test_complete_byte_exact(admin_url,result_job):
    raw=complete(admin_url,result_job)
    with result_job[0].result(result_job[1],WORKER) as lease:assert lease.status==200 and lease.body==raw;lease.before_write()

@pytest.mark.parametrize('mutation',[
 "UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s",
 "UPDATE oracle2.sources SET status='error' WHERE source_id=%s",
 "UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s",
 "UPDATE oracle2.source_blocks SET text='changed' WHERE source_id=%s AND kind='original'",
 "UPDATE oracle2.operating_view_runs SET expires_at=now()-interval '1 second' WHERE run_id=%s",
])
def test_result_revocation(admin_url,result_job,mutation):
    complete(admin_url,result_job); value=result_job[7] if 'appointments' in mutation else result_job[1].job_id if 'view_runs' in mutation else result_job[3]
    with psycopg.connect(admin_url) as c:c.execute(mutation,(value,))
    with pytest.raises(Exception):
        with result_job[0].result(result_job[1],WORKER):pass

def test_policy_changed_before_first_byte(result_job):
    with result_job[0].result(result_job[1],WORKER) as lease:
        result_job[8].write_text('{}')
        with pytest.raises(PermissionError):lease.before_write()

def test_default_private_result_denied(result_job):
    result_job[0].job_authority.synthetic=False
    with pytest.raises(PermissionError):
        with result_job[0].result(result_job[1],WORKER):pass

def test_actual_tls_result_and_crosspurpose(admin_url,result_job,certificates):
    store,job=result_job[:2]
    tls=server_tls(certfile=str(certificates/'server.pem'),keyfile=str(certificates/'server.key'),cafile=str(certificates/'ca.pem'))
    server=OpaqueGateway(('127.0.0.1',0),tls=tls,worker_uri=WORKER,signing_key=KEY,admit=store.admit,result=store.result)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    ctx=ssl.create_default_context(cafile=str(certificates/'ca.pem'));ctx.verify_flags|=ssl.VERIFY_X509_STRICT;ctx.load_cert_chain(str(certificates/'worker.pem'),str(certificates/'worker.key'))
    def request(path,signedpath,nonce,override=None):
        body=json.dumps({**job.__dict__,'nonce':nonce,**(override or {})}).encode();sig=hmac.new(KEY,body if signedpath=='legacy' else signature_message('POST',signedpath,body),hashlib.sha256).hexdigest()
        req=urllib.request.Request(f'https://localhost:{server.server_port}'+path,data=body,headers={'Content-Type':'application/json','X-Oracle-Job-Signature':sig})
        try:
            with urllib.request.urlopen(req,context=ctx,timeout=6) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,b''
    try:
        assert request('/v1/jobs/result','/v1/jobs/result',str(uuid4()))==(202,b'{"state":"pending"}')
        raw=complete(admin_url,result_job)
        assert request('/v1/jobs/result','/v1/jobs/admit',str(uuid4()))[0]==403
        assert request('/v1/jobs/result','legacy',str(uuid4()))[0]==403
        for override in ({'job_id':str(uuid4())},{'source_id':str(uuid4())},{'runtime_hash':'0'*64},{'admission_hash':'0'*64},{'expires_at':0},{'padding':'x'*3000}):
            assert request('/v1/jobs/result','/v1/jobs/result',str(uuid4()),override)[0]==403
        nonce=str(uuid4());assert request('/v1/jobs/result','/v1/jobs/result',nonce)==(200,raw)
        assert request('/v1/jobs/admit','/v1/jobs/admit',nonce)[0]==403
    finally:server.shutdown();server.server_close();t.join()

@pytest.mark.parametrize('override',[{'runtime':'0'*64},{'hash':'0'*64},{'bytes':b'{}'},{'bytes':b'x'*263000}])
def test_pack_receipt_tampering_denied(admin_url,result_job,override):
    complete(admin_url,result_job,override=override)
    with pytest.raises(Exception):
        with result_job[0].result(result_job[1],WORKER):pass


def test_result_holds_permission_against_inflight_revocation(admin_url,result_job):
    complete(admin_url,result_job);blocked=[]
    def revoke():
        with psycopg.connect(admin_url) as c:
            c.execute("SET LOCAL lock_timeout='100ms'")
            try:c.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(result_job[7],))
            except psycopg.errors.LockNotAvailable:blocked.append(True)
    with result_job[0].result(result_job[1],WORKER) as lease:
        t=threading.Thread(target=revoke);t.start();t.join(2);assert not t.is_alive() and blocked==[True];lease.before_write()
    with psycopg.connect(admin_url) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(result_job[7],))
    next_job=OpaqueJob(**{**result_job[1].__dict__,'nonce':str(uuid4())})
    with pytest.raises(Exception):
        with result_job[0].result(next_job,WORKER):pass


def test_gateway_never_gets_broad_pack_or_original_grants(gateway_database,result_job):
    with psycopg.connect(gateway_database) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT canonical_pack FROM oracle2.operating_view_pack_receipts')
    with psycopg.connect(gateway_database) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT text FROM oracle2.source_blocks')


def test_result_rejects_plaintext_url(result_job):
    authority=result_job[0].job_authority
    authority.url=psycopg.conninfo.make_conninfo(authority.url,sslmode='disable')
    with pytest.raises(PermissionError):
        authority.resolve_result(result_job[1].job_id,'a'*64,'2'*64)


def test_actual_gateway_tls_scram_session(admin_url,gateway_database,result_job):
    with psycopg.connect(gateway_database) as c:
        assert c.pgconn.ssl_in_use is True
        login=c.execute('SELECT session_user').fetchone()[0]
    with psycopg.connect(admin_url) as c:
        assert c.execute("SELECT rolpassword LIKE 'SCRAM-SHA-256$%%' FROM pg_authid WHERE rolname=%s",(login,)).fetchone()==(True,)


@pytest.mark.parametrize('pack_size,accepted',[(1024,True),(1025,False)])
def test_sealed_query_byte_limit_exact_boundary(admin_url,result_job,pack_size,accepted):
    prefix=b'{"artifact_hash":"'+b'd'*64+b'","unicode":"\xe2\x98\x83","numeric":1.2300,"padding":"'
    raw=prefix+b'x'*(pack_size-len(prefix)-2)+b'"}'
    assert len(raw)==pack_size
    with psycopg.connect(admin_url) as c:
        c.execute('INSERT INTO oracle2.operating_view_pack_receipts(run_id,workspace_id,actor_id,release_id,release_hash,runtime_hash,canonical_pack,pack_hash) SELECT run_id,workspace_id,actor_id,release_id,release_hash,%s,%s,%s FROM oracle2.operating_view_runs WHERE run_id=%s',('a'*64,raw,hashlib.sha256(raw).hexdigest(),result_job[1].job_id))
        c.execute("UPDATE oracle2.operating_view_runs SET status='completed',pack=%s WHERE run_id=%s",(Jsonb(json.loads(raw)),result_job[1].job_id))
    if accepted:
        with result_job[0].result(result_job[1],WORKER) as lease:assert lease.body==raw;lease.before_write()
    else:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with result_job[0].result(result_job[1],WORKER):pass
