#!/usr/bin/env python3
"""Enable authenticated TLS on an exact owned, labelled ephemeral test container."""
import argparse,hashlib,ipaddress,json,os,subprocess
from pathlib import Path
import psycopg


def run(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)


def bootstrap(container,admin_url,directory):
    details=json.loads(run('docker','inspect',container))[0]
    if details['Config'].get('Labels',{}).get('oracle.operating.synthetic')!='true':
        raise PermissionError('explicit synthetic container label required')
    ports=details['NetworkSettings']['Ports'].get('5432/tcp') or []
    params=psycopg.conninfo.conninfo_to_dict(admin_url)
    if (not ports or any(p['HostIp']!='127.0.0.1' for p in ports)
            or params.get('host')!='127.0.0.1'
            or not any(p['HostPort']==params.get('port') for p in ports)
            or params.get('user')!='oracle2_admin' or params.get('password')!='oracle2_local_admin_only'
            or params.get('dbname')!='oracle2'):
        raise PermissionError('exact invented loopback fixture required')
    env=set(details['Config']['Env'])
    if not {'POSTGRES_USER=oracle2_admin','POSTGRES_PASSWORD=oracle2_local_admin_only','POSTGRES_DB=oracle2'}<=env:
        raise PermissionError('invented PostgreSQL fixture identity required')
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(directory,0o700)
    cert,key=directory/'ca.pem',directory/'server.key'
    run('openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-subj','/CN=Oracle invented ephemeral test CA',
        '-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-keyout',str(key),'-out',str(cert))
    os.chmod(cert,0o600);os.chmod(key,0o600)
    data='/var/lib/postgresql/data'
    for path in (cert,key):run('docker','cp',str(path),container+':'+data+'/'+path.name)
    run('docker','exec',container,'chown','postgres:postgres',data+'/ca.pem',data+'/server.key')
    run('docker','exec',container,'chmod','600',data+'/ca.pem',data+'/server.key')
    hba=run('docker','exec',container,'cat',data+'/pg_hba.conf')
    before=directory/'pg_hba.before.conf'
    if not before.exists():before.write_text(hba);os.chmod(before,0o600)
    networks={'127.0.0.1/32','::1/128'}
    for network in details['NetworkSettings']['Networks'].values():
        if network.get('IPAddress'):
            networks.add(str(ipaddress.ip_network(network['IPAddress']+'/'+str(network['IPPrefixLen']),strict=False)))
    lines=['local all oracle2_admin trust','local all all reject',
           'hostnossl all all 0.0.0.0/0 reject','hostnossl all all ::/0 reject']
    lines += ['hostssl all all '+network+' scram-sha-256' for network in sorted(networks)]
    lines += ['hostssl all all 0.0.0.0/0 reject','hostssl all all ::/0 reject']
    after=directory/'pg_hba.conf';after.write_text('\n'.join(lines)+'\n');os.chmod(after,0o600)
    run('docker','cp',str(after),container+':'+data+'/pg_hba.conf')
    run('docker','exec',container,'chown','postgres:postgres',data+'/pg_hba.conf')
    for statement in ("ALTER SYSTEM SET ssl='on'", "ALTER SYSTEM SET ssl_cert_file='/var/lib/postgresql/data/ca.pem'", "ALTER SYSTEM SET ssl_key_file='/var/lib/postgresql/data/server.key'", 'SELECT pg_reload_conf()'):
        run('docker','exec',container,'psql','-U','oracle2_admin','-d','oracle2','-v','ON_ERROR_STOP=1','-c',statement)
    url=psycopg.conninfo.make_conninfo(admin_url,sslmode='verify-full',sslrootcert=str(cert.resolve()))
    with psycopg.connect(url) as c:
        if not c.pgconn.ssl_in_use:raise AssertionError('actual TLS required')
        methods=c.execute("SELECT auth_method FROM pg_hba_file_rules WHERE type='hostssl' AND auth_method<>'reject'").fetchall()
        if not methods or any(row[0]!='scram-sha-256' for row in methods):raise AssertionError('actual host SCRAM required')
        if not c.execute("SELECT rolpassword LIKE 'SCRAM-SHA-256$%%' FROM pg_authid WHERE rolname=SESSION_USER").fetchone()[0]:raise AssertionError('SCRAM stored verifier required')
    try:psycopg.connect(psycopg.conninfo.make_conninfo(url,password='invented-deliberately-wrong'))
    except psycopg.OperationalError:pass
    else:raise AssertionError('wrong password unexpectedly authenticated')
    try:psycopg.connect(psycopg.conninfo.make_conninfo(url,sslmode='disable'))
    except psycopg.OperationalError:pass
    else:raise AssertionError('plaintext unexpectedly authenticated')
    proof={'synthetic_only':True,'container_id':details['Id'],'tls_verify_full':True,'wrong_password_refused':True,'plaintext_refused':True,'hostssl_scram_networks':sorted(networks),'ca_sha256':hashlib.sha256(cert.read_bytes()).hexdigest(),'hba_sha256':hashlib.sha256(after.read_bytes()).hexdigest()}
    qualification=directory/'qualification.json';qualification.write_text(json.dumps(proof,indent=2)+'\n');os.chmod(qualification,0o600)
    result={'ORACLE2_TEST_ADMIN_URL':url,'ORACLE2_TEST_TLS_ROOT':str(cert.resolve())}
    output=directory/'environment.json';output.write_text(json.dumps(result,indent=2)+'\n');os.chmod(output,0o600)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--container',required=True);parser.add_argument('--directory',required=True)
    args=parser.parse_args();os.umask(0o077)
    result=bootstrap(args.container,os.environ['ORACLE2_TEST_ADMIN_URL'],args.directory)
    if os.getenv('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'],'a') as f:
            for key,value in result.items():f.write(key+'='+value+'\n')
    print('Owned synthetic PostgreSQL: verify-full TLS, SCRAM, plaintext and wrong-password refusal proved')
