"""Read-only synthetic TLS catalog regression. Never installs or alters SQL."""
import os
import psycopg
from psycopg.pq import TransactionStatus
import pytest
from oracle_brain.operating_model.q2b_target_catalog_v1 import (
    Q2bExpectedPins, read_target_catalog,
)


@pytest.fixture
def metadata_target():
    if (not os.environ.get('ORACLE2_TEST_TLS_QUALIFICATION')
            or not os.environ.get('ORACLE2_SYNTHETIC_POSTGRES_CONTAINER')):
        pytest.skip('owned invented-data TLS metadata target not configured')
    url = os.environ.get('ORACLE2_TEST_ADMIN_URL')
    if not url:
        pytest.fail('owned synthetic metadata target URL required')
    with psycopg.connect(url, autocommit=True) as connection:
        params = connection.info.get_parameters()
        assert params['host'] in ('127.0.0.1', 'localhost', '::1')
        assert params['sslmode'] == 'verify-full' and connection.pgconn.ssl_in_use
        signature, owner = connection.execute(
            "SELECT p.oid::regprocedure::text, pg_get_userbyid(p.proowner) "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='oracle2' ORDER BY p.oid LIMIT 1"
        ).fetchone()
        user = connection.info.user
        pins = Q2bExpectedPins(
            function_signatures=(signature,), expected_owner_role=owner,
            expected_session_role=user, expected_execute_grants=((signature, ()),),
            role_scope=tuple(sorted({owner, user})), expected_host=params['host'],
            expected_port=int(params['port']), expected_dbname=params['dbname'],
            expected_user=user, expected_sslmode='verify-full')
        yield connection, pins


def test_actual_idle_autocommit_catalog_read_stays_unadmitted(metadata_target):
    connection, pins = metadata_target
    receipt = read_target_catalog(connection, pins)
    assert receipt.admitted is False and receipt.fact_mac == ''
    assert connection.info.transaction_status is TransactionStatus.IDLE


@pytest.mark.parametrize('isolation', ['REPEATABLE READ', 'SERIALIZABLE'])
def test_actual_preexisting_readonly_snapshot_refused(metadata_target, isolation):
    connection, pins = metadata_target
    # Only transaction controls and metadata SELECTs; no catalog/data mutation.
    connection.execute('BEGIN ISOLATION LEVEL ' + isolation + ' READ ONLY')
    snapshot = connection.execute('SELECT pg_current_snapshot()::text').fetchone()[0]
    assert connection.info.transaction_status is TransactionStatus.INTRANS
    with pytest.raises(PermissionError, match='idle autocommit'):
        read_target_catalog(connection, pins)
    assert connection.info.transaction_status is TransactionStatus.INTRANS
    assert connection.execute('SELECT pg_current_snapshot()::text').fetchone()[0] == snapshot
    connection.rollback()


def test_actual_nonautocommit_idle_connection_refused(metadata_target):
    connection, pins = metadata_target
    connection.autocommit = False
    assert connection.info.transaction_status is TransactionStatus.IDLE
    with pytest.raises(PermissionError, match='idle autocommit'):
        read_target_catalog(connection, pins)
    assert connection.info.transaction_status is TransactionStatus.IDLE
