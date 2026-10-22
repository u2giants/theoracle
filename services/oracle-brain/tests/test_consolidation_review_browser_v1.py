"""Actual invented browser→production API→mTLS→owned SQL/private bytes.

Auth import hooks and phase qualification are explicit invented fixtures. This
is not a real Supabase session, paid generation, installation or business proof.
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

def test_actual_browser_owned_sql_qualified_model_review(admin_url,sql_qualified_v3,tmp_path,certificates,monkeypatch):
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
    # The original caller window may be longer than an old-history grant.
    # Actual private snapshot/delivery must retain the shorter SQL lease.
    history_limit=datetime.now(timezone.utc)+timedelta(seconds=12)
    with psycopg.connect(admin_url) as c:c.execute('UPDATE oracle2.appointments SET expires_at=%s WHERE workspace_id=%s AND actor_id=%s AND scope=%s',
        (history_limit,f['workspace'],h['actor'],'source-history:'+str(previous['sources'][0].source_id)+':1'))
    body=canonical_bytes(dict(schema_version=1,operation='inspect',model_id=str(f['model']),base_version=1,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=25)).isoformat().replace('+00:00','Z')))
    probe=ModelReviewFactoryV1(settings);probe_data,probe_until=original_execute(probe,body)
    assert json.loads(probe_data)['basePermitted'] is True and probe_until<=history_limit
    server=protected_model_review_server_v1(settings);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    metadata=dict(scratch=str(tmp_path),auth_user_id=str(uuid4()),employee_id=str(uuid4()),project_url='https://invented-auth.invalid',principal_id=str(h['actor']),workspace_id=str(f['workspace']),model_id=str(f['model']),runtime_hash=history.runtime_hash,registry_hash=history.registry_hash,review_config_sha256=cp['sha256'],review_peer_profile_sha256=pp['sha256'],backend_origin='https://localhost.localdomain:'+str(server.server_port),server_key_file=key['path'],server_certificate_file=cert['path'],client_ca_file=ca['path'],client_certificate_file=str(certificates/'worker.pem'),client_key_file=str(certificates/'worker.key'),client_uri=WORKER,issuer_actor=str(issuer),reviewer_actor=str(reviewer),valid_from=peer.valid_from.isoformat(),expires_at=end.isoformat(),original_horizon=end.isoformat())
    mp=protected('review-browser-metadata.json',json.dumps(metadata).encode())
    try:
        result=subprocess.run(['pnpm','--filter','@oracle/web','exec','tsx','tests/oracle2/model-review-proof.ts',mp['path']],cwd=Path(__file__).resolve().parents[3],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=55)
        (tmp_path/'browser-process.txt').write_text(result.stdout)
        assert result.returncode==0,result.stdout[-6000:]
        receipt=json.loads((tmp_path/'browser-receipt.json').read_text());assert receipt['actual_browser'] and receipt['auth']=='invented existing-import hooks'
        assert len(calls)==4
        def direct(raw,*,identity='worker',path='/v1/replacement/model-review',extra=()):
            context=ssl.create_default_context(cafile=str(certificates/'ca.pem'));context.load_cert_chain(str(certificates/(identity+'.pem')),str(certificates/(identity+'.key')))
            connection=http.client.HTTPSConnection('localhost',server.server_port,context=context,timeout=3)
            try:
                connection.putrequest('POST',path);connection.putheader('Content-Length',str(len(raw)));connection.putheader('Content-Type','application/json')
                for key,value in extra:connection.putheader(key,value)
                connection.endheaders(raw);response=connection.getresponse();response.read();return response.status
            finally:connection.close()
        valid=canonical_bytes(dict(schema_version=1,operation='inspect',model_id=str(f['model']),base_version=1,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat().replace('+00:00','Z')))
        before=len(calls)
        assert direct(valid,identity='other')==503
        assert direct(valid,path='/v1/replacement/advance')==503
        assert direct(valid,extra=(('Content-Encoding','gzip'),))==503
        assert direct(valid,extra=(('Content-Type','application/json'),))==503
        assert direct(valid,extra=(('Transfer-Encoding','chunked'),))==503
        assert direct(valid.replace(b'"base_version":1',b'"base_version":1,"actor_id":"untrusted"'))==503
        expired=json.loads(valid);expired['caller_deadline']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat().replace('+00:00','Z')
        assert direct(canonical_bytes(expired))==503
        assert len(calls)==before
        # Same bytes in a replaced protected installation still refuse.
        config_path=Path(cp['path']);data=config_path.read_bytes();replacement=tmp_path/'replacement-config';replacement.write_bytes(data);replacement.chmod(0o600);replacement.replace(config_path)
        assert direct(valid)==503 and len(calls)==before
        with psycopg.connect(admin_url) as c:
            rows=c.execute("SELECT kind,payload->>'decision_kind' FROM oracle2.processing_model_events_v1 WHERE workspace_id=%s AND artifact_id=%s AND kind='business-accept'",(f['workspace'],f['model'])).fetchall()
            assert rows==[('business-accept','employee-account')]
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1
