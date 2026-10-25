"""Offline fixture-order proof only: no socket, Docker, DB or actual Next."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import os
import pytest
import test_recommendation_next_auth_browser_v1 as owner

PARENT='postgresql://invented@127.0.0.1/parent'
CHILD='postgresql://invented@127.0.0.1/oracle_operating_model_test_'+'1'*32
KEYS=('ORACLE2_TEST_ADMIN_URL','ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT','ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256')

@pytest.mark.parametrize('failure',(False,True))
def test_phase_binding_precedes_qualification_and_restores_after_both_paths(tmp_path,failure):
    events=[];before={k:os.environ.get(k) for k in KEYS}
    @contextmanager
    def phase(parent,container,directory):
        assert parent==PARENT and container=='invented-owned'
        events.append('phase-created-canonical-once')
        try:yield dict(zip(KEYS,(CHILD,'invented-child-receipt','a'*64)))
        finally:
            assert {k:os.environ.get(k) for k in KEYS}==before
            events.append('phase-closed-exact-child')
    def schema(url):
        assert url==CHILD and os.environ[KEYS[0]]==CHILD
        assert os.environ[KEYS[1]]=='invented-child-receipt'
        events.append('child-catalog-asserted')
    def advice(url,directory,monkeypatch,*,serving):
        assert url==CHILD and serving is True and os.environ[KEYS[0]]==CHILD
        events.append('qualification-after-binding')
        return 'invented-advice'
    class Result:
        def __init__(self,row):self.row=row
        def fetchone(self):return self.row
    class Connection:
        pgconn=type('SSL',(),dict(ssl_in_use=True))()
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,query,args=()):
            if query.startswith('SELECT SESSION_USER'):return Result(('oracle2_admin','parent'))
            assert query.startswith('SELECT count(*) FROM pg_database')
            assert args==('oracle_operating_model_test_'+'1'*32,)
            events.append('independent-child-absence')
            return Result((0,))
    def parent_state(url):
        assert url==PARENT
        events.append('parent-state')
        return ('parent',[],[])
    monkeypatch=pytest.MonkeyPatch()
    try:
        monkeypatch.setenv('ORACLE2_SYNTHETIC_POSTGRES_CONTAINER','invented-owned')
        with patch.object(owner,'owned_worker_database',lambda *args:None),patch.object(owner,'owned_phase_database',phase),patch.object(owner,'_assert_recommendation_schema_v1',schema),patch.object(owner,'_parent_next_identity_state_v1',parent_state),patch.object(owner,'_measurement_advice_v1',advice),patch.object(owner.psycopg,'connect',lambda *args:Connection()):
            fixture=owner.recommendation_next_database_v1.__wrapped__(PARENT,tmp_path,monkeypatch)
            target=next(fixture)
            assert owner.recommendation_next_serving_advice_v1.__wrapped__(target,None,tmp_path,monkeypatch)=='invented-advice'
            events.append('all-test-processes-closed')
            if failure:
                with pytest.raises(RuntimeError,match='invented test stage failed'):
                    fixture.throw(RuntimeError('invented test stage failed'))
            else:
                with pytest.raises(StopIteration):next(fixture)
        assert {k:os.environ.get(k) for k in KEYS}==before
        assert events==['parent-state','phase-created-canonical-once','child-catalog-asserted','qualification-after-binding','all-test-processes-closed','phase-closed-exact-child','parent-state','independent-child-absence']
        assert (tmp_path/'actual-next-database-cleanup.json').is_file()
    finally:monkeypatch.undo()
