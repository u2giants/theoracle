"""Actual isolated TLS/SCRAM metadata LOGIN/source-session authority proof."""
import base64,hashlib,hmac,json,os,secrets,subprocess
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo
import pytest
from oracle_brain.hosting.synthetic_fixture import fixture,fixed_scenario,FORWARD_SCENARIO
from oracle_brain.hosting.synthetic_seed import compile_seed
from oracle_brain.operating_model.contracts import canonical_bytes


def test_real_native_metadata_login_source_read_session(tmp_path):
    admin=os.environ.get('ORACLE2_TEST_ADMIN_URL');assert admin,'real isolated PostgreSQL fixture required'
    dbparams=conninfo_to_dict(admin);assert dbparams['host']=='127.0.0.1'
    namespace=uuid4().hex;database='oracle_operating_model_test_'+namespace
    roles={kind:'oracle_native_'+kind+'_'+namespace for kind in ('gateway','executor','projector','unrelated')}
    password=secrets.token_urlsafe(24)
    salt=secrets.token_bytes(16);salted=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,4096)
    enc=lambda b:base64.b64encode(b).decode()
    verifier='SCRAM-SHA-256$4096:'+enc(salt)+'$'+enc(hashlib.sha256(hmac.digest(salted,b'Client Key','sha256')).digest())+':'+enc(hmac.digest(salted,b'Server Key','sha256'))
    scenario=fixed_scenario(FORWARD_SCENARIO);expires=datetime.now(timezone.utc)+timedelta(hours=1)
    params={'runtime_hash':'a'*64,'source_role_registry_hash':'b'*64,'review_hash':'c'*64,'expires_at':expires.isoformat(),
      'synthetic_scenario':scenario.scenario_id,'synthetic_scenario_seal':scenario.seal(),**{kind+'_scram':verifier for kind in ('gateway','executor','projector')}}
    seed,_,payload,release=compile_seed(params)
    for kind in ('gateway','executor','projector'):seed=seed.replace('oracle_synthetic_'+kind,roles[kind])
    with psycopg.connect(admin,autocommit=True) as connection:
        assert connection.pgconn.ssl_in_use
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    localadmin=make_conninfo(**{**dbparams,'dbname':database})
    root=Path(__file__).resolve().parents[3]
    try:
        with psycopg.connect(localadmin,autocommit=True) as connection:
            for name in ('001_foundation','002_pilot','004_workflow_integrity','006_hosting_gateway_authority','007_hosting_candidate_permissions','008_hosting_runtime_permissions','009_hosting_result_permissions','010_hosting_job_permissions'):
                connection.execute((Path(__file__).parents[1]/'sql'/f'{name}.sql').read_text())
            connection.execute(seed)
            connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}').format(sql.Identifier(roles['unrelated']),sql.Literal(password)))
        def pin(name,data):
            path=tmp_path/name;path.write_bytes(data);path.chmod(0o600)
            return {'path':str(path),'sha256':hashlib.sha256(data).hexdigest()}
        ca=pin('database-ca',Path(dbparams['sslrootcert']).read_bytes())
        def url(user):
            from urllib.parse import quote
            return 'postgresql://'+quote(user)+':'+quote(password)+'@127.0.0.1:'+dbparams['port']+'/'+database+'?sslmode=verify-full&sslrootcert='+str(tmp_path/'database-ca')
        login=pin('metadata-login',url(roles['gateway']).encode());other=pin('unrelated-login',url(roles['unrelated']).encode())
        # Existing fixture issuer creates a public test identity, never production
        # authority, company credentials or a minted pilot grant.
        def openssl(*args):subprocess.run(['openssl',*args],cwd=tmp_path,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.pem','-days','1','-subj','/CN=Public invented native fixture','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign')
        openssl('req','-newkey','rsa:2048','-nodes','-keyout','worker.key','-out','worker.csr','-subj','/CN=Public invented worker')
        (tmp_path/'worker.ext').write_text('subjectAltName=URI:'+scenario.worker_uri+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=clientAuth\n')
        openssl('x509','-req','-in','worker.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial','-out','worker.pem','-days','1','-extfile','worker.ext')
        cert=pin('client.crt',(tmp_path/'worker.pem').read_bytes());key=pin('client.key',(tmp_path/'worker.key').read_bytes());serverca=pin('server-ca',(tmp_path/'ca.pem').read_bytes());hmacpin=pin('hmac',b'public-invented-fixed-key-'*3)
        settings={'schema_version':1,'purpose':'public-invented-native-browser','namespace':'invented-native-source-role','hostname':'gateway','origin':'https://gateway:8443',
          'actor_id':str(scenario.actor),'workspace_id':str(scenario.workspace),'job_id':str(scenario.run),'runtime_hash':params['runtime_hash'],
          'admission_hash':release.documentary_gate_hash,'release_hash':release.content_hash(),'permission_hash':release.permission_digest,'worker_uri':scenario.worker_uri,
          'source_authority_expires_at':int(expires.timestamp()),'worker_permit_expires_at':int(expires.timestamp()),'job_expires_at':int(expires.timestamp()),
          'source_refs':payload['source_refs'],'metadata_login':roles['gateway'],'metadata_role':'oracle2_gateway_metadata','database_url':login,'database_ca':ca,
          'client_cert':cert,'client_key':key,'server_ca':serverca,'hmac_key':hmacpin}
        context=pin('context.json',canonical_bytes({'settings':settings,'admin_url':url(dbparams['user']),'unrelated_login':roles['unrelated'],'unrelated_url':other}))
        # Native admin is the fixture's existing admin credential; no printed URL.
        data=json.loads(Path(context['path']).read_bytes());data['admin_url']=localadmin
        # postgres.js takes URI; construct correct fixture admin URI locally.
        from urllib.parse import quote
        data['admin_url']='postgresql://'+quote(dbparams['user'])+':'+quote(dbparams.get('password',''))+'@127.0.0.1:'+dbparams['port']+'/'+database+'?sslmode=verify-full&sslrootcert='+str(tmp_path/'database-ca')
        Path(context['path']).write_bytes(canonical_bytes(data));Path(context['path']).chmod(0o600)
        environment={**os.environ,'ORACLE_NATIVE_BROWSER_TEST_CONTEXT':context['path']}
        log=tmp_path/'native-postgres.log'
        with log.open('w') as stream:
            result=subprocess.run(['pnpm','--dir',str(root/'apps/web'),'exec','tsx','--tsconfig','tsconfig.json','lib/__verify__/native-browser-postgres.ts'],cwd=root,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=60)
        assert result.returncode==0,'real native PostgreSQL/source session verification failed; protected fixture log retained'
        assert '9 passed' in log.read_text()
    finally:
        with psycopg.connect(admin,autocommit=True) as connection:
            connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
            for role in roles.values():connection.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
