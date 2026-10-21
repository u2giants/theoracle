#!/usr/bin/env python3
"""Invented authenticated browser -> opaque worker -> SDK -> current ledger proof.

Environment supplies loopback stores. No credential or source text is a command
argument. This is an engineering test, never private semantic/hosted admission.
"""
import asyncio,hashlib,json,os,secrets,signal,socket,subprocess,sys,tempfile,threading,time,tarfile,io
from pathlib import Path
from uuid import UUID,uuid4
from urllib.parse import urlparse,quote
from urllib.request import urlopen
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from oracle_brain.authz import appoint_owner,delegate
from oracle_brain.operating_model.authority_adapter import PostgresSources
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.source_receipts import EvidenceRef
from oracle_brain.operating_model.observations import create_observation
from oracle_brain.operating_model.findings import Finding
from oracle_brain.operating_model.workflows.process_model import WorkflowModel,Step,Support,Transition
from oracle_brain.operating_model.model import BusinessOperatingModel,ProcessRecord,BusinessRecord,Interface
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.sdk_projection import SDKProjection
from oracle_brain.operating_model.runtime import NoGeneration,SyntheticEmbedding,run_view
from oracle_brain.operating_model.cutover import activate,watermark
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.contracts import digest
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from dev.oracle2.legacy_database_fixture import owned_legacy_database,LegacyCleanupBlocked,stop_owned_process
from dev.oracle2.test_tls_bootstrap import postgres_uri
def verify_source_offer():
    directory=ROOT/'apps/web/.source-offer'
    data=json.loads((directory/'manifest.json').read_text())
    archive=(directory/'oracle-source.tar.gz').read_bytes()
    assert hashlib.sha256(archive).hexdigest()==data['archive_sha256']
    assert data['revision']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        files={entry.name:tar.extractfile(entry).read() for entry in tar.getmembers() if entry.name!='SOURCE_ARCHIVE_MANIFEST.json'}
    assert {name:hashlib.sha256(value).hexdigest() for name,value in files.items()}==data['files']
    assert all(not any(part in ('.env','.env.local','uploads','.ai','node_modules') for part in name.split('/')) for name in files)
verify_source_offer()

def main():
    with owned_legacy_database() as legacy:
        return _run(legacy.url)


def _run(admin):
    graph=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL']
    if any(urlparse(v).hostname not in {'127.0.0.1','localhost'} for v in (admin,graph)):raise PermissionError('owned loopback stores required')
    workspace,owner,actor,source,artifact,generation=(uuid4() for _ in range(6))
    with tempfile.TemporaryDirectory(prefix='oracle-workflow-browser-',dir=os.getenv('TMPDIR')) as tmp:
        private=Path(tmp);os.chmod(private,0o700);blobs=FileBlobStore(private/'blobs')
        with psycopg.connect(admin) as conn:
            for name in ('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql'):conn.execute((ROOT/'services/oracle-brain/sql'/name).read_text())
        key=Ed25519PrivateKey.generate();appointment=uuid4()
        os.environ['ORACLE2_OWNER_PUBLIC_KEY']=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
        message=f'oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}'.encode()
        appoint_owner(admin,workspace_id=workspace,owner_id=owner,appointed_by=uuid4(),appointment_id=appointment,owner_signature_hex=key.sign(message).hex())
        delegate(admin,workspace_id=workspace,grantor_id=owner,actor_id=actor,scope='review')
        delegate(admin,workspace_id=workspace,grantor_id=owner,actor_id=actor,scope='source-read:'+str(source))
        text='Intake sends packet to Review. Approval owner is missing.';seal=hashlib.sha256(text.encode()).hexdigest()
        provenance={'original_hash':seal,'content_hash':seal,'parser_identity':'a'*64,'content_type':'text/plain','evidence_kind':'native_text','page_count':1,'review_receipt':'b'*64}
        with psycopg.connect(admin) as conn:
            conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented.txt','text/plain','confirmed')",(source,workspace,actor))
            conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'Invented Intake','confirmed')",(uuid4(),source,workspace,actor))
            for index,kind,value in ((0,'original',text),(1,'original-metadata',json.dumps(provenance))):conn.execute('INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) VALUES(%s,%s,%s,%s,%s,%s,0,%s)',(uuid4(),source,workspace,index,kind,value,len(value)))
        export_source=uuid4();export_text='id,case,activity,time\nE1,C,Review,2026-01-01T00:00:00Z\n';export_seal=hashlib.sha256(export_text.encode()).hexdigest()
        delegate(admin,workspace_id=workspace,grantor_id=owner,actor_id=actor,scope='source-read:'+str(export_source))
        delegate(admin,workspace_id=workspace,grantor_id=owner,actor_id=actor,scope='event-import:intake')
        delegate(admin,workspace_id=workspace,grantor_id=owner,actor_id=actor,scope='finding-review:intake')
        export_provenance={**provenance,'original_hash':export_seal,'content_hash':export_seal}
        with psycopg.connect(admin) as conn:
            conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented-events.csv','text/csv','confirmed')",(export_source,workspace,actor))
            conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'Invented Events','confirmed')",(uuid4(),export_source,workspace,actor))
            for index,kind,value in ((0,'original',export_text),(1,'original-metadata',json.dumps(export_provenance))):
                conn.execute('INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) VALUES(%s,%s,%s,%s,%s,%s,0,%s)',(uuid4(),export_source,workspace,index,kind,value,len(value)))
        authority=PostgresSources(admin,synthetic=True);receipt=authority.current(workspace,source)
        second=uuid4();text2='Review receives packet from Intake.';seal2=hashlib.sha256(text2.encode()).hexdigest()
        delegate(admin,workspace_id=workspace,grantor_id=owner,actor_id=actor,scope='source-read:'+str(second))
        provenance2={**provenance,'original_hash':seal2,'content_hash':seal2}
        with psycopg.connect(admin) as conn:
            conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented-review.txt','text/plain','confirmed')",(second,workspace,actor))
            conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'Invented Review','confirmed')",(uuid4(),second,workspace,actor))
            for index,kind,value in ((0,'original',text2),(1,'original-metadata',json.dumps(provenance2))):conn.execute('INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) VALUES(%s,%s,%s,%s,%s,%s,0,%s)',(uuid4(),second,workspace,index,kind,value,len(value)))
        receipt2=authority.current(workspace,second)
        observation2=create_observation(receipt2,'receiving-packet','handoff','intake',text2,(EvidenceRef(ref=receipt2.ref,start=0,end=len(text2),quote=text2),))
        evidence=EvidenceRef(ref=receipt.ref,start=0,end=30,quote=text[:30])
        observed=create_observation(receipt,'explicit-route','handoff','intake',text[:30],(evidence,))
        finding=Finding(finding_id='missing-owner',workspace_id=workspace,source_refs=(receipt.ref,),scope='intake',process_id='intake',kind='missing_information',text='Approval owner is missing.',origin='source_reported',evidence_refs=(EvidenceRef(ref=receipt.ref,start=31,end=len(text),quote=text[31:]),))
        support=Support(observation_ids=(observed.observation_id,))
        workflow=WorkflowModel(workflow_id='Invented intake',version=1,workspace_id=workspace,process_id='intake',scope='intake',source_refs=(receipt.ref,),completeness='partial',coverage_digest='c'*64,steps=(Step(step_id='intake',label='Intake',kind='start',support=support),Step(step_id='review',label='Review',kind='end',support=support)),transitions=(Transition(transition_id='packet-handoff',from_id='intake',to_id='review',support=support),))
        model=BusinessOperatingModel(model_id=uuid4(),version=1,workspace_id=workspace,source_refs=(receipt.ref,receipt2.ref),declared_population='Two connected invented processes',processes=(ProcessRecord(process_id='intake',label='Intake',workflow_ids=(workflow.workflow_id,),scope='intake',source_ids=(source,),observation_ids=(observed.observation_id,),completeness='partial'),ProcessRecord(process_id='review',label='Review',scope='intake',source_ids=(second,),observation_ids=(observation2.observation_id,),completeness='partial')),objects=(BusinessRecord(object_id='packet',kind='artifact',label='packet',scope='intake',support=support),),interfaces=(Interface(interface_id='packet-interface',from_process='intake',to_process='review',artifact_id='packet',scope='intake',support=support,status='supported'),),assembly_decisions=(),workflows=(workflow,),finding_ids=(finding.finding_id,),completeness='partial')
        legacy=Finding(finding_id='legacy-gap',workspace_id=workspace,source_refs=(receipt.ref,),scope='intake',kind='missing_information',text='Unverified legacy licensor concern',origin='legacy_unverified',status='needs_evidence')
        payload={'source_refs':[receipt.ref.model_dump(mode='json'),receipt2.ref.model_dump(mode='json')],'observations':[observed.model_dump(mode='json'),observation2.model_dump(mode='json')],'findings':[finding.model_dump(mode='json'),legacy.model_dump(mode='json')],'workflows':[workflow.model_dump(mode='json')],'operating_models':[model.model_dump(mode='json')]}
        ledger=Ledger(admin,blobs,principal=actor,can_read=authority.can_read,current_source=authority.current)
        ledger.persist(workspace_id=workspace,artifact_id=artifact,version=1,kind='operating_model',payload=payload,refs=(receipt.ref,receipt2.ref),permission_digest='d'*64,compiler_digest='e'*64)
        from datetime import datetime
        from oracle_brain.operating_model.ingest.event_store import import_events
        from oracle_brain.operating_model.ingest.operational_export import Mapping
        from oracle_brain.operating_model.report_store import persist_report
        from oracle_brain.operating_model.consultant.process_analysis import Report
        from oracle_brain.operating_model.retrieval import QueryPlan
        from oracle_brain.operating_model.release_manifest import ReportReference
        event_manifest,event_log=import_events(ledger,authority.current(workspace,export_source),export_text.encode(),format='csv',
            mapping=Mapping(columns={'event_id':'id','case_id':'case','activity_id':'activity','timestamp':'time'},source_system='invented',process_id='intake',scope='intake',activity_map={'Review':'review'}),
            window_start=datetime.fromisoformat('2026-01-01T00:00:00+00:00'),window_end=datetime.fromisoformat('2026-01-02T00:00:00+00:00'),permission_digest='d'*64,compiler_digest='f'*64)
        def generate(role,inputs):
            if role=='planner':return {'operations':['describe_metrics']}
            if role=='analyst':return {'notes':'invented events only'}
            if role=='challenger':return {'supported':True}
            return Report(variant='measured',state='ready',model_artifact_hash=inputs['pack']['artifact_hash'],event_artifact_hash=inputs['event_artifact_hash'],measurements=inputs['metrics'],clauses=(),finding_ids=tuple(f['finding_id'] for f in inputs['pack']['findings']),actual_data_acceptance='synthetic',limitations=('Invented event fixture only.',)).model_dump(mode='json')
        preview=persist_report(ledger,workspace_id=workspace,model_id=artifact,model_version=1,report_id=uuid4(),report_version=1,
            plan=QueryPlan(view='process_local',process_ids=('intake',),question='invented measurements',max_bytes=131072,page=0,page_size=25),generate=generate,synthetic=True,permission_digest='d'*64,compiler_digest='f'*64,event_id=event_log.import_id,event_version=1)
        assert preview['state']=='ready' and preview['calls']==4
        async def build():
            projection=SDKProjection(graph,workspace_id=workspace,artifact_id=artifact,artifact_version=1,generation=generation,llm=NoGeneration(),embedder=SyntheticEmbedding(),dimensions=8)
            try:return await projection.build(ledger,workspace,artifact,1)
            finally:await projection.close()
        built=asyncio.run(build())
        with psycopg.connect(admin) as conn:mark=watermark(conn,workspace)
        manifest=ReleaseManifest(release_id=uuid4(),workspace_id=workspace,artifact_id=artifact,artifact_version=1,artifact_content_hash=digest(payload),runtime_digest='f'*64,permission_digest='d'*64,source_refs=(receipt.ref,receipt2.ref,authority.current(workspace,export_source).ref),report_refs=(ReportReference(artifact_id=UUID(preview['artifact_id']),version=1,content_hash=preview['content_hash']),),graph_generation=generation,graph_name=built['graph_name'],graph_record_digest=built['record_digest'],acceptance_state='synthetic',independent_review_hash='1'*64,documentary_gate_hash='2'*64,source_inventory_hash='3'*64,ledger_watermark=mark)
        # Synthetic test admission only; never a technical release approval.
        activate(admin,manifest,expected_generation=0,ledger=ledger,verify_projection=lambda m,p:None,runtime_digest='f'*64,synthetic=True,reviewed_release_hashes=frozenset({manifest.content_hash()}))
        role='operating_view_test_'+uuid4().hex;password=secrets.token_urlsafe(32)
        with psycopg.connect(admin) as conn:
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(role)))
            for table in ('appointments','sources','drafts','source_blocks','operating_release_selectors','operating_release_manifests','operating_model_change_log','artifact_manifests','artifact_invalidations','finding_events','artifact_dependencies','operating_model_source_receipts','document_observations','assembly_revisions','operational_imports'):
                conn.execute(sql.SQL('GRANT SELECT ON oracle2.{} TO {}').format(sql.Identifier(table),sql.Identifier(role)))
            conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON oracle2.operating_view_runs TO {}').format(sql.Identifier(role)))
            conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON oracle2.operating_action_runs TO {}').format(sql.Identifier(role)))
            for table in ('artifact_manifests','artifact_dependencies','operating_model_source_receipts','document_observations','assembly_revisions','operational_imports','outbox','finding_events'):
                conn.execute(sql.SQL('GRANT INSERT ON oracle2.{} TO {}').format(sql.Identifier(table),sql.Identifier(role)))

        parts=psycopg.conninfo.conninfo_to_dict(admin);parts.update(user=role,password=password)
        viewer=postgres_uri(psycopg.conninfo.make_conninfo(**parts),sslrootcert=parts['sslrootcert'])
        stopped=threading.Event();worker_errors=[];active_worker=[None];worker_lock=threading.Lock()
        worker_env={**os.environ,'ORACLE2_DATABASE_URL':viewer,'ORACLE2_OPERATING_GRAPH_URL':graph,'ORACLE2_OPERATING_BLOB_ROOT':str(blobs.root),'ORACLE2_OPERATING_SYNTHETIC':'1','ORACLE2_ENVIRONMENT':'synthetic'}
        def dispatch():
            while not stopped.wait(.15):
                with psycopg.connect(admin,connect_timeout=5) as conn:runs=conn.execute("SELECT run_id,workspace_id,operation FROM oracle2.operating_action_runs WHERE workspace_id=%s AND status='pending' UNION ALL SELECT run_id,workspace_id,'view' FROM oracle2.operating_view_runs WHERE workspace_id=%s AND status='pending'",(workspace,workspace)).fetchall()
                for run_id,run_workspace,operation in runs:
                    if stopped.is_set():break
                    try:
                        with worker_lock:
                            if stopped.is_set():break
                            process=subprocess.Popen([sys.executable,str(ROOT/'services/oracle-brain/oracle_brain/operating_model_cli.py'),json.dumps({'runId':str(run_id),'workspaceId':str(run_workspace),'operation':operation})],env=worker_env,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
                            active_worker[0]=process
                        with process:
                            try:
                                output,_=process.communicate(timeout=60)
                            finally:
                                stop_owned_process(process)
                                with worker_lock:active_worker[0]=None
                            if process.returncode or json.loads(output).get('state')!='completed':raise RuntimeError('fresh worker denied')
                    except Exception as problem:
                        worker_errors.append(type(problem).__name__)
                        with psycopg.connect(admin,connect_timeout=5) as conn:conn.execute("UPDATE oracle2.operating_view_runs SET status='error' WHERE run_id=%s",(run_id,))
        worker=threading.Thread(target=dispatch,daemon=True)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        token=secrets.token_urlsafe(32)
        env={**os.environ,'ORACLE2_DATABASE_URL':viewer,'ORACLE2_PILOT_ACTOR':str(actor),'ORACLE2_PILOT_WORKSPACE_ID':str(workspace),'ORACLE2_PILOT_TOKEN':token,'ORACLE2_OPERATING_SYNTHETIC':'1','ORACLE2_PREVIEW_URL':f'http://127.0.0.1:{port}','NEXT_PUBLIC_SUPABASE_URL':'https://example.supabase.co','NEXT_PUBLIC_SUPABASE_ANON_KEY':'synthetic','ORACLE2_WORKFLOW_SCREENSHOT':str(ROOT/'.ai/reviews/workflow-browser.png')}
        import base64
        env['ORACLE2_EVENT_FIXTURE']=json.dumps({'process_id':'intake','mapping':{'columns':{'event_id':'id','case_id':'case','activity_id':'activity','timestamp':'time'},'source_system':'invented','process_id':'intake','scope':'intake','activity_map':{'Review':'review'}},'raw_export_base64':base64.b64encode(export_text.encode()).decode(),'format':'csv','window_start':'2026-01-01T00:00:00+00:00','window_end':'2026-01-02T00:00:00+00:00','source_refs':[authority.current(workspace,export_source).ref.model_dump(mode='json')]})
        web=None
        try:
            worker.start()
            with (private/'web.log').open('w') as log:
                web=subprocess.Popen(['pnpm','--filter','@oracle/web','exec','next','dev','--hostname','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True)
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    if web.poll() is not None:raise RuntimeError('owned web process exited')
                    try:
                        with urlopen(env['ORACLE2_PREVIEW_URL']+'/consultant/operating-model',timeout=2) as response:
                            if response.status==200:break
                    except Exception:time.sleep(.3)
                else:raise TimeoutError('owned browser server readiness')
                result=subprocess.run(['pnpm','--filter','@oracle/web','exec','playwright','test','--config','playwright.oracle2.config.ts','tests/oracle2/workflow-browser.spec.ts'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=100)
                if result.returncode:print(result.stdout[-6000:]);raise RuntimeError('invented browser proof failed')
                if worker_errors:raise RuntimeError('view worker failed current-source SDK check')
            print(json.dumps({'success':True,'synthetic':True,'live_business_accepted':False,'worker_sdk_ledger_verified':True}))
        finally:
            stopped.set()
            with worker_lock:
                process=active_worker[0]
                stop_owned_process(process)
            if worker.ident is not None:worker.join(timeout=15)
            stop_owned_process(web)
            if worker.is_alive():raise LegacyCleanupBlocked('owned worker did not terminate')
            with psycopg.connect(admin) as conn:
                conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)));conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))

if __name__=='__main__':main()
