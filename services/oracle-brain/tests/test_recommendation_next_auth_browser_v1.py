"""Actual Next/Auth HTTP/employee SQL → fixed mTLS → canonical advice SQL.

Requires the complete current canonical inventory including025. The canonical
owner installs it ONCE in this case's fresh UUID database BEFORE qualification.
Host-prepared qualification is not native/company proof. This source preparation
may not run from an unmerged deployment task.
"""
from dataclasses import asdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
import hashlib,json,os,signal,subprocess,threading,time
import psycopg
from psycopg import sql
import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.consultant.recommendation_authority_v1 import FUNCTIONS
from oracle_brain.hosting.recommendation_actions_settings_v1 import RecommendationConfigV1,RecommendationPeerV1,RecommendationSettingsV1
from oracle_brain.hosting.recommendation_actions_service_v1 import protected_recommendation_web_server_v1
from oracle_brain.hosting.recommendation_actions_v1 import RecommendationFactoryV1
from test_recommendation_actions_sql import _assert_recommendation_schema_v1,_measurement_advice_v1,sql_qualified_serving_v3,RUNTIME
from test_hosting_boundary import certificates,WORKER
from invented_next_employee_fixture_v1 import invented_next_employee_fixture_v1
from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
from dev.oracle2.test_canonical_schema import owned_phase_database


def _parent_next_identity_state_v1(url):
    """Invented parent objects/rows must survive this child's isolated proof."""
    name=psycopg.conninfo.conninfo_to_dict(url)['dbname']
    with psycopg.connect(url) as connection:
        assert connection.pgconn.ssl_in_use
        assert connection.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',name)
        objects=connection.execute("""SELECT n.nspname,c.relname,c.oid,c.relowner,c.relrowsecurity,c.relforcerowsecurity
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname IN('employees','employee_identities') ORDER BY c.relname""").fetchall()
        rows=[]
        for table in ('employees','employee_identities'):
            if any(row[1]==table for row in objects):
                result=connection.execute(sql.SQL('SELECT to_jsonb(t) FROM public.{} t ORDER BY id').format(sql.Identifier(table))).fetchall()
                rows.append((table,hashlib.sha256(canonical_bytes([row[0] for row in result])).hexdigest()))
        return name,objects,rows


@pytest.fixture
def recommendation_next_database_v1(admin_url,tmp_path,monkeypatch):
    container=os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER']
    owned_worker_database(container,admin_url)
    parent_state=_parent_next_identity_state_v1(admin_url)
    keys=('ORACLE2_TEST_ADMIN_URL','ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT','ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256')
    saved=tuple((key,os.environ.get(key)) for key in keys)
    receipt_path=os.environ.get('ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT')
    parent_receipt=hashlib.sha256(Path(receipt_path).read_bytes()).hexdigest() if receipt_path else None
    child_name=None
    directory=tmp_path/'phase';directory.mkdir()
    try:
        with owned_phase_database(admin_url,container,directory) as env:
            target=env['ORACLE2_TEST_ADMIN_URL']
            child_name=psycopg.conninfo.conninfo_to_dict(target)['dbname']
            assert child_name!=parent_state[0]
            with monkeypatch.context() as phase:
                for key in keys:phase.setenv(key,env[key])
                _assert_recommendation_schema_v1(target)
                yield target
    finally:
        # Dependent source fixtures and the test's browser/server finally blocks
        # unwind first; the canonical context then drops ONLY its own UUID DB.
        assert tuple((key,os.environ.get(key)) for key in keys)==saved
        assert (hashlib.sha256(Path(receipt_path).read_bytes()).hexdigest() if receipt_path else None)==parent_receipt
        owned_worker_database(container,admin_url)
        assert _parent_next_identity_state_v1(admin_url)==parent_state
        if child_name is not None:
            with psycopg.connect(admin_url) as connection:
                assert connection.pgconn.ssl_in_use
                assert connection.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',parent_state[0])
                assert connection.execute('SELECT count(*) FROM pg_database WHERE datname=%s',(child_name,)).fetchone()==(0,)
            (tmp_path/'actual-next-database-cleanup.json').write_text(json.dumps(dict(parent_database=parent_state[0],child_database=child_name,child_absent=True,parent_identity_unchanged=True,parent_receipt_unchanged=True,environment_restored=True)))


@pytest.fixture
def recommendation_next_serving_advice_v1(recommendation_next_database_v1,sql_qualified_serving_v3,tmp_path,monkeypatch):
    # Actual target/receipt binding precedes this NEW120/115 source preparation.
    return _measurement_advice_v1(recommendation_next_database_v1,tmp_path,monkeypatch,serving=True)


def test_actual_next_auth_employee_sql_recommendation_actions(recommendation_next_database_v1,recommendation_next_serving_advice_v1,tmp_path,certificates,monkeypatch):
    admin_url=recommendation_next_database_v1
    f=recommendation_next_serving_advice_v1;stage=f['stage'];container=os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER']
    owned_worker_database(container,admin_url)
    identity=invented_next_employee_fixture_v1(admin_url,container=container)
    def protected(name,data):
        path=tmp_path/name;path.write_bytes(data);path.chmod(0o600)
        return dict(schema_version=1,path=str(path),sha256=hashlib.sha256(data).hexdigest())
    # Exact owned leaf covers both actual selected loopback DNS names. This is
    # installation fixture material, not TLS bypass or a production certificate.
    ext=tmp_path/'server.ext';ext.write_text('subjectAltName=DNS:localhost,DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
    cert_path=tmp_path/'next-server.pem'
    subprocess.run(['openssl','x509','-req','-in',str(certificates/'server.csr'),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAcreateserial','-out',str(cert_path),'-days','1','-extfile',str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    tls={name:protected(name,data) for name,data in [('server.pem',cert_path.read_bytes()),('server.key',(certificates/'server.key').read_bytes()),('ca.pem',(certificates/'ca.pem').read_bytes())]}
    consumers={}
    for name in ('read','feedback','measurement'):
        a=f[name];values=json.loads(json.dumps(asdict(a.binding),default=str));values['schema_version']=1
        values['database_url']=protected(name+'-sql',a.url.encode());consumers[name]=values
    root=stage['blobs'].root;info=root.stat();now=datetime.now(timezone.utc)
    end=min(stage['expiry'],*(a.binding.original_horizon for a in (f['read'],f['feedback'],f['measurement'])))
    config=RecommendationConfigV1.model_validate_json(canonical_bytes(dict(schema_version=1,purpose='qualified-recommendation-actions-v1',principal_id=str(stage['actor']),workspace_id=str(stage['w']),model_id=str(stage['f']['model']),**consumers,storage_root=str(root),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=info.st_uid,storage_profile_hash='a'*64,original_horizon=end.isoformat(),expires_at=end.isoformat())))
    cp=protected('advice-config',canonical_bytes(config.model_dump(mode='json')));issuer,reviewer=uuid4(),uuid4()
    peer=RecommendationPeerV1.model_validate_json(canonical_bytes(dict(schema_version=1,purpose='qualified-recommendation-actions-peer-v1',config_sha256=cp['sha256'],principal_id=str(config.principal_id),workspace_id=str(config.workspace_id),model_id=str(config.model_id),read_appointment_id=str(config.read.appointment_id),feedback_appointment_id=str(config.feedback.appointment_id),measurement_appointment_id=str(config.measurement.appointment_id),issuer_actor=str(issuer),reviewer_actor=str(reviewer),client_certificate_sha256=hashlib.sha256(x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes()).public_bytes(Encoding.DER)).hexdigest(),client_uri=WORKER,client_ca=tls['ca.pem'],server_certificate=tls['server.pem'],server_key=tls['server.key'],listen_host='::1',listen_port=0,valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=end.isoformat(),original_horizon=end.isoformat())))
    pp=protected('advice-peer',canonical_bytes(peer.model_dump(mode='json')))
    settings=RecommendationSettingsV1.load(config_path=cp['path'],config_sha256=cp['sha256'],peer_path=pp['path'],peer_sha256=pp['sha256'],expected_issuer_actor=issuer,expected_reviewer_actor=reviewer)
    original_execute=RecommendationFactoryV1.execute_v1;calls=[]
    def observed(self,raw):
        q=json.loads(raw);calls.append(dict(operation=q['operation'],command_id=q.get('command_id'),sha256=hashlib.sha256(raw).hexdigest()))
        (tmp_path/'factory-count').write_text(str(len(calls)))
        return original_execute(self,raw)
    monkeypatch.setattr(RecommendationFactoryV1,'execute_v1',observed)
    original_body=RecommendationFactoryV1._body;private_reads=[]
    def closed_body(self,manifest):
        with psycopg.connect(admin_url) as c:
            assert c.execute('SELECT count(*) FROM pg_stat_activity WHERE application_name=%s',(stage['app_name'],)).fetchone()[0]==0
        private_reads.append(str(manifest.artifact_id));return original_body(self,manifest)
    monkeypatch.setattr(RecommendationFactoryV1,'_body',closed_body)
    server=protected_recommendation_web_server_v1(settings);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01})
    metadata=dict(scratch=str(tmp_path),auth_user_id=str(identity.auth_user_id),employee_id=str(identity.employee_id),principal_id=str(config.principal_id),workspace_id=str(config.workspace_id),model_id=str(config.model_id),runtime_hash=config.read.runtime_hash,registry_hash=config.read.registry_hash,recommendation_config_sha256=cp['sha256'],recommendation_peer_profile_sha256=pp['sha256'],backend_origin='https://localhost.localdomain:'+str(server.server_port),server_key_file=tls['server.key']['path'],server_certificate_file=tls['server.pem']['path'],client_ca_file=tls['ca.pem']['path'],client_certificate_file=str(certificates/'worker.pem'),client_key_file=str(certificates/'worker.key'),client_uri=WORKER,issuer_actor=str(issuer),reviewer_actor=str(reviewer),valid_from=peer.valid_from.isoformat(),expires_at=end.isoformat(),original_horizon=end.isoformat(),web_database_url=identity.web_database_url)
    mp=protected('actual-next-metadata.json',json.dumps(metadata).encode())
    bundle=tmp_path/'synthetic-ca-bundle.pem';bundle.write_bytes((certificates/'ca.pem').read_bytes()+Path(identity.database_root_ca).read_bytes());bundle.chmod(0o600)
    stop=threading.Event();observations=[];monitor_errors=[]
    def monitor():
        disabled=False;withdrawn=False
        try:
            while not stop.wait(.1):
                with psycopg.connect(admin_url) as c:
                    assert c.pgconn.ssl_in_use and c.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',identity.database)
                    for pid,user,db,encrypted,query in c.execute("SELECT a.pid,a.usename,a.datname,s.ssl,a.query FROM pg_stat_activity a JOIN pg_stat_ssl s USING(pid) WHERE a.usename=%s AND a.datname=%s",(identity.login,identity.database)):
                        if 'employee_identities' in query:
                            assert encrypted is True;observations.append(dict(pid=pid,user=user,database=db,tls=encrypted,query_sha256=hashlib.sha256(query.encode()).hexdigest()))
                    if (tmp_path/'withdraw-source').exists() and not withdrawn:
                        owned_worker_database(container,admin_url);ref=stage['sources'][0]
                        c.execute('INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(uuid4(),stage['w'],ref.source_id,ref.revision,ref.original_sha256,stage['actor'],stage['login'],RUNTIME,'invented actual Next source withdrawal',uuid4(),'a'*64));withdrawn=True
                    if (tmp_path/'disable-employee').exists() and not disabled:
                        owned_worker_database(container,admin_url);c.execute('UPDATE public.employees SET disabled_at=clock_timestamp() WHERE id=%s',(identity.employee_id,));disabled=True
                if withdrawn:(tmp_path/'source-withdrawn').write_text('committed')
                if disabled:(tmp_path/'employee-disabled').write_text('committed')
        except BaseException as error:monitor_errors.append(type(error).__name__)
    watcher=threading.Thread(target=monitor);process=None
    try:
        thread.start();watcher.start()
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','TMPDIR','LANG','SHELL')};env['NODE_EXTRA_CA_CERTS']=str(bundle)
        process=subprocess.Popen(['pnpm','--filter','@oracle/web','exec','tsx','tests/oracle2/recommendation-next-auth-proof.ts',mp['path']],cwd=Path(__file__).resolve().parents[3],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        output=''
        try:output,_=process.communicate(timeout=110)
        except subprocess.TimeoutExpired as error:
            output=error.output.decode() if isinstance(error.output,bytes) else (error.output or '')
            raise
        finally:
            for sig in (signal.SIGTERM,signal.SIGKILL):
                try:os.killpg(process.pid,sig)
                except ProcessLookupError:pass
            if process.poll() is None:process.wait(timeout=3)
            (tmp_path/'next-auth-harness.txt').write_text(output)
            remaining=[]
            for attempt in range(20):
                remaining=[]
                for proc in Path('/proc').iterdir():
                    if proc.name.isdecimal():
                        try:
                            fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
                            if int(fields[2])==process.pid and fields[0]!='Z':remaining.append(int(proc.name))
                        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
                if not remaining:break
                time.sleep(.05)
            (tmp_path/'actual-next-process-cleanup.json').write_text(json.dumps(dict(process_group=process.pid,remaining_active=remaining)))
            assert not remaining,remaining
        assert process.returncode==0,output[-6000:]
        receipt=json.loads((tmp_path/'actual-next-receipt.json').read_text())
        assert receipt['actual_next'] and receipt['auth_requests']>receipt['seed_requests'] and receipt['clock_guard_unchanged']
        assert observations and not monitor_errors,monitor_errors
        writes=[c for c in calls if c['operation'] in ('feedback','measurement')]
        with psycopg.connect(admin_url) as c:
            events=c.execute("SELECT command_id,command_sha256,sequence,kind,payload FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s ORDER BY sequence",(stage['w'],)).fetchall()
        if receipt['outcome']=='actual-framework-refused':
            assert writes==[] and events==[]
        else:
            assert [c['operation'] for c in writes]==['feedback','measurement']
            assert len(events)==2 and [e[2:4] for e in events]==[(1,'feedback'),(2,'baseline')]
            assert [(str(e[0]),e[1]) for e in events]==[(c['command_id'],c['sha256']) for c in writes]
            assert events[0][4]['decision']=='accept' and events[0][4]['policy_accepted'] is False and events[0][4]['effect_executed'] is False
            assert events[1][4]['measurement']['amount']=='12.5' and events[1][4]['reported_only'] and events[1][4]['causal_savings'] is False and events[1][4]['realized_savings_verified'] is False
        if receipt['outcome']=='actual-framework-positive':assert private_reads
        (tmp_path/'employee-sql-observation.json').write_text(json.dumps(observations))
        (tmp_path/'actual-next-effect-proof.json').write_text(json.dumps(dict(outcome=receipt['outcome'],factory_calls=calls,private_reads=len(private_reads),events=[dict(command_id=str(e[0]),command_sha256=e[1],sequence=e[2],kind=e[3]) for e in events],company_policy_accepted=False,effect_executed=False,realized_savings_verified=False)))
        assert receipt['outcome']=='actual-framework-positive','actual Next refusal remains an architecture blocker, not acceptance'
    finally:
        stop.set()
        if watcher.ident is not None:watcher.join(3)
        assert not watcher.is_alive()
        if thread.ident is not None:server.shutdown()
        server.server_close()
        if thread.ident is not None:thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1
