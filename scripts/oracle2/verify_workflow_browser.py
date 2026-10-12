#!/usr/bin/env python3
"""Invented authenticated browser -> opaque worker -> SDK -> current ledger proof.

Environment supplies loopback stores. No credential or source text is a command
argument. This is an engineering test, never private semantic/hosted admission.
"""
import asyncio,hashlib,json,os,secrets,signal,socket,subprocess,sys,tempfile,threading,time,tarfile,io
from pathlib import Path
from uuid import uuid4
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
from oracle_brain.operating_model.model import BusinessOperatingModel,ProcessRecord
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.sdk_projection import SDKProjection
from oracle_brain.operating_model.runtime import NoGeneration,SyntheticEmbedding,run_view
from oracle_brain.operating_model.cutover import activate,watermark
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.contracts import digest

ROOT=Path(__file__).resolve().parents[2]
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
    admin=os.environ['ORACLE2_TEST_ADMIN_URL'];graph=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL']
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
        authority=PostgresSources(admin);receipt=authority.current(workspace,source)
        evidence=EvidenceRef(ref=receipt.ref,start=0,end=30,quote=text[:30])
        observed=create_observation(receipt,'explicit-route','step','intake',text[:30],(evidence,))
        finding=Finding(finding_id='missing-owner',workspace_id=workspace,source_refs=(receipt.ref,),scope='intake',process_id='intake',kind='missing_information',text='Approval owner is missing.',origin='source_reported',evidence_refs=(EvidenceRef(ref=receipt.ref,start=31,end=len(text),quote=text[31:]),))
        support=Support(observation_ids=(observed.observation_id,))
        workflow=WorkflowModel(workflow_id='Invented intake',version=1,workspace_id=workspace,process_id='intake',scope='intake',source_refs=(receipt.ref,),completeness='partial',coverage_digest='c'*64,steps=(Step(step_id='intake',label='Intake',kind='start',support=support),Step(step_id='review',label='Review',kind='end',support=support)),transitions=(Transition(transition_id='packet-handoff',from_id='intake',to_id='review',support=support),))
        model=BusinessOperatingModel(model_id=uuid4(),version=1,workspace_id=workspace,source_refs=(receipt.ref,),declared_population='One invented intake process',processes=(ProcessRecord(process_id='intake',label='Intake',scope='intake',source_ids=(source,),observation_ids=(observed.observation_id,),completeness='partial'),),objects=(),interfaces=(),assembly_decisions=(),workflows=(workflow,),finding_ids=(finding.finding_id,),completeness='partial')
        payload={'source_refs':[receipt.ref.model_dump(mode='json')],'observations':[observed.model_dump(mode='json')],'findings':[finding.model_dump(mode='json')],'workflows':[workflow.model_dump(mode='json')],'operating_models':[model.model_dump(mode='json')]}
        ledger=Ledger(admin,blobs,principal=actor,can_read=authority.can_read,current_source=authority.current)
        ledger.persist(workspace_id=workspace,artifact_id=artifact,version=1,kind='operating_model',payload=payload,refs=(receipt.ref,),permission_digest='d'*64,compiler_digest='e'*64)
        async def build():
            projection=SDKProjection(graph,workspace_id=workspace,artifact_id=artifact,artifact_version=1,generation=generation,llm=NoGeneration(),embedder=SyntheticEmbedding(),dimensions=8)
            try:return await projection.build(ledger,workspace,artifact,1)
            finally:await projection.close()
        built=asyncio.run(build())
        with psycopg.connect(admin) as conn:mark=watermark(conn,workspace)
        manifest=ReleaseManifest(release_id=uuid4(),workspace_id=workspace,artifact_id=artifact,artifact_version=1,artifact_content_hash=digest(payload),runtime_digest='f'*64,permission_digest='d'*64,source_refs=(receipt.ref,),graph_generation=generation,graph_name=built['graph_name'],graph_record_digest=built['record_digest'],acceptance_state='synthetic',independent_review_hash='1'*64,documentary_gate_hash='2'*64,source_inventory_hash='3'*64,ledger_watermark=mark)
        # Synthetic test admission only; never a technical release approval.
        activate(admin,manifest,expected_generation=0,ledger=ledger,verify_projection=lambda m,p:None,runtime_digest='f'*64,synthetic=True,reviewed_release_hashes=frozenset({manifest.content_hash()}))
        role='operating_view_test_'+uuid4().hex;password=secrets.token_urlsafe(32)
        with psycopg.connect(admin) as conn:
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(role)))
            for table in ('appointments','sources','drafts','source_blocks','operating_release_selectors','operating_release_manifests','operating_model_change_log','artifact_manifests','artifact_invalidations'):
                conn.execute(sql.SQL('GRANT SELECT ON oracle2.{} TO {}').format(sql.Identifier(table),sql.Identifier(role)))
            conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON oracle2.operating_view_runs TO {}').format(sql.Identifier(role)))
        parts=psycopg.conninfo.conninfo_to_dict(admin);parts.update(user=role,password=password);viewer=f"postgresql://{quote(role)}:{quote(password)}@{parts['host']}:{parts.get('port','5432')}/{quote(parts['dbname'])}"
        stopped=threading.Event();worker_errors=[]
        worker_env={**os.environ,'ORACLE2_DATABASE_URL':viewer,'ORACLE2_OPERATING_GRAPH_URL':graph,'ORACLE2_OPERATING_BLOB_ROOT':str(blobs.root),'ORACLE2_OPERATING_SYNTHETIC':'1','ORACLE2_ENVIRONMENT':'synthetic'}
        def dispatch():
            while not stopped.wait(.15):
                with psycopg.connect(admin) as conn:runs=conn.execute("SELECT run_id FROM oracle2.operating_view_runs WHERE workspace_id=%s AND status='pending'",(workspace,)).fetchall()
                for (run_id,) in runs:
                    try:
                        completed=subprocess.run([sys.executable,str(ROOT/'services/oracle-brain/oracle_brain/operating_model_cli.py'),json.dumps({'runId':str(run_id),'workspaceId':str(workspace)})],env=worker_env,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
                        if completed.returncode or json.loads(completed.stdout).get('state')!='completed':raise RuntimeError('fresh worker denied')
                    except Exception as problem:
                        worker_errors.append(type(problem).__name__)
                        with psycopg.connect(admin) as conn:conn.execute("UPDATE oracle2.operating_view_runs SET status='error' WHERE run_id=%s",(run_id,))
        worker=threading.Thread(target=dispatch,daemon=True);worker.start()
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        token=secrets.token_urlsafe(32)
        env={**os.environ,'ORACLE2_DATABASE_URL':viewer,'ORACLE2_PILOT_ACTOR':str(actor),'ORACLE2_PILOT_WORKSPACE_ID':str(workspace),'ORACLE2_PILOT_TOKEN':token,'ORACLE2_OPERATING_SYNTHETIC':'1','ORACLE2_PREVIEW_URL':f'http://127.0.0.1:{port}','NEXT_PUBLIC_SUPABASE_URL':'https://example.supabase.co','NEXT_PUBLIC_SUPABASE_ANON_KEY':'synthetic','ORACLE2_WORKFLOW_SCREENSHOT':str(ROOT/'.ai/reviews/workflow-browser.png')}
        web=None
        try:
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
            stopped.set();worker.join(timeout=5)
            if web and web.poll() is None:os.killpg(web.pid,signal.SIGTERM);web.wait(timeout=10)
            with psycopg.connect(admin) as conn:
                conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)));conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))

if __name__=='__main__':main()
