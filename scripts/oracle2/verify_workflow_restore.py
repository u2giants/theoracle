"""Fresh synthetic Postgres/blob restore and actual SDK rebuild; no company acceptance."""
import asyncio,hashlib,json,os,shutil,subprocess
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from graphrag_sdk.core.providers import Embedder,LLMInterface
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.sdk_projection import SDKProjection
from oracle_brain.operating_model.source_receipts import SourceReceipt,SourceRef,EvidenceRef
from oracle_brain.operating_model.observations import create_observation

ROOT=Path(__file__).resolve().parents[2]
class NoCall(LLMInterface):
    def __init__(self):super().__init__('synthetic-no-call',max_concurrency=1)
    def invoke(self,*args,**kwargs):raise AssertionError('restore attempted generation')
class FixedEmbedder(Embedder):
    model_name='synthetic-fixed-8'
    def embed_query(self,*args,**kwargs):return [1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]

def verify(admin_url,scratch,container,graph_url):
    parts=psycopg.conninfo.conninfo_to_dict(admin_url)
    if parts.get('host') not in {'127.0.0.1','localhost'}:raise PermissionError('owned synthetic loopback target required')
    inspected=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
    if inspected['Config']['Labels'].get('oracle.operating.synthetic')!='true':raise PermissionError('unowned restore container')
    bindings=inspected['NetworkSettings']['Ports'].get('5432/tcp',[])
    if not any(b['HostIp']=='127.0.0.1' and b['HostPort']==parts.get('port') for b in bindings):raise PermissionError('restore target does not match owned container')
    scratch.mkdir(parents=True,exist_ok=True);scratch.chmod(0o700)
    names=['oracle_operating_model_test_'+uuid4().hex for _ in range(2)];created=[]
    urls=[psycopg.conninfo.make_conninfo(**{**parts,'dbname':n}) for n in names]
    def native(program,name,*,dump=None):
        env={**os.environ,'PGDATABASE':name,'PGUSER':parts.get('user','postgres'),'PGPASSWORD':parts.get('password','')}
        cmd=['docker','exec','-i','--env','PGDATABASE','--env','PGUSER','--env','PGPASSWORD',container,program]
        if program=='pg_dump':cmd+=['--format=custom','--no-owner','--no-acl']
        else:cmd+=['--exit-on-error','--no-owner','--no-acl','--dbname',name]
        with dump.open('wb' if program=='pg_dump' else 'rb') as stream:
            result=subprocess.run(cmd,env=env,stdout=stream if program=='pg_dump' else subprocess.PIPE,stdin=stream if program!='pg_dump' else subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=60)
        if result.returncode:raise RuntimeError('isolated database backup/restore failed; protected target not logged')
        dump.chmod(0o600)
    try:
        with psycopg.connect(admin_url,autocommit=True) as conn:
            for name in names:conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)));created.append(name)
        with psycopg.connect(urls[0]) as conn:
            for migration in ('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql'):conn.execute((ROOT/'services/oracle-brain/sql'/migration).read_text())
        workspace,source,artifact=uuid4(),uuid4(),uuid4();text='Synthetic intake sends the packet.';seal=hashlib.sha256(text.encode()).hexdigest()
        ref=SourceRef(workspace_id=workspace,source_id=source,revision=1,original_sha256=seal,reading_sha256=seal,parser_id='synthetic-restore')
        receipt=SourceReceipt(ref=ref,reading=text,display_revision='r1')
        observation=create_observation(receipt,'intake','process','invented',text,(EvidenceRef(ref=ref,start=0,end=len(text),quote=text),))
        payload={'source_refs':[ref.model_dump(mode='json')],'observations':[observation.model_dump(mode='json')],'findings':[]}
        live=FileBlobStore(scratch/'live-blobs');ledger=Ledger(urls[0],live,principal=workspace,can_read=lambda *_:True,current_source=lambda *_:receipt)
        manifest=ledger.persist(workspace_id=workspace,artifact_id=artifact,version=1,kind='extraction',payload=payload,refs=(ref,),permission_digest='a'*64,compiler_digest='b'*64)
        backup=scratch/'backup';backup.mkdir(mode=0o700);shutil.copytree(scratch/'live-blobs',backup/'blobs')
        original_files={str(p.relative_to(backup/'blobs')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (backup/'blobs').rglob('*') if p.is_file()}
        reading_file=backup/'source-receipt.json';reading_file.write_text(receipt.model_dump_json());reading_file.chmod(0o600)
        dump=backup/'ledger.dump';native('pg_dump',names[0],dump=dump);native('pg_restore',names[1],dump=dump)
        # Prove restored reads cannot accidentally use the original database or blob root.
        with psycopg.connect(admin_url,autocommit=True) as conn:conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(names[0])))
        created.remove(names[0]);shutil.rmtree(scratch/'live-blobs')
        restored_receipt=SourceReceipt.model_validate_json(reading_file.read_text());restored=Ledger(urls[1],FileBlobStore(backup/'blobs'),principal=workspace,can_read=lambda *_:True,current_source=lambda *_:restored_receipt)
        if restored.read(workspace,artifact,1)!=payload:raise ValueError('restored payload differs')
        if original_files!={str(p.relative_to(backup/'blobs')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (backup/'blobs').rglob('*') if p.is_file()}:raise ValueError('restored blob checksum differs')
        async def project():
            generation=uuid4()
            def fresh():return SDKProjection(graph_url,workspace_id=workspace,artifact_id=artifact,artifact_version=1,generation=generation,llm=NoCall(),embedder=FixedEmbedder(),dimensions=8)
            first=fresh()
            try:built=await first.build(restored,workspace,artifact,1)
            finally:await first.close()
            second=fresh()
            try:
                if await second.load(restored,workspace,artifact,1)!=payload:raise ValueError('restored SDK reload differs')
            finally:await second.close()
            return built['graph_name']
        graph_name=asyncio.run(project())
        return {'passed':True,'synthetic':True,'business_accepted':False,'fresh_database_restored':True,'source_database_removed':True,'blob_checksums_verified':len(original_files),'sdk_rebuilt_reloaded':True,'graph_namespace':graph_name,'artifact_hash':manifest.content_hash,'dump_sha256':hashlib.sha256(dump.read_bytes()).hexdigest()}
    finally:
        with psycopg.connect(admin_url,autocommit=True) as conn:
            for name in created:
                conn.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s',(name,))
                conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
if __name__=='__main__':
    print(json.dumps(verify(os.environ['ORACLE2_TEST_ADMIN_URL'],Path(os.environ['ORACLE2_RESTORE_SCRATCH']),os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL']),sort_keys=True))
