#!/usr/bin/env python3
"""Enable authenticated TLS on an exact owned, labelled ephemeral test container."""
import argparse,hashlib,ipaddress,json,os,re,shutil,subprocess
from pathlib import Path
import psycopg
from urllib.parse import quote, urlencode


def postgres_uri(conninfo, *, sslrootcert):
    """Export one explicit loopback URI; never service/hostaddr indirection."""
    params=psycopg.conninfo.conninfo_to_dict(conninfo)
    allowed={'host','port','user','password','dbname','sslmode','sslrootcert'}
    if set(params)-allowed or params.get('host') not in {'127.0.0.1','localhost'}:
        raise PermissionError('single explicit loopback PostgreSQL target required')
    if not re.fullmatch(r'[0-9]{1,5}',params.get('port','')) or not 0<int(params['port'])<=65535:
        raise PermissionError('explicit PostgreSQL port required')
    if not all(params.get(k) for k in ('user','password','dbname')):
        raise PermissionError('explicit fixture identity required')
    authority=quote(params['user'],safe='')+':'+quote(params['password'],safe='')+'@'+params['host']+':'+params['port']
    return 'postgresql://'+authority+'/'+quote(params['dbname'],safe='')+'?'+urlencode({'sslmode':'verify-full','sslrootcert':str(sslrootcert)},quote_via=quote)


def run(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE,timeout=30)


def owned_postgres_fixture(container,admin_url):
    """Read-only proof of the exact labelled, invented loopback PostgreSQL."""
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}',container):
        raise PermissionError('exact synthetic container identity required')
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
    return details


def bootstrap(container,admin_url,directory):
    details=owned_postgres_fixture(container,admin_url)
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(directory,0o700)
    issuer=directory/'issuer';issuer.mkdir(mode=0o700,exist_ok=True);os.chmod(issuer,0o700)
    name=details['Name'].lstrip('/')
    if not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}',name):raise PermissionError('invalid owned Docker DNS name')
    image='python@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e'
    issuer_modes=[]
    def issue(*args):
        created=run('docker','create','--network','none','--read-only','--cap-drop','ALL',
                    '--security-opt','no-new-privileges','--user',str(os.getuid())+':'+str(os.getgid()),
                    '--mount','type=bind,src='+str(issuer.resolve())+',dst=/issuer',
                    '--entrypoint','openssl',image,*args).strip()
        if not re.fullmatch('[0-9a-f]{64}',created):raise AssertionError('exact issuer container identity required')
        try:
            actual=json.loads(run('docker','inspect',created))[0]
            mode=actual['HostConfig']['NetworkMode']
            if mode!='none' or not actual['HostConfig']['ReadonlyRootfs']:
                raise AssertionError('issuer must actually be networkless and read-only')
            issuer_modes.append(mode)
            output=run('docker','start','-a',created)
            if json.loads(run('docker','inspect',created))[0]['State']['ExitCode']!=0:
                raise AssertionError('networkless issuer command failed')
            return output
        finally:
            # Only the exact disposable issuer is removed; its protected keys survive.
            run('docker','rm','-f',created)
    issue('req','-x509','-newkey','rsa:2048','-nodes','-days','2','-subj','/CN=Oracle invented ephemeral issuer',
          '-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign',
          '-keyout','/issuer/issuer.key','-out','/issuer/ca.pem')
    issue('req','-new','-newkey','rsa:2048','-nodes','-subj','/CN='+name,
          '-keyout','/issuer/server.key','-out','/issuer/server.csr')
    extension=issuer/'leaf.ext';extension.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost,DNS:'+name+',IP:127.0.0.1,IP:::1\n')
    issue('x509','-req','-days','2','-in','/issuer/server.csr','-CA','/issuer/ca.pem','-CAkey','/issuer/issuer.key',
          '-CAcreateserial','-extfile','/issuer/leaf.ext','-out','/issuer/server.crt')
    for path in issuer.iterdir():os.chmod(path,0o600)
    cert,key,leaf=directory/'ca.pem',directory/'server.key',directory/'server.crt'
    for filename in ('ca.pem','server.key','server.crt'):
        shutil.copyfile(issuer/filename,directory/filename);os.chmod(directory/filename,0o600)
    certificate=run('openssl','x509','-in',str(leaf),'-noout','-text')
    if 'CA:FALSE' not in certificate or 'TLS Web Server Authentication' not in certificate or 'X509v3 Key Usage: critical' not in certificate:
        raise AssertionError('qualified non-CA server leaf required')
    data='/var/lib/postgresql/data'
    for path in (cert,key,leaf):run('docker','cp',str(path),container+':'+data+'/'+path.name)
    run('docker','exec',container,'chown','postgres:postgres',data+'/ca.pem',data+'/server.key',data+'/server.crt')
    run('docker','exec',container,'chmod','600',data+'/ca.pem',data+'/server.key',data+'/server.crt')
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
    for statement in ("ALTER SYSTEM SET ssl='on'", "ALTER SYSTEM SET ssl_cert_file='/var/lib/postgresql/data/server.crt'", "ALTER SYSTEM SET ssl_key_file='/var/lib/postgresql/data/server.key'", 'SELECT pg_reload_conf()'):
        run('docker','exec',container,'psql','-U','oracle2_admin','-d','oracle2','-v','ON_ERROR_STOP=1','-c',statement)
    url=postgres_uri(admin_url,sslrootcert=cert.resolve())
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
    run('docker','exec',container,'test','!','-e',data+'/issuer.key')
    if any(str(issuer.resolve())==m.get('Source') for m in details.get('Mounts',[])):raise AssertionError('issuer must not be mounted in runtime')
    proof={'issuer_network_mode':'none','issuer_actual_network_modes':issuer_modes,'issuer_key_runtime_path_absent':True,'issuer_mount_absent':True,'leaf_ca':False,'leaf_server_auth':True,'synthetic_only':True,'container_id':details['Id'],'tls_verify_full':True,'wrong_password_refused':True,'plaintext_refused':True,'hostssl_scram_networks':sorted(networks),'ca_sha256':hashlib.sha256(cert.read_bytes()).hexdigest(),'hba_sha256':hashlib.sha256(after.read_bytes()).hexdigest()}
    qualification=directory/'qualification.json';qualification.write_text(json.dumps(proof,indent=2)+'\n');os.chmod(qualification,0o600)
    result={'ORACLE2_TEST_ADMIN_URL':url,'ORACLE2_TEST_TLS_ROOT':str(cert.resolve()),'ORACLE2_TEST_TLS_QUALIFICATION':str(qualification.resolve())}
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
