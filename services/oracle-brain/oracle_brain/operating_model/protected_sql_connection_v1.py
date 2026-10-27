"""Single prearmed protected SQL connection owner; no identity/DDL/semantic grant.

Extracted from reviewed S09 b002 connection body; explicit target/environment
restrictions are an additive owned repair. Every consumer
retains its separate fixed role/currentness/catalog checks. Legacy APIs may opt
in only by supplying their actual original deadline; no renewal or retry.
"""
from contextlib import contextmanager
import psycopg
from .request_deadline_v1 import (sql_remaining_v1 as _sql_remaining_v1,
    sql_execute_v1 as _execute_v1,_sql_window_v1,_sql_send_window_v1,
    request_remaining_v1,_sql_windows_v1)


def require_protected_sql_window_v1(connection):
    """Restriction only. An existing request cannot borrow an uncaptured socket."""
    if request_remaining_v1(required=False) is None:
        return
    matching = [window for window in _sql_windows_v1.get() if window.connection is connection]
    if len(matching) != 1:
        raise PermissionError('actual original prearmed SQL connection required')
    _sql_send_window_v1(connection, matching[0].deadline)


@contextmanager
def _connection_v1(url,deadline,*,require_pinned_address=False):
    import ipaddress
    import os
    from pathlib import Path
    if any(key.startswith("PG") for key in os.environ):
        raise PermissionError("protected SQL cannot consume PG environment defaults")
    params=psycopg.conninfo.conninfo_to_dict(url)
    allowed={'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout','application_name'}
    if (set(params)-allowed or not all(params.get(k) for k in ('host','port','dbname','user','password','sslmode','sslrootcert'))
            or not Path(params.get('sslrootcert','')).is_absolute() or not params.get('host') or require_pinned_address and not params.get('hostaddr')
            or any(',' in params.get(k,'') for k in ('host','hostaddr','port'))
            or params.get('sslmode')!='verify-full' or not params.get('port','5432').isdigit()):
        raise PermissionError('one explicitly pinned verify-full host/address/port target required')
    try:
        address=ipaddress.ip_address(params.get('hostaddr') or params['host'])
        if str(address)!=(params.get('hostaddr') or params['host']):
            raise ValueError('noncanonical address')
    except ValueError:raise PermissionError('one pinned numeric SQL address required') from None
    remaining=_sql_remaining_v1(deadline)
    # Exact installed psycopg timeout_from_conninfo enforces libpq minimum2s.
    # https://www.postgresql.org/docs/16/libpq-connect.html#LIBPQ-PARAMKEYWORDS
    if remaining<=2.002:raise PermissionError('original SQL window cannot fit the supported two-second connection bound')
    first=max(1,min(2000,int((remaining-2-.001)*1000)))
    options=f'-c statement_timeout={first}ms -c lock_timeout={min(first,2000)}ms'
    # An implicit psycopg BEGIN followed by the first query would be two sends
    # behind one guard. Start exactly one explicit transaction instead. Actual
    # psycopg __exit__ commits explicit BEGIN even with autocommit=True.
    with psycopg.connect(url,host=params['host'],hostaddr=str(address),port=params['port'],dbname=params['dbname'],user=params['user'],sslmode=params['sslmode'],sslrootcert=params['sslrootcert'],connect_timeout=2,tcp_user_timeout=max(1,int(min(2,remaining-2)*1000)),options=options,autocommit=True) as connection:
        with _sql_window_v1(connection,deadline,armed_timeout_ms=first):
            _sql_send_window_v1(connection,deadline)
            _execute_v1(connection,deadline,'BEGIN ISOLATION LEVEL READ COMMITTED')
            yield connection
            # The transaction context's COMMIT is also a send under the
            # already armed timeout. Refusal propagates UNKNOWN for writes.
            _sql_send_window_v1(connection,deadline)
    _sql_remaining_v1(deadline)

