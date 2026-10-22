"""W10-owned ephemeral clusters isolate cluster-wide roles across test workers.

Reuse the canonical Compose image/init and TLS/SCRAM qualifier. Retire this
helper with the verifier when the tests no longer mutate cluster-wide roles.
Only invented, regenerable fixtures are created; no existing project is reused.
"""
from contextlib import contextmanager
import json,os,re,stat,subprocess
from pathlib import Path
from uuid import uuid4
from dev.oracle2.test_tls_bootstrap import bootstrap,owned_postgres_fixture

ROOT=Path(__file__).resolve().parents[2]


def run(*args,env=None):
    return subprocess.check_output(args,env=env,text=True,stderr=subprocess.PIPE,timeout=60)


def owned_worker_database(container,admin_url):
    """Read-only proof of a canonical DB inside the exact owned TLS worker.

    The bootstrap guard stays fixed to oracle2. Only its database component is
    changed for that guard; the actual requested target is separately observed.
    No connection fallback, migration, role grant or database creation occurs.
    """
    import psycopg
    params=psycopg.conninfo.conninfo_to_dict(admin_url)
    allowed={'host','port','user','password','dbname','sslmode','sslrootcert'}
    name=params.get('dbname','')
    if (set(params)!=allowed or params.get('sslmode')!='verify-full'
            or not params.get('sslrootcert')
            or not (name=='oracle2' or re.fullmatch(r'oracle_operating_model_test_[0-9a-f]{32}',name))):
        raise PermissionError('exact canonical worker database and verify-full TLS required')
    base=psycopg.conninfo.make_conninfo(**(params|{'dbname':'oracle2'}))
    details=owned_postgres_fixture(container,base)
    with psycopg.connect(admin_url,connect_timeout=5) as connection:
        actual=connection.info.get_parameters()
        if (not connection.pgconn.ssl_in_use
                or any(actual.get(key)!=params[key] for key in
                    ('host','port','user','dbname','sslmode','sslrootcert'))):
            raise PermissionError('actual owned worker TLS target differs')
        row=connection.execute("SELECT SESSION_USER,current_database(),pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()").fetchone()
        if row!=('oracle2_admin',name,'oracle2_admin'):
            raise PermissionError('actual owned worker database identity/owner differs')
    return details


def worker_startup_intent(directory,base,label):
    """Read only the exact retained project owner after a pre-yield failure.

    Missing/changed evidence is unknown, never proof that resources are absent.
    The caller may inspect exact labels; this reader never performs cleanup.
    """
    if (not re.fullmatch(r'oracle2-(?:ci|synthetic)-[a-z0-9-]{1,80}',base)
            or not re.fullmatch(r'(?:documentary-[0-9]{2}|event)',label)):
        raise PermissionError('exact startup intent scope required')
    directory=Path(directory);parent=directory.lstat();path=directory/'startup-intent.json'
    before=path.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode)!=0o700
            or parent.st_uid!=os.getuid() or not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode)!=0o600 or before.st_uid!=os.getuid()
            or before.st_size>512):
        raise PermissionError('private startup intent required')
    def identity(info):
        return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,
                info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    with path.open('rb') as stream:
        opened=os.fstat(stream.fileno());raw=stream.read(513)
    after=path.lstat()
    if identity(before)!=identity(opened) or identity(before)!=identity(after) or len(raw)>512:
        raise PermissionError('startup intent changed')
    value=json.loads(raw)
    if (type(value) is not dict or set(value)!={'project','worker','synthetic_only'}
            or type(value['project']) is not str
            or not re.fullmatch(re.escape(base)+r'-w[0-9a-f]{12}',value['project'])
            or value['worker']!=label or value['synthetic_only'] is not True
            or raw!=(json.dumps(value,sort_keys=True)+'\n').encode()):
        raise PermissionError('exact startup intent differs')
    return value


@contextmanager
def worker_postgres(environment,directory,label):
    base=environment.get('COMPOSE_PROJECT_NAME','')
    if not re.fullmatch(r'oracle2-(?:ci|synthetic)-[a-z0-9-]{1,80}',base):
        raise PermissionError('owned synthetic Compose project required')
    if not re.fullmatch(r'(?:documentary-[0-9]{2}|event)',label):
        raise PermissionError('fixed bounded worker label required')
    project=base+'-w'+uuid4().hex[:12]
    if run('docker','ps','-aq','--filter','label=com.docker.compose.project='+project).strip():
        raise PermissionError('fresh empty worker project required')
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    env={**environment,'COMPOSE_PROJECT_NAME':project,'ORACLE2_POSTGRES_PORT':'0'}
    command=('docker','compose','-f',str(ROOT/'dev/oracle2/compose.yaml'),'-p',project)
    # Retain this exact privately generated owner before the first Compose effect,
    # even when startup fails before a container identity can be yielded. Exclusive
    # creation prevents replacement; the closed receipt never contains credentials.
    intent=directory/'startup-intent.json'
    descriptor=os.open(intent,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as stream:
        stream.write(json.dumps({'project':project,'worker':label,'synthetic_only':True},sort_keys=True)+'\n')
        stream.flush();os.fsync(stream.fileno())
    created=False
    try:
        # The project name was empty and is privately generated by this call.
        created=True
        run(*command,'up','-d','--wait','postgres',env=env)
        container=run(*command,'ps','-q','postgres',env=env).strip()
        if not re.fullmatch('[0-9a-f]{64}',container):raise PermissionError('exact worker container required')
        details=json.loads(run('docker','inspect',container))[0]
        labels=details['Config'].get('Labels',{})
        ports=details['NetworkSettings']['Ports'].get('5432/tcp') or []
        if (labels.get('com.docker.compose.project')!=project
                or labels.get('com.docker.compose.service')!='postgres'
                or labels.get('oracle.operating.synthetic')!='true'
                or set(details['NetworkSettings']['Networks'])!={project+'_default'}
                or len(ports)!=1 or ports[0]['HostIp']!='127.0.0.1'):
            raise PermissionError('worker project/container/network/loopback identity differs')
        identity={'project':project,'container_id':container,'port':int(ports[0]['HostPort']),
                  'worker':label,'synthetic_only':True}
        receipt=directory/'ownership.json';receipt.write_text(json.dumps(identity,sort_keys=True)+'\n');receipt.chmod(0o600)
        url='postgresql://oracle2_admin:oracle2_local_admin_only@127.0.0.1:'+str(identity['port'])+'/oracle2'
        tls=bootstrap(container,url,directory/'tls')
        yield {**tls,'ORACLE2_SYNTHETIC_POSTGRES_CONTAINER':container},identity
    finally:
        if created:
            # This exact fresh project contains only regenerable PostgreSQL
            # fixtures. Canonical source and ownership/qualification survive.
            run(*command,'down','--volumes',env=env)
