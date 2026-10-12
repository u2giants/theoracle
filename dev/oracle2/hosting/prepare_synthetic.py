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
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID

POSTGRES='postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297'
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
    parser.add_argument('--release-hash',required=True,action='append')
    parser.add_argument('--synthetic',required=True,action='store_true')
    args=parser.parse_args(argv)
    if not re.fullmatch('sha256:[a-f0-9]{64}',args.image):raise ValueError('immutable local image ID required')
    if any(not re.fullmatch('[a-f0-9]{64}',x) for x in [args.runtime_hash,*args.release_hash]):raise ValueError('exact hashes required')
    root=Path(args.directory)
    if root.exists():raise FileExistsError('new synthetic directory required')
    root.mkdir(parents=True,mode=0o700)
    for name,uid in [('gateway',10001),('executor',10001),('worker',os.getuid()),('ledger',70),('candidate',999),('confirmed',999),('spool',10001),('blobs',10001),('init',70)]:
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
    gateway_password,executor_password,broker_password,admin_password=(secrets.token_hex(32) for _ in range(4))
    write(root/'ledger'/'admin-password',admin_password,70)
    hmac=secrets.token_bytes(48)
    write(root/'gateway'/'hmac-key',hmac);write(root/'worker'/'hmac-key',hmac,os.getuid())
    for folder,user,password in [('gateway','oracle_synthetic_gateway',gateway_password),('executor','oracle_synthetic_executor',executor_password)]:
        url=f'postgresql://{user}:{password}@ledger:5432/oracle_synthetic?sslmode=verify-full&sslrootcert=/run/oracle-auth/ca.crt'
        write(root/folder/'database-url',url)
    # No provider key is issued. Broker startup remains admission-gated.
    write(root/'ledger'/'synthetic-broker-password',broker_password,70)
    write(root/'ledger'/'pg_hba.conf','local all all trust\nhostssl oracle_synthetic oracle_synthetic_gateway all scram-sha-256\nhostssl oracle_synthetic oracle_synthetic_executor all scram-sha-256\nhostssl oracle_synthetic oracle_synthetic_broker all scram-sha-256\nhost all all all reject\n',70)
    sqlroot=Path(__file__).resolve().parents[3]/'services/oracle-brain/sql'
    for index,name in enumerate(('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql','006_hosting_gateway_authority.sql')):
        write(root/'init'/f'{index:02d}-{name}',(sqlroot/name).read_bytes(),70)
    roles=f'''-- Fresh owned synthetic namespace only; not a deployment authority.
CREATE TABLE oracle2.synthetic_hosting_marker(marker text PRIMARY KEY CHECK(marker='invented-local-only'));
INSERT INTO oracle2.synthetic_hosting_marker VALUES('invented-local-only');
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE ROLE oracle_synthetic_gateway LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{gateway_password}';
GRANT oracle2_gateway_metadata TO oracle_synthetic_gateway;
ALTER ROLE oracle_synthetic_gateway SET role='oracle2_gateway_metadata';
CREATE ROLE oracle_synthetic_executor LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{executor_password}';
GRANT USAGE ON SCHEMA oracle2 TO oracle_synthetic_executor;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA oracle2 TO oracle_synthetic_executor;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA oracle2 TO oracle_synthetic_executor;
CREATE ROLE oracle_synthetic_broker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{broker_password}';
GRANT USAGE ON SCHEMA oracle2 TO oracle_synthetic_broker;
GRANT SELECT,INSERT ON oracle2.operating_dispatch_reservations,oracle2.operating_dispatch_receipts,oracle2.operating_dispatch_diagnoses TO oracle_synthetic_broker;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO oracle_synthetic_broker;
'''
    write(root/'init'/'90-synthetic-roles.sql',roles,70)
    # The graph password is only synthetic; native SDK executes inside isolated
    # candidate network. TLS SDK support requires its own qualified receipt.
    graph_password=secrets.token_hex(32)
    for folder in ('candidate','confirmed'):
        password=graph_password if folder=='candidate' else secrets.token_hex(32)
        write(root/folder/'server.conf',f'bind 0.0.0.0\nport 6379\nprotected-mode yes\nrequirepass {password}\ndir /var/lib/falkordb/data\n',999)
    write(root/'executor'/'graph-url',f'redis://:{graph_password}@candidate:6379')
    registry={'worker_uri':'spiffe://oracle/synthetic-worker','runtime_hash':args.runtime_hash,'active':True,
              'expires_at':int((now+timedelta(hours=1)).timestamp()),'allowed_release_hashes':args.release_hash}
    canonical=json.dumps(registry,sort_keys=True,separators=(',',':')).encode()
    registry_hash=hashlib.sha256(canonical).hexdigest()
    settings_hash={}
    for profile in ('gateway','executor'):
        write(root/profile/'registry.json',canonical)
        cfg={'profile':profile,'runtime_hash':args.runtime_hash,'synthetic':True,'allowed_release_hashes':args.release_hash,
             'worker_uri':registry['worker_uri'],'database_url_file':'/run/oracle-auth/database-url',
             'registry':'/run/oracle-auth/registry.json','registry_hash':registry_hash,'spool':'/run/oracle-jobs'}
        if profile=='gateway':cfg.update(server_cert='/run/oracle-auth/server.crt',server_key='/run/oracle-auth/server.key',client_ca='/run/oracle-auth/ca.crt',hmac_key_file='/run/oracle-auth/hmac-key',bind_host='0.0.0.0',bind_port=8443)
        else:cfg.update(graph_url_file='/run/oracle-auth/graph-url',blob_root='/run/oracle-blobs')
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
        depends_on: {{ledger: {{condition: service_healthy}}}}
      executor:
        <<: *boundary
        command: [executor]
        environment: {{ORACLE_HOSTING_SETTINGS_SHA256: {settings_hash['executor']}}}
        networks: [jobs, ledger, candidate, provider]
        volumes: [./executor:/run/oracle-auth:ro, ./spool:/run/oracle-jobs, ./blobs:/run/oracle-blobs]
        depends_on: {{ledger: {{condition: service_healthy}}}}
      ledger:
        image: {POSTGRES}
        environment: {{POSTGRES_PASSWORD_FILE: /run/oracle-auth/admin-password, POSTGRES_DB: oracle_synthetic}}
        command: [postgres, -c, ssl=on, -c, ssl_cert_file=/run/oracle-auth/server.crt, -c, ssl_key_file=/run/oracle-auth/server.key, -c, hba_file=/run/oracle-auth/pg_hba.conf]
        networks: [ledger]
        volumes: [ledger-data:/var/lib/postgresql/data, ./ledger:/run/oracle-auth:ro, ./init:/docker-entrypoint-initdb.d:ro]
        healthcheck: {{test: [CMD-SHELL, 'pg_isready -U postgres -d oracle_synthetic'], interval: 2s, timeout: 2s, retries: 30}}
      candidate:
        image: {FALKOR}
        command: [redis-server, /run/oracle-auth/server.conf, --loadmodule, /var/lib/falkordb/bin/falkordb.so]
        networks: [candidate]
        volumes: [candidate-data:/var/lib/falkordb/data, ./candidate:/run/oracle-auth:ro]
      confirmed:
        image: {FALKOR}
        command: [redis-server, /run/oracle-auth/server.conf, --loadmodule, /var/lib/falkordb/bin/falkordb.so]
        networks: [confirmed]
        volumes: [confirmed-data:/var/lib/falkordb/data, ./confirmed:/run/oracle-auth:ro]
    networks:
      ingress: {{}}
      jobs: &isolated
        internal: true
        enable_ipv6: true
        driver_opts:
          com.docker.network.bridge.gateway_mode_ipv4: isolated
          com.docker.network.bridge.gateway_mode_ipv6: isolated
      ledger: *isolated
      candidate: *isolated
      confirmed: *isolated
      provider: *isolated
    volumes:
      ledger-data: {{}}
      candidate-data: {{}}
      confirmed-data: {{}}
    ''')
    write(root/'compose.yaml',compose,os.getuid())
    write(root/'SYNTHETIC.json',json.dumps({'synthetic':True,'image':args.image,'runtime_hash':args.runtime_hash,'registry_hash':registry_hash,'profiles':['gateway','executor'],'provider':'pending-admission','company_questions':'paused','grading':'paused'}),os.getuid())
    if os.geteuid()!=0:
        # Scoped local helper only owns this freshly generated synthetic tree;
        # no host socket, production path, credentials or network is mounted.
        owner_code="import os,pathlib; root=pathlib.Path('/assets'); mapping={'gateway':10001,'executor':10001,'ledger':70,'candidate':999,'confirmed':999,'spool':10001,'blobs':10001,'init':70}; [(os.chown(p,u,u),os.chmod(p,0o700 if p.is_dir() else 0o600)) for n,u in mapping.items() for p in [root/n,*(root/n).rglob('*')]]"
        subprocess.run(['docker','run','--name','oracle-synthetic-owner-'+uuid4().hex[:12],
            '--network','none','--read-only','--mount',f'type=bind,src={root.resolve()},dst=/assets',
            'python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e',
            'python','-c',owner_code],check=True,stdout=subprocess.DEVNULL)
    print(json.dumps({'prepared':True,'synthetic':True,'profiles':['gateway','executor'],'provider':'pending-admission'}))

if __name__=='__main__':main()
