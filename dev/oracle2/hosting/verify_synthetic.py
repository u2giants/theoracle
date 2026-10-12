"""Live local boundary proof; no claim of native job/source acceptance."""
import argparse
import hashlib
import hmac
import http.client
import json
from pathlib import Path
import socket
import ssl
import subprocess
import time
from uuid import uuid4


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);args=parser.parse_args(argv)
    root=Path(args.directory).resolve()
    marker=json.loads((root/'SYNTHETIC.json').read_text())
    if marker.get('synthetic') is not True:raise PermissionError('owned synthetic marker required')
    command=['docker','compose','-f',str(root/'compose.yaml')]
    ids=subprocess.check_output(command+['ps','-q']).decode().split()
    actual=json.loads(subprocess.check_output(['docker','inspect',*ids]))
    services={r['Config']['Labels']['com.docker.compose.service']:r for r in actual}
    if set(services)!={'gateway','executor','ledger','candidate','confirmed'} or not all(r['State']['Running'] for r in actual):
        raise AssertionError('actual five-profile synthetic stack unavailable')
    project=services['gateway']['Config']['Labels']['com.docker.compose.project']
    networks=json.loads(subprocess.check_output(['docker','network','inspect',*[project+'_'+n for n in ('jobs','ledger','candidate','confirmed','provider')]]))
    for network in networks:
        assert network['Internal'] is True and network['EnableIPv6'] is True
        assert network['Options']['com.docker.network.bridge.gateway_mode_ipv4']=='isolated'
        assert network['Options']['com.docker.network.bridge.gateway_mode_ipv6']=='isolated'
    checks={'five_profiles_running':True,'isolated_ipv4_ipv6':True,'native_job_acceptance':False,'provider_dispatch':False}
    port=int(services['gateway']['NetworkSettings']['Ports']['8443/tcp'][0]['HostPort'])
    context=ssl.create_default_context(cafile=str(root/'worker'/'ca.crt'))
    context.minimum_version=ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(root/'worker'/'server.crt',root/'worker'/'server.key')
    body=json.dumps({'job_id':str(uuid4()),'runtime_hash':marker['runtime_hash'],'admission_hash':'2'*64,
                     'nonce':str(uuid4()),'expires_at':int(time.time())+30},sort_keys=True,separators=(',',':')).encode()
    signature=hmac.new((root/'worker'/'hmac-key').read_bytes(),b'POST\n/v1/jobs/admit\n'+body,hashlib.sha256).hexdigest()
    with context.wrap_socket(socket.create_connection(('127.0.0.1',port),timeout=5),server_hostname='gateway') as sock:
        raw=b'POST /v1/jobs/admit HTTP/1.0\r\nHost: gateway\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\nX-Oracle-Job-Signature: '+signature.encode()+b'\r\n\r\n'+body
        sock.sendall(raw);reply=sock.recv(4096)
        assert reply.startswith(b'HTTP/1.0 403')
    checks['valid_worker_unregistered_job_denied']=True
    no_cert=ssl.create_default_context(cafile=str(root/'worker'/'ca.crt'))
    try:
        with no_cert.wrap_socket(socket.create_connection(('127.0.0.1',port),timeout=5),server_hostname='gateway') as sock:
            sock.sendall(b'GET / HTTP/1.0\r\n\r\n');sock.recv(4096)
    except ssl.SSLError:checks['missing_client_certificate_denied']=True
    else:raise AssertionError('missing worker cert accepted')
    gateway_code='''import pathlib,psycopg,json
url=pathlib.Path('/run/oracle-auth/database-url').read_text().strip()
with psycopg.connect(url) as conn:
 role=conn.execute('SELECT current_user').fetchone()[0]
 assert role=='oracle2_gateway_metadata'
 assert conn.pgconn.ssl_in_use is True
for query in ('SELECT pack FROM oracle2.operating_view_runs','SELECT text FROM oracle2.source_blocks',"UPDATE oracle2.sources SET status='error'"):
 with psycopg.connect(url) as conn:
  try:conn.execute(query)
  except psycopg.errors.InsufficientPrivilege:pass
  else:raise AssertionError('private read/write allowed')
print(json.dumps({'metadata_tls_verified':True,'private_reads_writes_denied':True}))
'''
    result=subprocess.check_output(['docker','exec','-i',services['gateway']['Id'],'python','-'],input=gateway_code.encode())
    checks.update(json.loads(result))
    confirmed_ip=services['confirmed']['NetworkSettings']['Networks'][project+'_confirmed']['IPAddress']
    executor_code='''import pathlib,psycopg,json,socket,redis
url=pathlib.Path('/run/oracle-auth/database-url').read_text().strip()
with psycopg.connect(url) as conn:
 assert conn.execute('SELECT current_user').fetchone()[0]=='oracle_synthetic_executor'
 assert conn.pgconn.ssl_in_use is True
 assert conn.execute("SELECT marker FROM oracle2.synthetic_hosting_marker").fetchone()[0]=='invented-local-only'
graph=pathlib.Path('/run/oracle-auth/graph-url').read_text().strip()
assert redis.Redis.from_url(graph).ping()
for host,port in [('1.1.1.1',443),('100.66.37.58',8000),('100.66.37.58',22),('2606:4700:4700::1111',443),(CONFIRMED,6379)]:
 try:
  sock=socket.create_connection((host,port),timeout=1);sock.close()
 except OSError:pass
 else:raise AssertionError('executor forbidden route opened')
print(json.dumps({'executor_application_tls_verified':True,'candidate_authenticated':True,'executor_external_host_confirmed_denied':True}))
'''.replace('CONFIRMED',repr(confirmed_ip))
    result=subprocess.check_output(['docker','exec','-i',services['executor']['Id'],'python','-'],input=executor_code.encode())
    checks.update(json.loads(result))
    checks['project']=project;checks['image']=marker['image']
    receipt=root/'boundary-proof.json';receipt.write_text(json.dumps(checks,sort_keys=True));receipt.chmod(0o600)
    print(json.dumps(checks,sort_keys=True))

if __name__=='__main__':main()
