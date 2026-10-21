"""Narrow read-only worker target qualification; no migration/role shortcuts."""
from types import SimpleNamespace
import os
import re
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
