"""Actual SQL ACK + native read-only SDK graph; invented vectors, no paid call."""
import asyncio,os,time
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit,urlunsplit
from uuid import uuid4,UUID
import psycopg
from psycopg.types.json import Jsonb
import pytest
from graphrag_sdk import ConnectionConfig
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1
from oracle_brain.operating_model.paid_sdk_embeddings_v3 import PaidProjectionEmbedderV3,verify_paid_sdk_embedding_v3
from oracle_brain.operating_model.projection_delivery import signature
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from oracle_brain.operating_model.sdk_projection import PaidConsolidationSDKProjectionV1,ConsolidatedMetadataSDKProjectionV1
from test_consolidation_sql_v1 import sql_qualified_v3,sql_qualified_serving_v3,prepared_qualified_model,RUNTIME,REGISTRY
from test_connected_answer_sql_v1 import own_history
from test_paid_sdk_embeddings_v3 import paid_case_for
from test_purpose_transport import bound_tls,certificates,SERVER
from test_hosting_boundary import WORKER


def _exercise_owned_answer_graph_v1(admin_url,sql_qualified_v3,tmp_path,bound_tls,certificates,*,proof_scope):
 from dev.oracle2.test_readonly_graph_fixture import processing_writer,processing_reader_scope,owned_target
 from dev.oracle2.test_graph_tls_fixture import owned_graph_tls,verify_graph_tls_peer
 def browser_assertions(ctx):
  # Each assertion is captured and assessed with its actual original/extraction;
  # the retained default fixture has only one assertion for two processes.
  # Do not pretend its unrelated process has a record or retrofit after capture.
  return [dict(assertion_id=str(uuid4()),revision=1,subject_id=str(uuid4()),predicate='reported_step',
   value=extraction.payload['observations'][0]['value'],provenance='employee_account',
   scope={key:{'mode':'unknown','identities':[]} for key in ('process','customer','product','region')},
   valid_time='unknown',supporting_observations=[extraction.payload['observations'][0]['observation_id']])
   for extraction in ctx.extractions]
 state=prepared_qualified_model(admin_url,sql_qualified_v3,tmp_path,return_fixture=True,
  assertion_factory=browser_assertions if proof_scope=='browser' else None)
 m=state['manifest'];payload=state['q']['payload'];f=state['f']
 h,authority=own_history(admin_url,f)
 authority=ConsolidationAuthorityV1(h['url'],binding=replace(authority.binding,retained_semantic_admissions=state['q']['trusted_admission_hashes']),delivery_capability_body_hashes=authority.delivery_capability_body_hashes)
 graph=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL'];container=os.environ['COMPOSE_PROJECT_NAME']+'-falkor-candidate-1'
 owned_target(container,graph);generation=uuid4();tls,_=bound_tls
 name=f'oracle_processing_v1_{m.workspace_id.hex}_{m.artifact_id.hex}_{m.version}_{generation.hex}'
 def config_for(url):
  return ConnectionConfig.from_url(url,graph_name=name,ssl=True,ssl_check_hostname=True,ssl_cert_reqs='required',ssl_ca_certs=str(certificates/'ca.pem'),ssl_certfile=str(certificates/'worker.pem'),ssl_keyfile=str(certificates/'worker.key'),query_timeout_ms=3000,retry_count=1,pool_timeout=1)
 async def run():
  with processing_writer(container,graph,tmp_path/'writer',workspace_id=m.workspace_id,artifact_id=m.artifact_id,version=m.version,generation=generation) as writer:
   with owned_graph_tls(container,graph,server_context=tls,expected_client_uri=WORKER) as port:
    verify_graph_tls_peer(port,ca_file=certificates/'ca.pem',certificate_file=certificates/'worker.pem',key_file=certificates/'worker.key',expected_server_uri=SERVER)
    def tls_url(url):
     parsed=urlsplit(url);return urlunsplit(('rediss',parsed.netloc.rsplit('@',1)[0]+'@localhost:'+str(port),'','',''))
    writable=tls_url(writer.environment['ORACLE2_TEST_PROCESSING_WRITER_GRAPH_URL'])
    projection=PaidConsolidationSDKProjectionV1(writable,workspace_id=m.workspace_id,artifact_id=m.artifact_id,artifact_version=m.version,generation=generation,embedder=PaidProjectionEmbedderV3(verify_paid_sdk_embedding_v3(**paid_case_for(payload,m))),qualification_guard=state['guard'],connection_config=config_for(writable))
    try:
     built=await projection.build(state['ledger'],m.workspace_id,m.artifact_id,m.version)
     # Build completion alone supplies no delivery. The real fixed canonical
     # lease and ACK are observed separately under the actual own compiler.
     with psycopg.connect(f['url']) as c:
      c.execute("SET LOCAL statement_timeout='5s'")
      lease=c.execute('SELECT oracle2.lease_processing_projection(%s,%s,%s,30)',(m.workspace_id,RUNTIME,REGISTRY)).fetchone()[0]
     assert lease['assertion_id']==str(m.artifact_id)
     body=dict(schema_version=3,event_id=lease['event_id'],workspace_id=str(m.workspace_id),artifact_id=str(m.artifact_id),version=m.version,content_hash=m.content_hash,source_digest=m.source_digest,permission_digest=m.permission_digest,graph_name=name,record_digest=built['record_digest'],sdk_version='1.4.0',projector_id='invented-native-vector-wire-real-SDK-SQL-proof',lease_role=f['login'],lease_token=lease['lease_token'],lease_attempt=lease['attempts'],lease_until=lease['lease_until'],projection_schema=built['projection_schema'],projection_digest=built['projection_digest'],embedding_protocol='paid-sdk-embedding-v3',**{k:v for k,v in built['paid_embedding'].items() if k not in ('schema_version','embedding_protocol')})
     secret=b'invented-readonly-graph-fixture-signature-key';seal=signature(secret,body)
     with psycopg.connect(f['url']) as c:
      c.execute("SET LOCAL statement_timeout='5s'")
      acknowledged=c.execute('SELECT oracle2.ack_processing_projection(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(lease['event_id'],m.workspace_id,lease['lease_token'],lease['attempts'],Jsonb(body),seal,RUNTIME,REGISTRY,datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]
     assert acknowledged['receipt']==body
     def actual_delivery(event):
      # Test fixture authorization uses the actual existing SQL current getter,
      # never an administrative table read or caller-authored ACK callback.
      value=state['source'].projection_receipt_v3(m.workspace_id,m.artifact_id,m.version)
      assert str(value.receipt.event_id)==str(event)
      return value.receipt.model_dump(mode='json')|{'signature':value.signature}
     with processing_reader_scope(container,graph,tmp_path/'reader',receipt=body|{'signature':seal},secret=secret,current_delivery=actual_delivery) as reader:
      readonly=tls_url(reader['ORACLE2_TEST_PROCESSING_READONLY_GRAPH_URL'])
      with _request_fence_v1(float(time.monotonic()+30)):
       served=ConsolidatedMetadataSDKProjectionV1(readonly,authority=authority,blobs=FileBlobStore(state['blobs'].root),model_id=m.artifact_id,version=m.version,generation=generation,connection_config=config_for(readonly),deadline=datetime.now(timezone.utc)+timedelta(seconds=29))
       try:
        packet=await served.load();assert digest(packet[2])==m.content_hash
        assert served.rag._conn is served.connection
        await served.verify(packet[2])
        with pytest.raises(PermissionError):await served.build(None)
        with pytest.raises(Exception):await served.connection.query('CREATE (:Forbidden)')
        lineage=(await projection.connection.query("MATCH (a:ReportedAssertionRecord)-[r:SUPPORTED_BY]->(e) RETURN a.id,e.id,r.polarity")).result_set
        assert lineage
        await projection.connection.query("MATCH (:ReportedAssertionRecord)-[r:SUPPORTED_BY]->() SET r.polarity='invented'")
        with pytest.raises(ValueError,match='assertion evidence'):await served.verify(packet[2])
        for a,e,polarity in lineage:
         await projection.connection.query("MATCH (a:ReportedAssertionRecord {id:$a})-[r:SUPPORTED_BY]->(e {id:$e}) SET r.polarity=$polarity",params={'a':a,'e':e,'polarity':polarity})
        await served.verify(packet[2])
        from test_connected_answer_service_v1 import install_answer,tls_request
        from oracle_brain.hosting.connected_answer_service_v1 import protected_connected_answer_server_v1,AnswerRequestV1
        from oracle_brain.workflows.answer import AnswerQueryV1
        from oracle_brain.operating_model.consolidation_contracts_v1 import AssertionScopeV1
        from oracle_brain.operating_model.contracts import canonical_bytes
        import threading,json
        import subprocess,hashlib
        from pathlib import Path
        # Fresh test-owned server leaf covers both explicit localhost names.
        extra=tmp_path/'browser-tls';extra.mkdir(mode=0o700)
        def openssl(*args):subprocess.run(['openssl',*map(str,args)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        ext=extra/'server.ext';ext.write_text('subjectAltName=DNS:localhost,DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\n')
        leaf=extra/'server.pem';openssl('x509','-req','-in',certificates/'server.csr','-CA',certificates/'ca.pem','-CAkey',certificates/'ca.key','-CAcreateserial','-out',leaf,'-days','1','-extfile',ext)
        settings=install_answer(state,authority,h,readonly,generation,certificates,tmp_path/'answer-install',server_certificate=leaf,listen_host='::1')
        server=protected_connected_answer_server_v1(settings)
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
        try:
         q=AnswerQueryV1(question='reported_step',mode='global',scope=AssertionScopeV1.model_validate_json(canonical_bytes({k:{'mode':'all','identities':[]} for k in ('process','customer','product','region')})))
         def request():return canonical_bytes(AnswerRequestV1(caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=28),query=q).model_dump(mode='json'))
         status,wire=tls_request(server,certificates,request())
         assert status==200,wire
         public=json.loads(wire);assert public['answer']['records'] and public['answer']['provider_generation_used'] is False,public['answer']
         if proof_scope=='backend':
          from oracle_brain.workflows.natural_answer_v1 import NaturalQuestionRequestV1
          unrelated=payload['consolidation_core']['model']['processes'][1]['label']
          question=NaturalQuestionRequestV1(question='What is reported in '+unrelated+'?',caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=28))
          missing_status,missing_wire=tls_request(server,certificates,canonical_bytes(question.model_dump(mode='json')))
          assert missing_status==200,missing_wire
          missing=json.loads(missing_wire)
          assert missing['answer']['state']=='missing' and missing['answer']['records']==[]
         if proof_scope=='workspace':
          from oracle_brain.hosting.qualified_workspace_v1 import WorkspaceRequestV1
          def workspace_request(operation='overview',process=None):
           return canonical_bytes(WorkspaceRequestV1(protocol='qualified-workspace-question-v1',operation=operation,process_id=process,page=0,caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=11)).model_dump(mode='json'))
          process_id=payload['consolidation_core']['model']['processes'][0]['process_id']
          for operation,selected in [('overview',None),('process',process_id)]:
           original=workspace_request(operation,selected);workspace_status,workspace_wire=tls_request(server,certificates,original)
           assert workspace_status==200,workspace_wire
           actual=json.loads(workspace_wire)
           assert actual['protocol']=='qualified-workspace-answer-v1' and actual['operation']==operation
           assert actual['principal_id']==str(h['actor']) and actual['request_sha256']==hashlib.sha256(original).hexdigest()
           assert actual['result']['process_count']==len(payload['consolidation_core']['model']['processes'])
           assert actual['result']['company_wide_completeness_verified'] is False and actual['result']['source_health_observed'] is False
           if selected is not None:assert actual['result']['selected_process']['process_id']==selected
           response_path=tmp_path/('workspace-'+operation+'.json');response_path.write_bytes(workspace_wire);response_path.chmod(0o600)
           project_root=Path(__file__).resolve().parents[3]
           with (tmp_path/('workspace-'+operation+'-decode.txt')).open('w') as decoder_log:
            checked=subprocess.run(['pnpm','--filter','@oracle/web','exec','tsx','lib/__verify__/qualified-workspace-wire.ts',str(response_path)],cwd=project_root,env={**os.environ},stdout=decoder_log,stderr=subprocess.STDOUT,timeout=10)
           assert checked.returncode==0,(tmp_path/('workspace-'+operation+'-decode.txt')).read_text()
          assert tls_request(server,certificates,workspace_request(),client='other')[0]==503
          assert tls_request(server,certificates,workspace_request('process','not-in-this-model'))[0]==503
         assert public['retained_projection_lease_until']==body['lease_until']
         assert tls_request(server,certificates,request(),client='other')[0]==503
         (tmp_path/'actual-answer-response.json').write_bytes(wire)
         from test_conversation_answer_v1 import exercise_actual_interview_answer
         interview_owner,interview_control,interview_snapshot,interview_turn=exercise_actual_interview_answer(admin_url,state,h,settings,tmp_path/'conversation-install')
         interview_owner.close()
         if proof_scope=='browser':
          # A distinct externally installed employee MCP peer uses a different
          # actual key/URI; no static legacy MCP token or role substitution.
          mcp_uri='spiffe://oracle/employee-mcp-source-proof'
          mcp_cert,mcp_key,mcp_csr=(extra/name for name in ('mcp.pem','mcp.key','mcp.csr'))
          openssl('req','-newkey','rsa:2048','-nodes','-keyout',mcp_key,'-out',mcp_csr,'-subj','/CN=Invented employee MCP')
          mcp_ext=extra/'mcp.ext';mcp_ext.write_text('subjectAltName=URI:'+mcp_uri+'\nextendedKeyUsage=clientAuth\nbasicConstraints=critical,CA:FALSE\n')
          openssl('x509','-req','-in',mcp_csr,'-CA',certificates/'ca.pem','-CAkey',certificates/'ca.key','-CAcreateserial','-out',mcp_cert,'-days','1','-extfile',mcp_ext)
          for file in (mcp_key,mcp_cert):file.chmod(0o600)
          mcp_settings=install_answer(state,authority,h,readonly,generation,certificates,tmp_path/'mcp-answer-install',channel='mcp',peer_certificate=mcp_cert,peer_key=mcp_key,peer_uri=mcp_uri,server_certificate=leaf,listen_host='::1',actors=(settings.peer.issuer_actor,settings.peer.reviewer_actor))
          mcp_server=protected_connected_answer_server_v1(mcp_settings)
          # Private invented-fixture diagnostics observe the SAME real method;
          # they neither replace authorization nor turn a refusal into success.
          web_owned=server.answer_owned_loop.service
          actual_web_handler=web_owned.handle_answer_v1
          async def observed_web_handler(raw):
           try:return await actual_web_handler(raw)
           except Exception as error:
            path=tmp_path/'web-owned-refusal.json';path.write_text(json.dumps(dict(type=type(error).__name__,reason=str(error))));path.chmod(0o600)
            raise
          web_owned.handle_answer_v1=observed_web_handler
          mcp_owned=mcp_server.answer_owned_loop.service
          actual_mcp_handler=mcp_owned.handle_answer_v1
          async def observed_mcp_handler(raw):
           try:return await actual_mcp_handler(raw)
           except Exception as error:
            (tmp_path/'mcp-owned-refusal.json').write_text(json.dumps(dict(type=type(error).__name__,reason=str(error))))
            raise
          mcp_owned.handle_answer_v1=observed_mcp_handler
          mcp_thread=threading.Thread(target=mcp_server.serve_forever,kwargs={'poll_interval':.01},daemon=True);mcp_thread.start()
          try:
           import ssl,http.client
           context=ssl.create_default_context(cafile=str(certificates/'ca.pem'));context.load_cert_chain(mcp_cert,mcp_key)
           direct=http.client.HTTPSConnection('localhost.localdomain',mcp_server.server_port,context=context,timeout=30)
           try:
            direct.request('POST','/v1/employee/mcp-answer',body=request(),headers={'Content-Type':'application/json','Connection':'close'})
            direct_response=direct.getresponse();direct_wire=direct_response.read()
            assert direct_response.status==200,direct_wire
            assert json.loads(direct_wire)['channel']=='mcp'
           finally:direct.close()
           expected=[]
           for process in payload['consolidation_core']['model']['processes']:
            ids=set(process['observation_ids'])
            expected.append(dict(label=process['label'],process_id=process['process_id'],assertion_ids=sorted(a['assertion_id'] for a in payload['consolidation_core']['assertions'] if ids&set(a['supporting_observations']))))
           assert len(expected)>=2 and all(p['assertion_ids'] for p in expected[:2])
           assert set(expected[0]['assertion_ids']).isdisjoint(expected[1]['assertion_ids'])
           meta=dict(process_expectations=expected,scratch=str(tmp_path),auth_user_id=str(uuid4()),employee_id=str(uuid4()),project_url='https://invented-answer.supabase.co',principal_id=str(h['actor']),workspace_id=str(m.workspace_id),model_id=str(m.artifact_id),runtime_hash=RUNTIME,registry_hash=REGISTRY,
            server_certificate_file=settings.peer.server_certificate.path,server_key_file=settings.peer.server_key.path,client_ca_file=settings.peer.client_ca.path,
            issuer_actor=str(settings.peer.issuer_actor),reviewer_actor=str(settings.peer.reviewer_actor),valid_from=settings.peer.valid_from.isoformat(),expires_at=settings.peer.expires_at.isoformat(),original_horizon=settings.peer.original_horizon.isoformat(),
            web=dict(answer_config_sha256=settings.config_sha256,answer_peer_sha256=settings.peer_sha256,backend_origin='https://localhost.localdomain:'+str(server.server_port),client_certificate_file=str(certificates/'worker.pem'),client_key_file=str(certificates/'worker.key'),client_uri=WORKER),
            mcp=dict(answer_config_sha256=mcp_settings.config_sha256,answer_peer_sha256=mcp_settings.peer_sha256,backend_origin='https://localhost.localdomain:'+str(mcp_server.server_port),client_certificate_file=str(mcp_cert),client_key_file=str(mcp_key),client_uri=mcp_uri))
           metadata=tmp_path/'browser-metadata.json';metadata.write_text(json.dumps(meta));metadata.chmod(0o600)
           project_root=Path(__file__).resolve().parents[3]
           with (tmp_path/'browser-output.txt').open('w') as log:
            result=subprocess.run(['pnpm','--filter','@oracle/web','exec','tsx','tests/oracle2/connected-answer-proof.ts',str(metadata)],cwd=project_root,env={**os.environ},stdout=log,stderr=subprocess.STDOUT,timeout=70)
           assert result.returncode==0,(tmp_path/'browser-output.txt').read_text()
           assert json.loads((tmp_path/'browser-receipt.json').read_text())['actual_browser'] is True
          finally:
           mcp_server.shutdown();mcp_server.server_close();mcp_thread.join(3)
           assert not mcp_thread.is_alive() and not mcp_server.answer_owned_loop.thread.is_alive()

         with psycopg.connect(admin_url) as c:c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h['aid'],))
         status,wire=tls_request(server,certificates,request());assert status==503 and b'reported_step' not in wire
         if proof_scope=='workspace':
          denied_status,denied_wire=tls_request(server,certificates,workspace_request())
          assert denied_status==503 and b'qualified-workspace-answer-v1' not in denied_wire
         from oracle_brain.hosting.conversation_answer_v1 import ConversationAnswerV1
         revoked_interview=ConversationAnswerV1(interview_control,settings)
         try:
          missing=revoked_interview.present_turn_v1(interview_snapshot,interview_turn)
          assert missing['qualified_answer'] is None and 'do not establish an answer' in missing['answer_first']
          assert missing['question_id']==interview_snapshot['pending_question_id']
          assert missing['question_count']==interview_snapshot['question_count']
          unchanged=interview_control.snapshot_v1(UUID(interview_snapshot['thread_id']))
          assert unchanged['revision']==interview_snapshot['revision'] and unchanged['events']==interview_snapshot['events']
         finally:revoked_interview.close()
        finally:
         server.shutdown();server.server_close();thread.join(3)
         assert not thread.is_alive() and not server.answer_owned_loop.thread.is_alive()
       finally:await served.close()
      # A distinct current read AFTER the browser/MCP journey has its own
      # original request. Never reuse/extend the earlier SDK object's spent
      # 29-second request merely to observe an exact SQL privilege refusal.
      # Same actual graph/ACK/source population; no qualification/lease renewal.
      with _request_fence_v1(float(time.monotonic()+12)):
       revoked=None
       try:
        # The real constructor already checks current SQL permission; an early
        # exact denial is required, not a reason to bypass that check for load.
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
         revoked=ConsolidatedMetadataSDKProjectionV1(readonly,authority=authority,
             blobs=FileBlobStore(state['blobs'].root),model_id=m.artifact_id,
             version=m.version,generation=generation,connection_config=config_for(readonly),
             deadline=datetime.now(timezone.utc)+timedelta(seconds=11))
         await revoked.load()
       finally:
        if revoked is not None:await revoked.close()
    finally:await projection.close()
 asyncio.run(run())


def test_actual_qualified_SQL_ACK_readonly_SDK_and_current_permission_before_after(admin_url,sql_qualified_v3,tmp_path,bound_tls,certificates):
 # Backend-only proof keeps the actual SQL/SDK/TLS/S06 guards; it deliberately
 # claims no browser/MCP result. The separate required test below owns those.
 return _exercise_owned_answer_graph_v1(admin_url,sql_qualified_v3,tmp_path,bound_tls,certificates,proof_scope='backend')


def test_actual_employee_browser_and_MCP_current_answer_and_denied_refresh(admin_url,sql_qualified_serving_v3,tmp_path,bound_tls,certificates):
 return _exercise_owned_answer_graph_v1(admin_url,sql_qualified_serving_v3,tmp_path,bound_tls,certificates,proof_scope='browser')
