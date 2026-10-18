"""Actual existing central ledger caps; synthetic admitted projections only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import time
from uuid import uuid4
import psycopg
from psycopg import sql
import pytest
from test_operating_model_adapters import test_database
from oracle_brain.operating_model.provider_adapter import Budget,AdmittedAllocationLimitV2

PURPOSES=('source-census','operating-audit','independent-source-semantic-acceptance','source-extraction')

def cap(batch=None,amount='.025',expires=None):
    return AdmittedAllocationLimitV2(batch_id=batch or uuid4(),allocation_hash='a'*64,
        original_receipt_hash='b'*64,ceiling_usd=Decimal(amount),
        expires_at=expires or datetime.now(timezone.utc)+timedelta(minutes=1))

def reserve(ledger,limit,purpose='source-census',batch=None):
    return ledger.reserve(workspace_id=uuid4(),artifact_id=uuid4(),batch_id=batch or limit.batch_id,
        purpose=purpose,attempt=1,maximum=Decimal('.01'),pricing_hash='c'*64,account_remaining=Decimal('25'))

@pytest.fixture
def phase_billing_urls(test_database):
    names=['purpose_bill_'+uuid4().hex[:16] for _ in PURPOSES]
    password=uuid4().hex
    with psycopg.connect(test_database) as conn:
        for name in names:
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}').format(sql.Identifier(name),sql.Literal(password)))
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(name)))
            conn.execute(sql.SQL('GRANT SELECT,INSERT ON oracle2.operating_dispatch_reservations,oracle2.operating_dispatch_receipts,oracle2.operating_dispatch_diagnoses TO {}').format(sql.Identifier(name)))
    try:
        yield tuple(psycopg.conninfo.make_conninfo(test_database,user=name,password=password) for name in names)
    finally:
        with psycopg.connect(test_database) as conn:
            for name in names:
                conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(name)))
                conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))


def test_four_phase_distinct_workspaces_share_actual_lower_allocation(test_database,phase_billing_urls):
    limit=cap()
    def run(pair):
        purpose,url=pair
        try:return reserve(Budget(url,admitted_allocation=limit),limit,purpose)
        except PermissionError:return None
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,zip(PURPOSES,phase_billing_urls)))
    assert sum(x is not None for x in results)==2
    with psycopg.connect(test_database) as conn:
        assert conn.execute('SELECT count(*),count(DISTINCT workspace_id),sum(reserved_usd) FROM oracle2.operating_dispatch_reservations').fetchone()==(2,2,Decimal('.02'))
        assert conn.execute('SELECT count(*) FROM oracle2.operating_dispatch_receipts').fetchone()[0]==0

@pytest.mark.parametrize('settled',[False,True])
def test_original_batch_all_history_survives_day_transition_and_unknown_hold(test_database,settled):
    limit=cap(amount='.015');budget=Budget(test_database,admitted_allocation=limit)
    reservation=uuid4()
    # Historical append-only fixture is seeded, never UPDATEd or reset.
    with psycopg.connect(test_database) as conn:
        conn.execute("INSERT INTO oracle2.operating_dispatch_reservations(reservation_id,workspace_id,artifact_id,batch_id,purpose,attempt,reserved_usd,pricing_hash,reserved_at) VALUES(%s,%s,%s,%s,'source-census',1,.01,%s,now()-interval '3 days')",(reservation,uuid4(),uuid4(),limit.batch_id,'c'*64))
        if settled:
            conn.execute("INSERT INTO oracle2.operating_dispatch_receipts(reservation_id,actual_usd,status,response_hash,created_at) VALUES(%s,.001,'completed',%s,now()-interval '3 days')",(reservation,'d'*64))
    with pytest.raises(PermissionError):reserve(Budget(test_database,admitted_allocation=limit),limit,'operating-audit')
    # A new worker/batch cannot reset the original admitted allocation.
    with pytest.raises(PermissionError):reserve(budget,limit,batch=uuid4())


def test_actual_lock_wait_expiry_denies_reservation_but_settlement_remains(test_database):
    limit=cap(expires=datetime.now(timezone.utc)+timedelta(seconds=.4))
    budget=Budget(test_database,admitted_allocation=limit)
    first=reserve(budget,limit)
    tag='purpose_cap_'+uuid4().hex
    url=psycopg.conninfo.make_conninfo(test_database,application_name=tag)
    with psycopg.connect(test_database) as owner:
        owner.execute("SELECT pg_advisory_xact_lock(hashtext('oracle-operating-budget'))")
        pool=ThreadPoolExecutor(max_workers=1)
        future=pool.submit(reserve,Budget(url,admitted_allocation=limit),limit)
        try:
            deadline=time.monotonic()+1
            while True:
                owner.execute('SELECT pg_stat_clear_snapshot()')
                if owner.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event_type='Lock' AND wait_event='advisory')",(tag,)).fetchone()[0]:break
                if time.monotonic()>=deadline:pytest.fail('owned reserve never reached actual budget lock')
                time.sleep(.005)
            owner.execute("SELECT pg_sleep(GREATEST(0,extract(epoch FROM %s::timestamptz-clock_timestamp()))+.01)",(limit.expires_at,))
        finally:
            # Release the owned blocker before joining even on a fixture failure.
            owner.rollback()
            pool.shutdown(wait=True)
        with pytest.raises(PermissionError):future.result(timeout=2)
    # Paid liability is recorded after admission expiry; it is never refunded.
    budget.finish(first,actual_usd=Decimal('.001'),failed=False,response_hash='d'*64)
    with psycopg.connect(test_database) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.operating_dispatch_reservations').fetchone()[0]==1
        assert conn.execute("SELECT status FROM oracle2.operating_dispatch_receipts WHERE reservation_id=%s",(first,)).fetchone()[0]=='completed'
