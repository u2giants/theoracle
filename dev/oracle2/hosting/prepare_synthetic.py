"""Protected synthetic-only assets. No existing deployment or credentials used."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import textwrap
import sys
import hmac
import base64
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID

POSTGRES='postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297'
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'services/oracle-brain'))
from oracle_brain.hosting.synthetic_fixture import fixture,WORKSPACE,ACTOR
from oracle_brain.hosting.synthetic_seed import compile_seed

FALKOR='falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d'

def write(path,data,uid=10001):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.write_bytes(data if isinstance(data,bytes) else data.encode())
    path.chmod(0o600)
    if os.geteuid()==0:os.chown(path,uid,uid)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--runtime-hash',required=True)
    parser.add_argument('--release-hash',action='append')
    parser.add_argument('--review-hash',required=True)
    parser.add_argument('--synthetic',required=True,action='store_true')
    args=parser.parse_args(argv)
    if not re.fullmatch(r'(?:sha256:|ghcr\.io/u2giants/theoracle-native@sha256:)[a-f0-9]{64}',args.image):raise ValueError('immutable reviewed image required')
    if any(not re.fullmatch('[a-f0-9]{64}',x) for x in [args.runtime_hash,args.review_hash,*(args.release_hash or [])]):raise ValueError('exact hashes required')
    # Certificate issuer must execute inside an explicitly networkless container.
    # A host process or container with a routed network cannot issue this fixture.
    interfaces={line.split(':',1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]}
    if interfaces!={'lo'}:raise PermissionError('networkless certificate issuer required')
    _,_,fixture_payload,fixture_manifest,fixture_release=fixture(args.runtime_hash,args.review_hash)
    if args.release_hash and args.release_hash!=[fixture_release.content_hash()]:raise PermissionError('fixed invented release required')
    args.release_hash=[fixture_release.content_hash()]
    root=Path(args.directory)
    if root.exists():raise FileExistsError('new synthetic directory required')
    root.mkdir(parents=True,mode=0o700)
    for name,uid in [('gateway',10001),('executor',10001),('projector',10001),('worker',os.getuid()),('ledger',70),('candidate',999),('confirmed',999),('candidate-data',999),('confirmed-data',999),('spool',10001),('blobs',10001),('init',70)]:
        folder=root/name;folder.mkdir(mode=0o700)
        if os.geteuid()==0:os.chown(folder,uid,uid)
    now=datetime.now(timezone.utc)
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Oracle invented synthetic CA')])
    ca=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=2))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,encipher_only=None,decipher_only=None),critical=True)
        .sign(ca_key,hashes.SHA256()))
    ca_bytes=ca.public_bytes(serialization.Encoding.PEM)
    for folder,host,uri,uid in [('ledger','ledger',None,70),('gateway','gateway',None,10001),('worker',None,'spiffe://oracle/synthetic-worker',os.getuid())]:
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,host or 'invented worker')])
        san=x509.DNSName(host) if host else x509.UniformResourceIdentifier(uri)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=2))
            .add_extension(x509.SubjectAlternativeName([san]),critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=True,data_encipherment=False,key_agreement=False,key_cert_sign=False,crl_sign=False,encipher_only=None,decipher_only=None),critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if host else ExtendedKeyUsageOID.CLIENT_AUTH]),critical=False)
            .sign(ca_key,hashes.SHA256()))
        write(root/folder/'server.crt',cert.public_bytes(serialization.Encoding.PEM),uid)
        write(root/folder/'server.key',key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),uid)
        write(root/folder/'ca.crt',ca_bytes,uid)
    write(root/'executor'/'ca.crt',ca_bytes)
    write(root/'projector'/'ca.crt',ca_bytes)
    gateway_password,executor_password,projector_password,admin_password=(secrets.token_hex(32) for _ in range(4))
    write(root/'ledger'/'admin-password',admin_password,70)
    hmac_key=secrets.token_bytes(48)
    write(root/'gateway'/'hmac-key',hmac_key);write(root/'worker'/'hmac-key',hmac_key,os.getuid())
    for folder,user,password in [('gateway','oracle_synthetic_gateway',gateway_password),('executor','oracle_synthetic_executor',executor_password),('projector','oracle_synthetic_projector',projector_password)]:
        url=f'postgresql://{user}:{password}@ledger:5432/oracle_synthetic?sslmode=verify-full&sslrootcert=/run/oracle-auth/ca.crt'
        write(root/folder/'database-url',url)
    # No provider key is issued. Broker startup remains admission-gated.
    hba='local all oracle_bootstrap trust\nlocal all all reject\nhostnossl all all all reject\n'
    for login in ('oracle_synthetic_gateway','oracle_synthetic_executor','oracle_synthetic_projector'):
        for cidr in ('172.30.41.0/24','fd42:6f72:6163:41::/64'):
            hba+=f'hostssl oracle_synthetic {login} {cidr} scram-sha-256\n'
    hba+='host all all all reject\n'
    write(root/'ledger'/'pg_hba.conf',hba,70)
    sqlroot=Path(__file__).resolve().parents[3]/'services/oracle-brain/sql'
    for index,name in enumerate(('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql','006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql','008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql')):
        write(root/'init'/f'{index+1:02d}-{name}',(sqlroot/name).read_bytes(),70)
    source_registry={'schema':'oracle-public-invented-role-admission/v1','runtime_hash':args.runtime_hash,'role_names':['oracle_synthetic_executor','oracle_synthetic_projector'],
                     'workspace_id':str(WORKSPACE),'principal_id':str(ACTOR),'source_refs':fixture_payload['source_refs'],'expires_at':(now+timedelta(hours=1)).isoformat()}
    source_registry_hash=hashlib.sha256(json.dumps(source_registry,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def scram(password):
        salt=secrets.token_bytes(16);salted=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,4096)
        stored=hashlib.sha256(hmac.new(salted,b'Client Key',hashlib.sha256).digest()).digest()
        server=hmac.new(salted,b'Server Key',hashlib.sha256).digest()
        enc=lambda b:base64.b64encode(b).decode()
        return 'SCRAM-SHA-256$4096:'+enc(salt)+'$'+enc(stored)+':'+enc(server)
    parameters={'runtime_hash':args.runtime_hash,'source_role_registry_hash':source_registry_hash,'review_hash':args.review_hash,
                'expires_at':source_registry['expires_at'],'gateway_scram':scram(gateway_password),'executor_scram':scram(executor_password),'projector_scram':scram(projector_password)}
    seed,_,_,_=compile_seed(parameters)
    write(root/'init'/'90-public-invented-seed.sql',seed,70)
    write(root/'init'/'00-empty-owned-preflight.sql',"DO $$ BEGIN IF current_database()<>'oracle_synthetic' OR current_user<>'oracle_bootstrap' OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' AND c.relkind IN ('r','p','v','m','S')) THEN RAISE EXCEPTION 'new empty owned synthetic ledger required'; END IF; END $$;\n",70)
    write(root/'projector'/'synthetic-review-hash',args.review_hash)
    write(root/'source-role-registry.json',json.dumps(source_registry,sort_keys=True,separators=(',',':')),os.getuid())
    # The graph password is only synthetic; native SDK executes inside isolated
    # candidate network. TLS SDK support requires its own qualified receipt.
    graph_password=secrets.token_hex(32);projector_graph_password=secrets.token_hex(32)
    graph=fixture_release.graph_name
    if not re.fullmatch('[A-Za-z0-9_-]+',graph):raise PermissionError('fixed graph namespace required')
    candidate_config=(f'bind 0.0.0.0\nport 6379\nprotected-mode yes\ndir /var/lib/falkordb/data\n'
      f'user default off\nuser oracle_executor on >{graph_password} ~{graph} +graph.ro_query +ping +hello +info|server\n'
      f'user oracle_projector on >{projector_graph_password} ~{graph} +graph.query +graph.ro_query +ping +hello +info|server\n')
    write(root/'candidate'/'server.conf',candidate_config,999)
    write(root/'confirmed'/'server.conf','bind 0.0.0.0\nport 6379\nprotected-mode yes\nuser default off\ndir /var/lib/falkordb/data\n',999)
    write(root/'executor'/'graph-url',f'redis://oracle_executor:{graph_password}@candidate:6379')
    write(root/'projector'/'graph-url',f'redis://oracle_projector:{projector_graph_password}@candidate:6379')
    registry={'worker_uri':'spiffe://oracle/synthetic-worker','runtime_hash':args.runtime_hash,'active':True,
              'expires_at':int((now+timedelta(hours=1)).timestamp()),'allowed_release_hashes':args.release_hash}
    canonical=json.dumps(registry,sort_keys=True,separators=(',',':')).encode()
    registry_hash=hashlib.sha256(canonical).hexdigest()
    settings_hash={}
    for profile in ('gateway','executor','projector'):
        write(root/profile/'registry.json',canonical)
        cfg={'profile':'executor' if profile=='projector' else profile,'runtime_hash':args.runtime_hash,'synthetic':True,'allowed_release_hashes':args.release_hash,
             'worker_uri':registry['worker_uri'],'database_url_file':'/run/oracle-auth/database-url',
             'registry':'/run/oracle-auth/registry.json','registry_hash':registry_hash,'spool':'/run/oracle-jobs'}
        if profile=='gateway':cfg.update(server_cert='/run/oracle-auth/server.crt',server_key='/run/oracle-auth/server.key',client_ca='/run/oracle-auth/ca.crt',hmac_key_file='/run/oracle-auth/hmac-key',bind_host='0.0.0.0',bind_port=8443)
        else:cfg.update(graph_url_file='/run/oracle-auth/graph-url',blob_root='/run/oracle-blobs',source_role_registry_hash=source_registry_hash)
        raw=json.dumps(cfg,sort_keys=True,separators=(',',':')).encode()
        write(root/profile/'settings.json',raw);settings_hash[profile]=hashlib.sha256(raw).hexdigest()
    compose=textwrap.dedent(f'''\
    name: oracle-synthetic-{uuid4().hex[:12]}
    x-boundary: &boundary
      image: {args.image}
      cap_drop: [ALL]
      security_opt: [no-new-privileges:true]
      read_only: true
      init: true
      tmpfs: ['/tmp:rw,noexec,nosuid,size=64m']
      pids_limit: 128
      mem_limit: 1g
      labels: {{oracle.hosting.synthetic: "true"}}
    services:
      gateway:
        <<: *boundary
        command: [gateway]
        environment: {{ORACLE_HOSTING_SETTINGS_SHA256: {settings_hash['gateway']}}}
        networks: [ingress, jobs, ledger]
        ports: [127.0.0.1::8443]
        volumes: [./gateway:/run/oracle-auth:ro, ./spool:/run/oracle-jobs]
        depends_on: {{ledger: {{condition: service_healthy}}, synthetic-project: {{condition: service_completed_successfully}}}}
      executor:
        <<: *boundary
        command: [executor]
        environment: {{ORACLE_HOSTING_SETTINGS_SHA256: {settings_hash['executor']}}}
        networks: [jobs, ledger, candidate, provider]
        volumes: [./executor:/run/oracle-auth:ro, ./spool:/run/oracle-jobs, ./blobs:/run/oracle-blobs]
        depends_on: {{ledger: {{condition: service_healthy}}, synthetic-project: {{condition: service_completed_successfully}}}}
      synthetic-project:
        <<: *boundary
        entrypoint: [python, -m, oracle_brain.hosting.synthetic_project]
        environment: {{ORACLE_HOSTING_SETTINGS_SHA256: {settings_hash['projector']}}}
        networks: [ledger, candidate]
        volumes: [./projector:/run/oracle-auth:ro, ./blobs:/run/oracle-blobs]
        depends_on: {{ledger: {{condition: service_healthy}}, candidate: {{condition: service_started}}}}
      ledger:
        image: {POSTGRES}
        environment: {{POSTGRES_PASSWORD_FILE: /run/oracle-auth/admin-password, POSTGRES_DB: oracle_synthetic, POSTGRES_USER: oracle_bootstrap}}
        command: [postgres, -c, ssl=on, -c, ssl_cert_file=/run/oracle-auth/server.crt, -c, ssl_key_file=/run/oracle-auth/server.key, -c, hba_file=/run/oracle-auth/pg_hba.conf]
        networks: [ledger]
        volumes: [ledger-data:/var/lib/postgresql/data, ./ledger:/run/oracle-auth:ro, ./init:/docker-entrypoint-initdb.d:ro]
        healthcheck: {{test: [CMD-SHELL, 'test $$(psql -U oracle_bootstrap -d oracle_synthetic -Atc \"SELECT count(*) FROM oracle2.synthetic_hosting_marker\") = 1'], interval: 2s, timeout: 2s, retries: 30}}
      candidate:
        image: {FALKOR}
        user: "999:999"
        environment: {{REDIS_ARGS: /run/oracle-auth/server.conf}}
        networks: [candidate]
        volumes: [./candidate-data:/var/lib/falkordb/data, ./candidate:/run/oracle-auth:ro]
      confirmed:
        image: {FALKOR}
        user: "999:999"
        environment: {{REDIS_ARGS: /run/oracle-auth/server.conf}}
        networks: [confirmed]
        volumes: [./confirmed-data:/var/lib/falkordb/data, ./confirmed:/run/oracle-auth:ro]
    networks:
      ingress: {{}}
      jobs: &isolated
        internal: true
        enable_ipv6: true
        driver_opts:
          com.docker.network.bridge.gateway_mode_ipv4: isolated
          com.docker.network.bridge.gateway_mode_ipv6: isolated
      ledger:
        <<: *isolated
        ipam:
          config: [{{subnet: 172.30.41.0/24}}, {{subnet: "fd42:6f72:6163:41::/64"}}]
      candidate: *isolated
      confirmed: *isolated
      provider: *isolated
    volumes:
      ledger-data: {{}}
      candidate-data: {{}}
      confirmed-data: {{}}
    ''')
    write(root/'compose.yaml',compose,os.getuid())
    write(root/'SYNTHETIC.json',json.dumps({'synthetic':True,'image':args.image,'runtime_hash':args.runtime_hash,'registry_hash':registry_hash,'profiles':['gateway','executor','synthetic-project'],'source_role_registry_hash':source_registry_hash,'release_hash':fixture_release.content_hash(),'provider':'pending-admission','company_questions':'paused','grading':'paused'}),os.getuid())
    # Protected normal-platform environment inputs. Each one-shot materializer
    # receives only its own bundle; no runtime receives the issuer environment.
    from oracle_brain.hosting.bootstrap import FILES
    platform_env={'ORACLE_GATEWAY_SETTINGS_SHA256':settings_hash['gateway'],
                  'ORACLE_EXECUTOR_SETTINGS_SHA256':settings_hash['executor'],
                  'ORACLE_PROJECTOR_SETTINGS_SHA256':settings_hash['projector']}
    for profile in FILES:
        folder='projector' if profile=='synthetic-project' else profile
        if profile=='ledger-init':files={'seed-parameters.json':json.dumps(parameters,sort_keys=True,separators=(',',':')).encode()}
        else:files={name:(root/folder/name).read_bytes() for name in FILES[profile][0]}
        raw=json.dumps({'schema':'oracle-hosted-files/v1','profile':profile,'files':{n:{'bytes_b64':base64.b64encode(v).decode(),'sha256':hashlib.sha256(v).hexdigest()} for n,v in files.items()}},sort_keys=True,separators=(',',':')).encode()
        env_profile='PROJECTOR' if profile=='synthetic-project' else profile.upper().replace('-','_')
        platform_env['ORACLE_'+env_profile+'_BUNDLE']=base64.b64encode(raw).decode()
        platform_env['ORACLE_'+env_profile+'_BUNDLE_SHA256']=hashlib.sha256(raw).hexdigest()
    write(root/'platform-env.json',json.dumps(platform_env,sort_keys=True,separators=(',',':')),os.getuid())
    if os.geteuid()!=0:
        # Scoped local helper only owns this freshly generated synthetic tree;
        # no host socket, production path, credentials or network is mounted.
        owner_code="import os,pathlib; root=pathlib.Path('/assets'); mapping={'gateway':10001,'executor':10001,'projector':10001,'ledger':70,'candidate':999,'confirmed':999,'candidate-data':999,'confirmed-data':999,'spool':10001,'blobs':10001,'init':70}; [(os.chown(p,u,u),os.chmod(p,0o700 if p.is_dir() else 0o600)) for n,u in mapping.items() for p in [root/n,*(root/n).rglob('*')]]"
        subprocess.run(['docker','run','--name','oracle-synthetic-owner-'+uuid4().hex[:12],
            '--network','none','--read-only','--mount',f'type=bind,src={root.resolve()},dst=/assets',
            'python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e',
            'python','-c',owner_code],check=True,stdout=subprocess.DEVNULL)
    print(json.dumps({'prepared':True,'synthetic':True,'profiles':['gateway','executor','synthetic-project'],'source_role_registry_hash':source_registry_hash,'release_hash':fixture_release.content_hash(),'provider':'pending-admission'}))

if __name__=='__main__':main()
