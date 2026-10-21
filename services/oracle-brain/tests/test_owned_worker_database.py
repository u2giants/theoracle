"""Narrow read-only worker target qualification; no migration/role shortcuts."""
from types import SimpleNamespace
import os
import re
from pathlib import Path
import psycopg
import pytest
from dev.oracle2 import test_worker_postgres_fixture as worker

PARAMS=dict(host='127.0.0.1',port='54321',user='oracle2_admin',password='oracle2_local_admin_only',
    dbname='oracle_operating_model_test_'+'a'*32,sslmode='verify-full',sslrootcert='/invented/ca.pem')

@pytest.fixture
def observed(monkeypatch):
    state={'calls':[],'params':dict(PARAMS),'ssl':True,'row':('oracle2_admin',PARAMS['dbname'],'oracle2_admin')}
    def parent(container,url):
        state['calls'].append(('parent',container,psycopg.conninfo.conninfo_to_dict(url)))
        if container!='owned-exact':raise PermissionError('invented wrong exact container')
        return {'owned':True}
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        @property
        def pgconn(self):return SimpleNamespace(ssl_in_use=state['ssl'])
        @property
        def info(self):return SimpleNamespace(get_parameters=lambda:state['params'])
        def execute(self,query):
            assert query.startswith('SELECT ')
            state['calls'].append(('read',query));return self
        def fetchone(self):return state['row']
    def connect(url,**kwargs):
        assert psycopg.conninfo.conninfo_to_dict(url)==PARAMS
        state['calls'].append(('connect',kwargs));return Connection()
    monkeypatch.setattr(worker,'owned_postgres_fixture',parent)
    monkeypatch.setattr(psycopg,'connect',connect)
    return state


def test_only_database_component_changes_for_unchanged_parent_guard(observed):
    assert worker.owned_worker_database('owned-exact',psycopg.conninfo.make_conninfo(**PARAMS))=={'owned':True}
    assert observed['calls'][0]==('parent','owned-exact',PARAMS|{'dbname':'oracle2'})
    assert len([x for x in observed['calls'] if x[0]=='connect'])==1
    assert len([x for x in observed['calls'] if x[0]=='read'])==1

@pytest.mark.parametrize('changes',[
    {'dbname':'company'}, {'dbname':'oracle_operating_model_test_'+'a'*31},
    {'dbname':'oracle_operating_model_test_'+'A'*32}, {'dbname':'oracle_operating_model_test_'+'a'*32+'x'},
    {'sslmode':'require'}, {'sslrootcert':''}, {'hostaddr':'127.0.0.1'}, {'options':'-c role=oracle2_admin'}])
def test_foreign_name_tls_or_indirection_rejected_before_parent_or_connection(observed,changes):
    with pytest.raises(PermissionError):worker.owned_worker_database('owned-exact',psycopg.conninfo.make_conninfo(**(PARAMS|changes)))
    assert observed['calls']==[]

@pytest.mark.parametrize('damage',['owner','session','database','ssl','ca','port','container'])
def test_actual_observed_owner_session_tls_target_and_exact_container_required(observed,damage):
    if damage=='owner':observed['row']=('oracle2_admin',PARAMS['dbname'],'foreign_owner')
    elif damage=='session':observed['row']=('foreign_session',PARAMS['dbname'],'oracle2_admin')
    elif damage=='database':observed['row']=('oracle2_admin','foreign_database','oracle2_admin')
    elif damage=='ssl':observed['ssl']=False
    elif damage=='ca':observed['params']['sslrootcert']='/foreign/ca.pem'
    elif damage=='port':observed['params']['port']='54322'
    with pytest.raises(PermissionError):
        worker.owned_worker_database('wrong' if damage=='container' else 'owned-exact',psycopg.conninfo.make_conninfo(**PARAMS))
    if damage=='container':assert not any(x[0]=='connect' for x in observed['calls'])


def test_real_canonical_owned_worker_database_is_observed():
    # Observe the exact caller-selected canonical database, without fallback.
    url=os.environ['ORACLE2_TEST_ADMIN_URL'];container=os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER']
    name=psycopg.conninfo.conninfo_to_dict(url)['dbname']
    # W10 supplies a fresh UUID database; the S03 phase owns the Compose base.
    # Both must prove the actual selected target, never switch to a fallback.
    assert name=='oracle2' or re.fullmatch(r'oracle_operating_model_test_[0-9a-f]{32}',name)
    details=worker.owned_worker_database(container,url)
    assert re.fullmatch(r'[0-9a-f]{64}',details['Id'])
    assert container==details['Id'] or details['Name']=='/'+container
    assert details['Config']['Labels']['oracle.operating.synthetic']=='true'


def test_retained_requester_fixture_cannot_overwrite_a_newer_canonical_capability(admin_url):
    """Regression: old requester setup replayed012/014 over newer same-OID code."""
    from dev.oracle2 import test_canonical_schema as schema
    from test_replacement_source_intake_sql import requester
    import psycopg
    signature = 'oracle2.finalize_source_revision_v1(uuid,integer,jsonb)'
    worker.owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], admin_url)
    with psycopg.connect(admin_url) as connection:
        original = connection.execute('SELECT pg_get_functiondef(to_regprocedure(%s))', (signature,)).fetchone()[0]
        assert original.count('AS $function$') == 1
        newer = original.replace('AS $function$', 'AS $function$\n-- invented later canonical extension; fixture must never overwrite\n', 1)
        connection.execute(newer)
    setup = requester.__wrapped__(admin_url)
    try:
        with pytest.raises(PermissionError, match='canonical test schema changed'):
            next(setup)
        with psycopg.connect(admin_url) as connection:
            actual = connection.execute('SELECT pg_get_functiondef(to_regprocedure(%s))', (signature,)).fetchone()[0]
            assert 'invented later canonical extension' in actual
        with pytest.raises(PermissionError, match='canonical test schema changed'):
            schema.bootstrap_canonical_test_schema(admin_url)
    finally:
        setup.close()
        worker.owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], admin_url)
        with psycopg.connect(admin_url) as connection:
            connection.execute(original)
    with psycopg.connect(admin_url) as connection:
        schema.assert_canonical_test_schema(connection, admin_url)


@pytest.mark.parametrize('damage',('permissions','symlink','changed','extra','noncanonical','duplicate'))
def test_canonical_schema_receipt_rejects_unprotected_changed_or_open_bytes(tmp_path,damage):
    import hashlib,json
    from dev.oracle2.test_canonical_schema import _read_receipt
    value={'schema_version':1,'database_key':'a'*64,'inventory':'b'*64,'catalog':'c'*64}
    raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    if damage=='extra':raw=json.dumps({**value,'authority':True},sort_keys=True,separators=(',',':')).encode()
    if damage=='noncanonical':raw=b' '+raw
    if damage=='duplicate':raw=raw[:-1]+b',"schema_version":1}'
    path=tmp_path/'receipt';path.write_bytes(raw);path.chmod(0o600);seal=hashlib.sha256(raw).hexdigest()
    if damage=='permissions':path.chmod(0o644)
    if damage=='symlink':
        link=tmp_path/'alias';link.symlink_to(path);path=link
    if damage=='changed':path.write_bytes(raw+b' ')
    with pytest.raises((PermissionError,OSError)):_read_receipt(path,seal)


def test_actual_canonical_schema_cross_process_receipt_verifies_without_replaying_ddl(admin_url,tmp_path):
    import subprocess,sys
    from dev.oracle2.test_canonical_schema import bootstrap_canonical_test_schema
    path=tmp_path/'canonical-schema.json'
    seal=bootstrap_canonical_test_schema(admin_url,receipt_path=path.resolve())
    script="""import os,psycopg
from dev.oracle2.test_canonical_schema import bootstrap_canonical_test_schema,_RECEIPTS
assert not _RECEIPTS
original=psycopg.Connection.execute
seen=[]
def readonly(self,query,*a,**kw):
    if not isinstance(query,str) or not query.lstrip().upper().startswith('SELECT '):
        raise AssertionError('child attempted schema replay or other mutation')
    seen.append(query)
    return original(self,query,*a,**kw)
psycopg.Connection.execute=readonly
bootstrap_canonical_test_schema(os.environ['ORACLE2_TEST_ADMIN_URL'])
assert seen and _RECEIPTS
"""
    env={**os.environ,'ORACLE2_TEST_ADMIN_URL':admin_url,'ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT':str(path.resolve()),'ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256':seal}
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('interrupt',(False,True))
def test_actual_phase_uses_distinct_uuid_and_cleans_only_its_database(admin_url,tmp_path,interrupt):
    from dev.oracle2.test_canonical_schema import owned_phase_database
    from scripts.oracle2.verify_phase import run_phase_tests
    import sys
    selected=None
    def exercise():
        nonlocal selected
        with owned_phase_database(admin_url,os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],tmp_path) as env:
            selected=psycopg.conninfo.conninfo_to_dict(env['ORACLE2_TEST_ADMIN_URL'])['dbname']
            assert re.fullmatch(r'oracle_operating_model_test_[0-9a-f]{32}',selected)
            assert selected!=psycopg.conninfo.conninfo_to_dict(admin_url)['dbname']
            case=tmp_path/'test_actual_phase_namespace.py'
            case.write_text("import os,psycopg\ndef test_actual():\n with psycopg.connect(os.environ['ORACLE2_TEST_ADMIN_URL']) as c:\n  assert c.pgconn.ssl_in_use\n  assert c.execute(\"SELECT to_regprocedure('oracle2.finalize_source_revision_v1(uuid,integer,jsonb)') IS NOT NULL\").fetchone()==(True,)\n")
            code,evidence,_=run_phase_tests(Path(sys.executable),[str(case)],env=env)
            assert code==0 and evidence['tests']==1 and evidence['failures']==evidence['skipped']==0
            if interrupt:raise RuntimeError('invented phase failure after actual tests')
    if interrupt:
        with pytest.raises(RuntimeError,match='invented phase failure'):exercise()
    else:exercise()
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM pg_database WHERE datname=%s',(selected,)).fetchone()==(0,)
        assert c.execute('SELECT current_database()').fetchone()==(psycopg.conninfo.conninfo_to_dict(admin_url)['dbname'],)
