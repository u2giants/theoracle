"""One fixed v2 invented Trigger job; externally sealed permission, no old replay.

No provider, issuer, arbitrary job, graph target or company route is exposed.
"""
import asyncio,base64,hashlib,json,os,re,sys,tempfile,time
from datetime import datetime,timezone
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode,unquote
from uuid import UUID
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from oracle_brain.hosting.synthetic_fixture import fixed_scenario,fixture,NATIVE_TRIGGER_V2_SCENARIO
from oracle_brain.operating_model.source_binding import SourceRoleBinding

SCENARIO=fixed_scenario(NATIVE_TRIGGER_V2_SCENARIO)
FILES={'database_url','database_ca','graph_url','graph_ca','graph_cert','graph_key'}
FIELDS={'schema_version','purpose','issued_at','expires_at','runtime_hash','review_hash','source_role_registry_hash','files'}
HASH=re.compile('[a-f0-9]{64}')
# Presence is forbidden even for empty values; task and Python enforce the same union.
FORBIDDEN_ENV=('ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'ZHIPU_API_KEY', 'AZURE_OPENAI_API_KEY', 'ORACLE2_NATIVE_TRIGGER_BUNDLE', 'ORACLE2_NATIVE_TRIGGER_BUNDLE_SHA256', 'ORACLE2_PREVIEW_ADMIN_URL', 'ORACLE_NATIVE_ADMIN_URL', 'DATABASE_URL', 'ORACLE2_DATABASE_URL', 'TRIGGER_ACCESS_TOKEN', 'ORACLE2_PROJECTOR_GRAPH_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ORACLE2_CONFIRMED_GRAPH_URL', 'ORACLE2_PROJECTION_SIGNING_KEY', 'ORACLE2_CHECKPOINT_DATABASE_URL', 'ORACLE_NATIVE_GRAPH_PROJECTOR_PASSWORD', 'ORACLE_NATIVE_PROJECTOR_DATABASE_URL', 'ORACLE2_PROJECTOR_DATABASE_URL', 'TRIGGER_PAT')


@dataclass(frozen=True)
class NativeSourceRoleBindingV2(SourceRoleBinding):
    expected_login:str='oracle_native_v2_executor'

    def check(self,connection):
        require(self.expected_login in ('oracle_native_v2_executor','oracle_native_v2_projector')
            and connection.info.dbname=='oracle_native_proof_v2','fixed new native role/database required')
        row=connection.execute("SELECT session_user,current_user,rolcanlogin,rolinherit,rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=session_user").fetchone()
        require(row==(self.expected_login,'oracle_native_v2_documentary_executor',True,False,False,False,False,False,False),
            'native source role privileges changed')
        memberships=connection.execute("WITH RECURSIVE members(oid) AS (SELECT roleid FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=session_user) UNION SELECT m.roleid FROM pg_auth_members m JOIN members x ON m.member=x.oid) SELECT rolname FROM pg_roles WHERE oid IN (SELECT oid FROM members) ORDER BY rolname").fetchall()
        require(memberships==[('oracle_native_v2_documentary_executor',)],'native source role memberships changed')
        admin=connection.execute("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=session_user) AND admin_option").fetchone()
        require(admin==(0,),'native source role admin option changed')
        group=connection.execute("SELECT rolcanlogin,rolinherit,rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        require(group==(False,False,False,False,False,False,False),'native effective group privileges changed')
        super().check(connection)


def native_python_digest():
    """Same immutable Python population before sync and inside Trigger image."""
    package=Path(__file__).resolve().parents[1]
    entries={str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package.rglob('*.py')) if p.is_file() and not p.is_symlink()}
    return hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def require(value,message):
    if not value:raise PermissionError(message)


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'duplicate sealed field');result[key]=value
    return result


def decode_bundle(raw,seal,now=None):
    now=time.time() if now is None else now
    require(type(raw) is bytes and len(raw)<=131072 and type(seal) is str and HASH.fullmatch(seal)
        and hashlib.sha256(raw).hexdigest()==seal,'externally sealed native bundle required')
    body=json.loads(raw,object_pairs_hook=unique)
    require(type(body) is dict and set(body)==FIELDS and type(body['schema_version']) is int and body['schema_version']==1
        and body['purpose']==NATIVE_TRIGGER_V2_SCENARIO,'fixed new invented purpose required')
    require(type(body['issued_at']) is int and type(body['expires_at']) is int
        and body['issued_at']<=now<body['expires_at']==body['issued_at']+3600,'new native permission expired or horizon changed')
    require(all(type(body[k]) is str and HASH.fullmatch(body[k]) for k in ('runtime_hash','review_hash','source_role_registry_hash')),
        'exact native source, review and role pins required')
    require(type(body['files']) is dict and set(body['files'])==FILES,'exact private credential population required')
    decoded={}
    for name,value in body['files'].items():
        require(type(value) is str and len(value)<=40000,'bounded credential file required')
        decoded[name]=base64.b64decode(value,validate=True)
        require(0<len(decoded[name])<=30000,'bounded nonempty credential file required')
    return body,decoded


def validate_payload(payload):
    require(type(payload) is dict and set(payload)=={'jobId','workspaceId'}
        and payload['jobId']==str(SCENARIO.run) and payload['workspaceId']==str(SCENARIO.workspace),
        'only the newly authorized opaque native job is available')


def database_url(raw,ca_path,*,role='executor'):
    require(role in ('executor','projector'),'fixed native SQL role required')
    parsed=urlsplit(raw.decode().strip())
    require(parsed.scheme=='postgresql' and parsed.hostname=='aws-0-us-east-1.pooler.supabase.com'
        and parsed.port==5432 and parsed.path=='/oracle_native_proof_v2'
        and unquote(parsed.username or '')=='oracle_native_v2_'+role+'.wfdrklofsczspazshaib'
        and bool(parsed.password) and not parsed.fragment and not parsed.query,
        'exact new isolated Oracle database and executor identity required')
    return urlunsplit(parsed._replace(query=urlencode({'sslmode':'verify-full','sslrootcert':str(ca_path),'connect_timeout':'5'})))


def tls_config(raw,paths,*,projector=False):
    require(type(projector) is bool,'fixed v2 graph role selector required')
    from graphrag_sdk import ConnectionConfig
    parsed=urlsplit(raw.decode().strip())
    expected='oracle_native_proof_projector_v2' if projector else 'oracle_native_proof_executor_v2'
    require(parsed.scheme=='rediss' and parsed.hostname=='oracle-graph.designflow.app' and parsed.port==16391
        and parsed.username==expected and bool(parsed.password) and parsed.path in ('','/','/0') and not parsed.query and not parsed.fragment,
        'exact current mTLS candidate graph identity required')
    graph=f'oracle_operating_model_v1_{SCENARIO.workspace.hex}_{SCENARIO.artifact.hex}_1_{SCENARIO.generation.hex}'
    return parsed.geturl(),ConnectionConfig(host=parsed.hostname,port=parsed.port,username=expected,
        password=unquote(parsed.password),graph_name=graph,max_connections=2,retry_count=1,retry_delay=0,
        pool_timeout=5,query_timeout_ms=30000,ssl=True,ssl_cert_reqs='required',ssl_check_hostname=True,
        ssl_ca_certs=str(paths['graph_ca']),ssl_certfile=str(paths['graph_cert']),ssl_keyfile=str(paths['graph_key']))


async def execute(payload,body,files,root,trigger_run):
    validate_payload(payload)
    require(body['runtime_hash']==native_python_digest(),'native Python population differs from reviewed runtime')
    require(type(trigger_run) is str and re.fullmatch(r'run_[A-Za-z0-9]{8,100}',trigger_run),'actual opaque Trigger attempt identity required')
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import load_pem_private_key,Encoding,PublicFormat
    from cryptography.x509.oid import ExtendedKeyUsageOID
    cert=x509.load_pem_x509_certificate(files['graph_cert']);now=datetime.now(timezone.utc)
    key=load_pem_private_key(files['graph_key'],password=None)
    require(cert.not_valid_before_utc<=now<cert.not_valid_after_utc
        and ExtendedKeyUsageOID.CLIENT_AUTH in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        and cert.public_key().public_bytes(Encoding.DER,PublicFormat.SubjectPublicKeyInfo)==key.public_key().public_bytes(Encoding.DER,PublicFormat.SubjectPublicKeyInfo),
        'current matching native client certificate required')
    paths={}
    for name,value in files.items():
        path=root/name;path.write_bytes(value);path.chmod(0o600);paths[name]=path
    url=database_url(files['database_url'],paths['database_ca'])
    graph_url,config=tls_config(files['graph_url'],paths)
    from oracle_brain.operating_model.authority_adapter import PostgresSources
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.ledger import Ledger
    from oracle_brain.operating_model.sdk_projection import NativeInventedTLSProjectionV2
    from oracle_brain.operating_model.view_jobs import execute_view
    from oracle_brain.operating_model.contracts import canonical_bytes
    from oracle_brain.hosting.job_authority import PostgresJobAuthority
    import psycopg
    _,_,content,manifest,release=fixture(body['runtime_hash'],body['review_hash'],NATIVE_TRIGGER_V2_SCENARIO)
    binding=NativeSourceRoleBindingV2(body['runtime_hash'],body['source_role_registry_hash'],synthetic=True)
    binding.check_url(url)
    authority=PostgresJobAuthority(url,runtime_hash=body['runtime_hash'],synthetic=True,allowed_release_hashes=frozenset((release.content_hash(),)))
    row=authority.resolve(str(SCENARIO.run),body['runtime_hash'],release.documentary_gate_hash)
    require(row['workspace_id']==str(SCENARIO.workspace) and row['expires_at']==body['expires_at'],'actual current native permission differs')
    # Durable SQL claim commits BEFORE any graph work. A failed attempt is spent.
    with psycopg.connect(url) as conn:
        conn.execute('SELECT oracle2.native_trigger_claim(%s,%s)',(SCENARIO.run,trigger_run))
    authority(row);binding.check_url(url)
    blobs=FileBlobStore(root/'blobs');blob_key,blob_hash=blobs.put(SCENARIO.workspace,content)
    require(blob_hash==manifest.content_hash and blob_key==manifest.private_object_key,'fixed invented blob differs')
    sources=PostgresSources(url,source_binding=binding,synthetic=True)
    ledger=Ledger(url,blobs,principal=SCENARIO.actor,can_read=sources.can_read,current_source=sources.current)
    projection=NativeInventedTLSProjectionV2(graph_url,connection_config=config,read_only=True)
    try:
        await projection.verify(content)
        result=await execute_view(url,SCENARIO.run,ledger=ledger,projection=projection,synthetic=True)
        require(result=={'state':'completed','run_id':str(SCENARIO.run)},'native completion differs')
        binding.check_url(url)
        authority.resolve_result(str(SCENARIO.run),body['runtime_hash'],release.documentary_gate_hash)
        require(time.time()<body['expires_at'],'native permission expired before completion metadata')
        with psycopg.connect(url) as conn:
            saved=conn.execute('SELECT pack FROM oracle2.operating_view_runs WHERE run_id=%s AND status=\'completed\' AND expires_at>clock_timestamp()',(SCENARIO.run,)).fetchone()
        require(saved and type(saved[0]) is dict,'canonical native completion unavailable')
        pack=canonical_bytes(saved[0]);require(len(pack)<=131072,'native result too large')
        return {'schema_version':1,'state':'completed','job_id':str(SCENARIO.run),'workspace_id':str(SCENARIO.workspace),
            'runtime_hash':body['runtime_hash'],'release_hash':release.content_hash(),'artifact_hash':manifest.content_hash,
            'result_sha256':hashlib.sha256(pack).hexdigest(),'sdk_version':'1.4.0','graph_name':projection.graph_name,
            'expires_at':body['expires_at']}
    finally:await projection.close()


def main():
    try:
        require(not any(k in os.environ for k in FORBIDDEN_ENV),'native executor has forbidden credentials')
        payload=json.loads(sys.argv[1],object_pairs_hook=unique);validate_payload(payload)
        raw=os.environ['ORACLE2_NATIVE_TRIGGER_V2_BUNDLE'].encode();body,files=decode_bundle(raw,os.environ['ORACLE2_NATIVE_TRIGGER_V2_BUNDLE_SHA256'])
        with tempfile.TemporaryDirectory(prefix='oracle-native-trigger-') as directory:
            result=asyncio.run(asyncio.wait_for(execute(payload,body,files,Path(directory),sys.argv[2]),timeout=115))
        print(json.dumps(result,separators=(',',':')))
    except BaseException:
        # No credential-bearing exception or source output crosses Trigger logs.
        print('{"state":"denied"}');raise SystemExit(1)

if __name__=='__main__':main()
