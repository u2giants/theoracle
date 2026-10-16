"""One retained PostgreSQL budget across isolated synthetic purpose processes."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4
import json
import psycopg
import pytest
from test_operating_model_adapters import test_database
from oracle_brain.operating_model.provider_adapter import Budget

PURPOSES=('source-census','operating-audit','independent-source-semantic-acceptance','source-extraction')

def test_all_phases_reserve_settle_one_actual_central_ledger(test_database):
    shared_identity='a'*64
    ledgers=[Budget(test_database,ledger_identity_hash=shared_identity) for _ in PURPOSES]
    reservations=[]
    for ledger,purpose in zip(ledgers,PURPOSES):
        rid=ledger.reserve(workspace_id=uuid4(),artifact_id=uuid4(),batch_id=uuid4(),purpose=purpose,
            attempt=1,maximum=Decimal('.001'),pricing_hash='b'*64,account_remaining=Decimal('25'))
        reservations.append(rid)
        ledger.finish(rid,actual_usd=Decimal('.0005'),failed=False,response_hash='c'*64)
    with psycopg.connect(test_database) as conn:
        rows=conn.execute('SELECT r.purpose,s.status,r.reserved_usd,s.actual_usd FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchall()
        assert {r[0] for r in rows}==set(PURPOSES) and len(rows)==4
        assert all(r[1:] == ('completed',Decimal('.001'),Decimal('.0005')) for r in rows)
        metadata=conn.execute('SELECT row_to_json(r)::text FROM oracle2.operating_dispatch_reservations r UNION ALL SELECT row_to_json(s)::text FROM oracle2.operating_dispatch_receipts s').fetchall()
        for row in metadata:
            fields=json.loads(row[0])
            assert not set(fields)&{'request','messages','reading','raw_response','candidate','parent_registry','provider_key'}
    with pytest.raises(PermissionError):
        ledgers[0].reserve(workspace_id=uuid4(),artifact_id=uuid4(),batch_id=uuid4(),purpose=PURPOSES[0],attempt=1,maximum=Decimal('.001'),pricing_hash='b'*64,account_remaining=Decimal('.004'))


def test_isolated_phase_clients_share_actual_account_lock_and_ceiling(test_database):
    def reserve(purpose):
        try:
            return Budget(test_database,ledger_identity_hash='a'*64).reserve(workspace_id=uuid4(),artifact_id=uuid4(),batch_id=uuid4(),purpose=purpose,attempt=1,maximum=Decimal('.01'),pricing_hash='b'*64,account_remaining=Decimal('.025'))
        except PermissionError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(reserve,PURPOSES))
    assert sum(r is not None for r in results)==2
    with psycopg.connect(test_database) as conn:
        assert conn.execute('SELECT count(*),sum(reserved_usd) FROM oracle2.operating_dispatch_reservations').fetchone()==(2,Decimal('.02'))
        assert conn.execute('SELECT count(*) FROM oracle2.operating_dispatch_receipts').fetchone()[0]==0
