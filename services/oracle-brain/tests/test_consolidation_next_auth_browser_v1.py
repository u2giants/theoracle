"""Actual Next framework, invented HTTPS auth protocol and real employee SQL.

Host-prepared qualified fixtures are not native generation or business proof.
A framework refusal is retained as an architecture blocker, not acceptance.
"""
from dataclasses import asdict,replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
import hashlib,json,subprocess,threading,ssl,http.client,time
import psycopg
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.consolidation_review_settings_v1 import ModelReviewConfigV1,ModelReviewPeerV1,ModelReviewSettingsV1
from oracle_brain.hosting.consolidation_review_service_v1 import protected_model_review_server_v1
from test_consolidation_sql_v1 import sql_qualified_v3,prepared_qualified_model,history_actor,adapter
from test_hosting_boundary import certificates,WORKER

def test_actual_next_auth_employee_sql_model_review(admin_url,sql_qualified_v3,tmp_path,certificates,monkeypatch):
    state=prepared_qualified_model(admin_url,sql_qualified_v3,tmp_path,return_fixture=True)
    previous=state
    # FRESH second source population, census/assembly/assessment commitments;
    # never retrofit old raw responses or inherit old semantic admission.
    import test_assembly_context as foundation
    import test_purpose_qualification_v3 as qualification
    original_make=qualification.make_v2
    def corrected(context):
        ctx,model,at=original_make(context)
        return ctx.model_copy(update={'model_id':previous['ctx'].model_id,'model_version':2,
            'job':ctx.job.model_copy(update={'artifact_id':previous['ctx'].model_id})}),model.model_copy(update={'model_id':previous['ctx'].model_id,'version':2}),at
    monkeypatch.setattr(qualification,'make_v2',corrected)
    fresh=qualification.qualified_v3.__wrapped__(foundation.context.__wrapped__())
    second=tmp_path/'corrected';second.mkdir(mode=0o700)
    state=prepared_qualified_model(admin_url,fresh,second,return_fixture=True,predecessor=previous)
    f,h,q,blobs=state['f'],state['h'],state['q'],state['blobs'];f['expiry']=datetime.now(timezone.utc)+timedelta(minutes=3)
    core=q['payload']['consolidation_core'];scope=core['assertions'][0]['scope']
    business=history_actor(admin_url,f,operation='business-review',scope_hash=digest(scope),principal=h['actor'])
    history=replace(state['history'].binding,retained_semantic_admissions=q['trusted_admission_hashes']|previous['q']['trusted_admission_hashes'])
    review=replace(adapter(admin_url,f,business).binding,operation='business-review',retained_semantic_admissions=q['trusted_admission_hashes']|previous['q']['trusted_admission_hashes'])
    def protected(name,data):
        path=tmp_path/name;path.write_bytes(data);path.chmod(0o600)
        return dict(path=str(path),sha256=hashlib.sha256(data).hexdigest())
    def consumer(binding,url,name):
        values=asdict(binding);values['retained_semantic_admissions']=tuple(sorted(binding.retained_semantic_admissions))
        values['database_url']=protected(name,url.encode());return values
    tls=tmp_path/'review-tls';tls.mkdir(mode=0o700)
    ext=tls/'server.ext';ext.write_text('subjectAltName=DNS:localhost,DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
    server_cert=tls/'server.pem'
    subprocess.run(['openssl','x509','-req','-in',str(certificates/'server.csr'),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAcreateserial','-out',str(server_cert),'-days','1','-extfile',str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    cert=protected('server.pem',server_cert.read_bytes());key=protected('server.key',(certificates/'server.key').read_bytes());ca=protected('client-ca.pem',(certificates/'ca.pem').read_bytes())
    Path(blobs.root).chmod(0o700);info=Path(blobs.root).stat();end=min(history.original_horizon,review.original_horizon)
    config=ModelReviewConfigV1.model_validate(dict(schema_version=1,purpose='qualified-model-review-v1',principal_id=h['actor'],workspace_id=f['workspace'],model_id=f['model'],history=consumer(history,h['url'],'history-url'),business=consumer(review,business['url'],'business-url'),decision_kind='employee-account',storage_root=str(blobs.root),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=info.st_uid,storage_profile_hash='a'*64,original_horizon=end,expires_at=end))
    cp=protected('review-config.json',canonical_bytes(config.model_dump(mode='json')));issuer,reviewer=uuid4(),uuid4()
    peer=ModelReviewPeerV1.model_validate(dict(schema_version=1,purpose='qualified-model-review-peer-v1',config_sha256=cp['sha256'],principal_id=h['actor'],workspace_id=f['workspace'],model_id=f['model'],history_appointment_id=h['aid'],business_appointment_id=business['aid'],issuer_actor=issuer,reviewer_actor=reviewer,client_certificate_sha256=hashlib.sha256(x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes()).public_bytes(serialization.Encoding.DER)).hexdigest(),client_uri=WORKER,client_ca=ca,server_certificate=cert,server_key=key,listen_host='::1',listen_port=0,valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=end,original_horizon=end))
    pp=protected('review-peer.json',canonical_bytes(peer.model_dump(mode='json')))
    settings=ModelReviewSettingsV1.load(config_path=cp['path'],config_sha256=cp['sha256'],peer_path=pp['path'],peer_sha256=pp['sha256'],expected_issuer_actor=issuer,expected_reviewer_actor=reviewer)
    from oracle_brain.hosting.consolidation_review_v1 import ModelReviewFactoryV1
    original_execute=ModelReviewFactoryV1.execute_v1;calls=[]
    def observed(self,raw):
        calls.append(raw);(tmp_path/'factory-count').write_text(str(len(calls)))
        try:result=original_execute(self,raw)
        except Exception:
            import traceback
            (tmp_path/'factory-error.txt').write_text(traceback.format_exc());raise
        (tmp_path/'factory-result.json').write_bytes(result[0])
        if json.loads(raw)['operation']=='decide':
            with psycopg.connect(admin_url) as c:
                c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope=ANY(%s)',
                    (f['workspace'],h['actor'],['source-read:'+str(ref.source_id) for ref in previous['sources']]))
        return result
    monkeypatch.setattr(ModelReviewFactoryV1,'execute_v1',observed)
    # Same actual fresh-owned identity fixture; production auth imports stay unchanged.
    import os
    from invented_next_employee_fixture_v1 import invented_next_employee_fixture_v1
    container=os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER']
    identity=invented_next_employee_fixture_v1(admin_url,container=container)
    auth_user,employee,login,dbname=identity.auth_user_id,identity.employee_id,identity.login,identity.database
    web_url=identity.web_database_url
    params=psycopg.conninfo.conninfo_to_dict(admin_url)
    # Observe unchanged actual boundaries without substituting auth/validation.
    import oracle_brain.hosting.consolidation_review_service_v1 as service_module
    boundary_events=[]
    def observing(name,original):
        def wrapped(*args,**kwargs):
            try:result=original(*args,**kwargs)
            except BaseException as exc:
                boundary_events.append(dict(boundary=name,outcome='refused',error_type=type(exc).__name__))
                raise
            boundary_events.append(dict(boundary=name,outcome='passed'))
            return result
        return wrapped
    for name in ('fixed_request_length_v1','peer_der_v1','read_request_body_v1','parse_review_request'):
        monkeypatch.setattr(service_module,name,observing(name,getattr(service_module,name)))
    server=protected_model_review_server_v1(settings)
    monkeypatch.setattr(server,'get_request',observing('actual_tls_get_request',server.get_request))
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    metadata=dict(scratch=str(tmp_path),auth_user_id=str(auth_user),employee_id=str(employee),principal_id=str(h['actor']),workspace_id=str(f['workspace']),model_id=str(f['model']),runtime_hash=history.runtime_hash,registry_hash=history.registry_hash,review_config_sha256=cp['sha256'],review_peer_profile_sha256=pp['sha256'],backend_origin='https://localhost.localdomain:'+str(server.server_port),server_key_file=key['path'],server_certificate_file=cert['path'],client_ca_file=ca['path'],client_certificate_file=str(certificates/'worker.pem'),client_key_file=str(certificates/'worker.key'),client_uri=WORKER,issuer_actor=str(issuer),reviewer_actor=str(reviewer),valid_from=peer.valid_from.isoformat(),expires_at=end.isoformat(),original_horizon=end.isoformat(),web_database_url=web_url)
    mp=protected('actual-next-metadata.json',json.dumps(metadata).encode())
    bundle=tmp_path/'synthetic-ca-bundle.pem';bundle.write_bytes((certificates/'ca.pem').read_bytes()+Path(params['sslrootcert']).read_bytes());bundle.chmod(0o600)
    stop=threading.Event();observations=[];monitor_errors=[]
    def monitor():
        disabled=False
        try:
            while not stop.wait(.1):
                with psycopg.connect(admin_url) as c:
                    assert c.pgconn.ssl_in_use and c.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',dbname)
                    for pid,user,db,encrypted,query in c.execute("""SELECT a.pid,a.usename,a.datname,s.ssl,a.query FROM pg_stat_activity a JOIN pg_stat_ssl s USING(pid) WHERE a.usename=%s AND a.datname=%s""",(login,dbname)):
                        if 'employee_identities' in query:
                            assert encrypted is True
                            observations.append(dict(pid=pid,user=user,database=db,tls=encrypted,query_sha256=hashlib.sha256(query.encode()).hexdigest()))
                    if (tmp_path/'disable-employee').exists() and not disabled:
                        owned_worker_database(container,admin_url)
                        c.execute('UPDATE public.employees SET disabled_at=clock_timestamp() WHERE id=%s',(employee,));disabled=True
                if disabled:(tmp_path/'employee-disabled').write_text('committed')
        except BaseException as exc:monitor_errors.append(str(exc))
    watcher=threading.Thread(target=monitor);watcher.start()
    try:
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','TMPDIR','LANG','SHELL')}
        env['NODE_EXTRA_CA_CERTS']=str(bundle)
        import signal
        process=subprocess.Popen(['pnpm','--filter','@oracle/web','exec','tsx','tests/oracle2/model-review-next-auth-proof.ts',mp['path']],cwd=Path(__file__).resolve().parents[3],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        output=''
        try:
            output,_=process.communicate(timeout=110)
        except subprocess.TimeoutExpired as exc:
            output=exc.output.decode() if isinstance(exc.output,bytes) else (exc.output or '')
            raise
        finally:
            # Exact own process group includes Next descendants even if pnpm
            # exits first. Never touch a foreign name/port/process namespace.
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
        (tmp_path/'employee-sql-observation.json').write_text(json.dumps(observations))
        with psycopg.connect(admin_url) as c:
            events=c.execute("SELECT kind,payload->>'decision_kind' FROM oracle2.processing_model_events_v1 WHERE workspace_id=%s AND artifact_id=%s AND kind='business-accept'",(f['workspace'],f['model'])).fetchall()
        if receipt['outcome']=='actual-framework-refused':assert calls==[] and events==[]
        else:
            assert receipt['outcome']=='actual-framework-positive' and events==[('business-accept','employee-account')]
            assert [json.loads(raw)['operation'] for raw in calls]==['inspect','inspect','inspect','decide','inspect']
        (tmp_path/'actual-next-effect-proof.json').write_text(json.dumps(dict(outcome=receipt['outcome'],factory_calls=len(calls),business_events=events)))
        assert receipt['outcome']=='actual-framework-positive','actual Next refused; retained architecture evidence is not positive acceptance'
    finally:
        (tmp_path/'actual-backend-boundaries.json').write_text(json.dumps(boundary_events))
        stop.set();watcher.join(3);assert not watcher.is_alive()
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1
