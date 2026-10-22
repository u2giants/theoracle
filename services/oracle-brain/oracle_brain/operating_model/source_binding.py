"""Externally sealed source-role admission pins; no registry issuance."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import psycopg
from .request_deadline_v1 import sql_execute_current_v1

@dataclass(frozen=True)
class SourceRoleBinding:
    runtime_hash: str
    source_role_registry_hash: str
    synthetic: bool = False

    def __post_init__(self):
        if (any(not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value)
                for value in (self.runtime_hash,self.source_role_registry_hash))
                or type(self.synthetic) is not bool):
            raise PermissionError('independently sealed source-role pins required')

    def check(self, connection):
        parameters=connection.info.get_parameters()
        if not connection.pgconn.ssl_in_use or parameters.get('sslmode')!='verify-full':
            if (not self.synthetic or connection.info.host not in {'127.0.0.1','localhost','::1'}
                    or not (connection.info.dbname.startswith('oracle_operating_model_test')
                            or connection.info.dbname=='oracle2'
                            or connection.info.dbname=='hosting_permissions_test')):
                raise PermissionError('source binding requires authenticated ledger TLS')
        role=sql_execute_current_v1(connection,'SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=SESSION_USER').fetchone()
        if role is None or role[0] or role[1]:
            raise PermissionError('source binding requires a non-bypass source role')
        rows=sql_execute_current_v1(connection,'SELECT runtime_hash,registry_hash,expires_at,clock_timestamp() '
                                'FROM oracle2.hosting_source_runtime_binding()').fetchall()
        if (len(rows)!=1 or rows[0][0]!=self.runtime_hash or rows[0][1]!=self.source_role_registry_hash
                or not isinstance(rows[0][2],datetime) or rows[0][2].tzinfo is None
                or rows[0][2]<=rows[0][3] or rows[0][2]<=datetime.now(timezone.utc)):
            raise PermissionError('current self-role source registry differs from sealed startup')

    def check_url(self, url):
        with psycopg.connect(url,connect_timeout=5) as connection:
            self.check(connection)
