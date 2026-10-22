"""Actual central Budget/receipt SQL with fake provider wire + real signed TLS.

Source/population getter remains explicit typed seam; SQL018 authority is tested
separately using actual own reviewer. No actual provider or company data.
"""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4
import hashlib
import psycopg
from psycopg import sql
import pytest
from oracle_brain.operating_model.native_factory import ledger_namespace_hash
from oracle_brain.operating_model.key_coverage import VerifiedKeyCoverage
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.provider_adapter import Budget
from oracle_brain.hosting import protected_raw_original_factory_v1 as m
from test_protected_raw_original_factory_v1 import (factory_case,bound_tls,certificates,KEY,FP,COVERAGE,
    REAL_RESERVE,REAL_FINISH,REAL_SETTLEMENT,REAL_VERIFY_LEDGER)
from test_raw_original_settings_v1 import write,appointment


@pytest.fixture
def actual_factory_ledger(admin_url):
    # This test is run only under canonical fresh owned worker guard. Restrict
    # again before its own DDL; no fallback URL or noncanonical database.
    import os,re
    from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
    container=os.environ.get('ORACLE2_SYNTHETIC_POSTGRES_CONTAINER','')
    if not container:raise PermissionError('actual owned worker identity required')
    owned_worker_database(container,admin_url)
    name='raw_billing_'+uuid4().hex[:12];password=uuid4().hex
    with psycopg.connect(admin_url) as c:
        assert c.pgconn.ssl_in_use and re.fullmatch(r'oracle_operating_model_test_[0-9a-f]{32}',c.info.dbname)
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(name),sql.Literal(password)))
        c.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(name)))
        c.execute(sql.SQL('GRANT SELECT,INSERT ON oracle2.operating_dispatch_reservations,oracle2.operating_dispatch_receipts,oracle2.operating_dispatch_diagnoses TO {}').format(sql.Identifier(name)))
        c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {}').format(sql.Identifier(name)))
        cluster=c.execute('SELECT system_identifier::text FROM pg_catalog.pg_control_system()').fetchone()[0]
        namespace=ledger_namespace_hash(c)
    url=psycopg.conninfo.make_conninfo(admin_url,user=name,password=password)
    try:yield url,name,cluster,namespace
    finally:
        owned_worker_database(container,admin_url)
        with psycopg.connect(admin_url) as c:
            c.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(name)))
            c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))


def test_factory_actual_budget_commit_and_unknown_overrun_are_durable(factory_case,actual_factory_ledger,monkeypatch):
    factory,state,_,_=factory_case;url,role,cluster,namespace=actual_factory_ledger
    # Restore the ACTUAL unchanged central Budget methods and factory SELECT.
    monkeypatch.setattr(Budget,'reserve',REAL_RESERVE);monkeypatch.setattr(Budget,'finish',REAL_FINISH)
    monkeypatch.setattr(m.ProtectedRawOriginalFactoryV1,'_settlement',REAL_SETTLEMENT)
    monkeypatch.setattr(m,'verify_ledger',REAL_VERIFY_LEDGER)
    s=factory.settings;b=factory.broker;parts=psycopg.conninfo.conninfo_to_dict(url)
    registry=b._registry.model_copy(update={'host':parts['host'],'port':int(parts['port']),
        'database':parts['dbname'],'role':role,'cluster_identifier':cluster,'namespace_hash':namespace})
    rh=digest(registry.model_dump(mode='json'));q=s.context.job.pricing.model_copy(update={'ledger_registry_hash':rh})
    job=type(s.context.job).model_validate(s.context.job.model_dump(mode='python')|{'pricing':q})
    x=type(s.context).model_validate(s.context.model_dump(mode='python')|{'job':job,'pricing_quote_hash':digest(q.model_dump(mode='json'))})
    bounds=s.read_billing_bounds().bounds.model_copy(update={'ledger_registry_hash':rh})
    xh=write(__import__('pathlib').Path(s.config.context.path),x)
    bh=write(__import__('pathlib').Path(s.config.billing_bounds.path),bounds)
    c=type(s.config).model_validate(s.config.model_dump(mode='python')|{'context':{'path':s.config.context.path,'sha256':xh},
        'billing_bounds':{'path':s.config.billing_bounds.path,'sha256':bh}})
    ch=write(s.config_path,c);a=appointment(c,ch);ah=write(s.appointment_path,a)
    factory.settings=replace(s,config=c,config_sha256=ch,appointment=a,appointment_sha256=ah,context=x)
    b._url=url;b._registry=registry;b._registry_hash=rh;state['job']=job
    def coverage():
        at=datetime.now(timezone.utc)-timedelta(seconds=1)
        return VerifiedKeyCoverage(admission_hash=COVERAGE,key_fingerprint=FP,ledger_identity_hash=rh,
            observed_at=at,expires_at=at+timedelta(seconds=10))
    b._coverage=coverage
    wire_locks=[]
    def no_budget_lock_during_native():
        with psycopg.connect(url) as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            available=conn.execute('SELECT pg_try_advisory_xact_lock(hashtext(%s))',('oracle-operating-budget',)).fetchone()[0]
            wire_locks.append(available)
            assert available is True, 'actual Budget transaction held across native POST'
    state['wire_hook']=no_budget_lock_during_native
    result=factory.execute()
    assert wire_locks==[True]
    with psycopg.connect(url) as conn:
        assert conn.execute('SELECT actual_usd,status,response_hash FROM oracle2.operating_dispatch_receipts WHERE reservation_id=%s',
            (result.commit.reservation_id,)).fetchone()==(Decimal('.003'),'completed',hashlib.sha256(result.content_utf8).hexdigest())
    assert state['paid']==1
    with pytest.raises(PermissionError):factory.execute()
    assert state['paid']==1
    # A separate independently pinned invented job exercises an observed upstream
    # overrun. It is not a retry: new dispatch/artifact, same original allocation.
    s=factory.settings;dispatch=uuid4();q=s.context.job.pricing.model_copy(update={'dispatch_id':dispatch})
    second=type(s.context.job).model_validate(s.context.job.model_dump(mode='python')|{
        'dispatch_id':dispatch,'artifact_id':uuid4(),'pricing':q})
    x=type(s.context).model_validate(s.context.model_dump(mode='python')|{'job':second,
        'pricing_quote_hash':digest(q.model_dump(mode='json'))})
    xh=write(__import__('pathlib').Path(s.config.context.path),x)
    c=s.config.model_copy(update={'context':s.config.context.model_copy(update={'sha256':xh})})
    ch=write(s.config_path,c);a=appointment(c,ch);ah=write(s.appointment_path,a)
    factory.settings=replace(s,config=c,config_sha256=ch,appointment=a,appointment_sha256=ah,context=x)
    state['job']=second;state['wire']['usage']['cost_details']['upstream_inference_cost']=2
    with pytest.raises(m.RawOriginalOutcomeUnknown):factory.execute()
    with psycopg.connect(url) as conn:
        row=conn.execute('''SELECT r.reservation_id,s.actual_usd,s.status,s.failure_kind,s.response_hash
            FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)
            WHERE r.artifact_id=%s''',(second.artifact_id,)).fetchone()
        assert row[1:]==(Decimal('2.001'),'overrun','transport_failure',None)
    assert wire_locks==[True,True]
    assert state['paid']==2 and factory._path(second,'.wire').exists() and factory._path(second,'.json').exists()
    assert not factory._path(second,'.raw-paid.json').exists()
    with pytest.raises(PermissionError):factory.execute()
    assert state['paid']==2
