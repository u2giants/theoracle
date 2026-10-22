"""Fixed own SQL027 consumer. No role issuance, source byte reader or retries."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from uuid import UUID
import hashlib
import psycopg

from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.protected_inputs_v1 import _pinned, parse_canonical_object_v1
from oracle_brain.operating_model.protected_sql_connection_v1 import _connection_v1
from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1, sql_execute_v1
from .migration_settings_v1 import MigrationConsumerSettingsV1, SIGNATURES, PRIVATE_NAMES, PUBLIC_NAMES

FLAGS = ('qualification','source_read_authorized','viewer_authorized','dispatch_authorized',
    'consistent_boundary_proven','serving_switch_authorized','shadow_comparison_accepted','company_acceptance')
TABLES = ('migration_admissions_v1','migration_admission_revocations_v1','migration_inventories_v1',
    'migration_inventory_entries_v1','migration_source_bindings_v1','migration_source_versions_v1',
    'migration_heads_v1','migration_intents_v1','migration_events_v1','migration_intent_observations_v1',
    'migration_resolution_events_v1','migration_citation_bindings_v1','migration_capture_observations_v1')


class MigrationOutcomeUnknown(PermissionError):
    """A write may have committed. Exact-command read-only reconciliation only."""


class MigrationAuthorityV1:
    def __init__(self, settings):
        if type(settings) is not MigrationConsumerSettingsV1:
            raise TypeError('exact independently installed migration settings required')
        settings.current()
        self.settings = settings
        c = settings.config
        self.url = _pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf8')
        self.params = psycopg.conninfo.conninfo_to_dict(self.url)
        allowed = {'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','application_name'}
        if (set(self.params)-allowed or any(not self.params.get(k) for k in ('host','port','dbname','user','password'))
                or self.params['user'] != c.session_role or self.params.get('sslmode') != 'verify-full'
                or self.params.get('sslrootcert') != c.database_ca.path):
            raise PermissionError('exact independently pinned migration SQL target required')

    def _time(self, deadline):
        bound = self.settings.current()
        now = datetime.now(timezone.utc)
        if (type(deadline) is not datetime or deadline.tzinfo is None or deadline.utcoffset() != timedelta(0)
                or not now < deadline <= min(bound,now+timedelta(seconds=30))):
            raise PermissionError('same original bounded migration deadline required')
        return min((deadline-now).total_seconds(),request_remaining_v1())

    def _execute(self, connection, deadline, query, params=()):
        self._time(deadline)
        value = sql_execute_v1(connection,deadline,query,params)
        self._time(deadline)
        return value

    def _check(self, connection, deadline):
        c = self.settings.config
        self._time(deadline)
        actual=connection.info.get_parameters()
        if (any(str(actual.get(k,''))!=str(self.params.get(k,'')) for k in ('host','dbname','user','sslmode','sslrootcert'))
                or connection.info.hostaddr != (self.params.get('hostaddr') or self.params['host'])
                or not connection.pgconn.ssl_in_use or connection.info.host != self.params['host']
                or connection.info.port != int(self.params['port']) or connection.info.dbname != self.params['dbname']):
            raise PermissionError('actual migration target/TLS changed')
        if self._execute(connection,deadline,'SELECT SESSION_USER,current_user,current_database()').fetchone() != (c.session_role,c.session_role,self.params['dbname']):
            raise PermissionError('actual fixed migration LOGIN required')
        rows = self._execute(connection,deadline,"""SELECT n.nspname,p.proname,r.rolname,p.prosecdef,p.proconfig,
          encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),
          encode(sha256(convert_to(coalesce((SELECT string_agg(grantee::text||':'||privilege_type||':'||is_grantable::text,',' ORDER BY grantee,privilege_type,is_grantable)
            FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner)))),'') ,'UTF8')),'hex'),
          coalesce((SELECT jsonb_agg(jsonb_build_object('role',CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,'privilege',x.privilege_type,'grantable',x.is_grantable))
            FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x),'[]'::jsonb)
          FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE p.oid IN(SELECT to_regprocedure(x) FROM unnest(%s::text[]) x)""",
          (['oracle2.'+s for s in SIGNATURES],)).fetchall()
        pins = {name:(body,acl) for name,body,acl in c.capability_fingerprints}
        roles = dict(c.public_capability_roles)
        if len(rows) != len(SIGNATURES) or {r[1] for r in rows} != set(pins):
            raise PermissionError('complete exact migration catalog required')
        for namespace,name,owner,security,search_path,body,acl,entries in rows:
            expected_security = name != '_migration_binding_once_v1'
            if (namespace != 'oracle2' or owner != c.expected_owner or security is not expected_security
                    or search_path != ['search_path=pg_catalog, oracle2'] or (body,acl) != pins[name]):
                raise PermissionError('migration catalog owner/body/ACL/search_path changed')
            if name in PRIVATE_NAMES or name in PUBLIC_NAMES:
                expected_roles = {c.expected_owner} | (set(roles[name]) if name in PUBLIC_NAMES else set())
                if ({e['role'] for e in entries} != expected_roles
                        or any(e['privilege'] != 'EXECUTE' or e['role'] != c.expected_owner and e['grantable'] is not False for e in entries)):
                    raise PermissionError('migration capability has unsafe ACL')
        tables = self._execute(connection,deadline,"""SELECT c.relname,pg_get_userbyid(c.relowner),c.relrowsecurity,
          has_table_privilege(SESSION_USER,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='oracle2' AND c.relname=ANY(%s::text[])""",(list(TABLES),)).fetchall()
        if (len(tables) != len(TABLES) or {r[0] for r in tables} != set(TABLES)
                or any(owner != c.expected_owner or rls is not True or direct is not False for _,owner,rls,direct in tables)):
            raise PermissionError('migration private owner/RLS/direct table access changed')

    @contextmanager
    def _connection(self, deadline):
        self._time(deadline)
        with _connection_v1(self.url,deadline) as connection:
            self._check(connection,deadline)
            yield connection
            self._check(connection,deadline)
        # Actual socket closed before delivery/private callbacks/other plane.
        self._time(deadline)

    def _args(self, deadline):
        c = self.settings.config
        return (c.admission_id,c.runtime_sha256,c.registry_sha256,self.settings.config_sha256,deadline)

    def _result(self, result, deadline):
        self._time(deadline)
        if type(result) is not dict or type(result.get('schema_version')) is not int or result.get('schema_version') != 1 or any(result.get(k) is not False for k in FLAGS):
            raise PermissionError('closed control-only migration result required')
        try:
            until = datetime.fromisoformat(result['valid_until'])
        except (KeyError,TypeError,ValueError):
            raise PermissionError('finite actual SQL result window required') from None
        if not datetime.now(timezone.utc) < until <= min(deadline,self.settings.config.original_horizon):
            raise PermissionError('actual migration result expired or renewed')
        return result

    def _read(self, function, extra, deadline):
        query = 'SELECT oracle2.'+function+'('+','.join(['%s']*(5+len(extra)))+')'
        with self._connection(deadline) as connection:
            result = self._execute(connection,deadline,query,self._args(deadline)+extra).fetchone()[0]
        return self._result(result,deadline)

    def source_context_v1(self, *, caller_deadline):
        if self.settings.config.operation != 'snapshot-register':
            raise PermissionError('own current snapshot/export consumer required')
        result = self._read('current_migration_v1',(None,),caller_deadline)
        c = self.settings.config
        if (result.get('operation') != 'source-export-context' or
                tuple(str(result.get(k)) for k in ('principal_id','workspace_id','origin_system','descriptor_sha256','source_scope_sha256','source_program_sha256','intake_principal_id','intake_config_sha256')) !=
                tuple(str(getattr(c,k)) for k in ('principal_id','workspace_id','origin_system','descriptor_sha256','source_scope_sha256','source_program_sha256','intake_principal_id','intake_config_sha256'))):
            raise PermissionError('actual source/export context differs from independent install')
        return result

    def status_v1(self, inventory_id, *, caller_deadline):
        if self.settings.config.operation != 'read' or type(inventory_id) is not UUID:
            raise PermissionError('own fixed inventory read required')
        result = self._read('current_migration_v1',(inventory_id,),caller_deadline)
        if result.get('inventory_id') != str(inventory_id):
            raise PermissionError('actual inventory selector mismatch')
        return result

    def reconcile_v1(self, command_id, *, caller_deadline):
        if self.settings.config.operation != 'reconcile' or type(command_id) is not UUID:
            raise PermissionError('own exact-command receipt reader required')
        result = self._read('reconcile_migration_command_v1',(command_id,),caller_deadline)
        if (result.get('command_id') != str(command_id) or result.get('receipt_read_only') is not True
                or result.get('write_authorized') is not False or result.get('resend_authorized') is not False):
            raise PermissionError('receipt cannot grant replay or unrelated operation')
        return result

    def _write(self, function, extra, command_id, receipt, deadline):
        if type(command_id) is not UUID or type(receipt) is not MigrationAuthorityV1:
            raise TypeError('exact independently admitted receipt reader required')
        c,r = self.settings.config,receipt.settings.config
        if (r.operation != 'reconcile' or r.session_role == c.session_role
                or (c.principal_id,c.workspace_id,c.origin_system) != (r.principal_id,r.workspace_id,r.origin_system)):
            raise PermissionError('separate same-principal own receipt consumer required')
        query = 'SELECT oracle2.'+function+'('+','.join(['%s']*(6+len(extra)))+')'
        attempted = False
        try:
            with self._connection(deadline) as connection:
                attempted = True
                result = self._execute(connection,deadline,query,self._args(deadline)+extra+(command_id,)).fetchone()[0]
            result = self._result(result,deadline)
            if result.get('command_id') != str(command_id):
                raise PermissionError('actual exact operation identity differs')
            # ALL failures after possible commit, including scope revoke, actual
            # close or second readonly connection loss, remain typed UNKNOWN.
            current = receipt.reconcile_v1(command_id,caller_deadline=deadline)
            if (current.get('event_id'),current.get('inventory_id'),current.get('sequence')) != (result.get('event_id'),result.get('inventory_id'),result.get('sequence')):
                raise PermissionError('fresh exact operation receipt mismatch')
            if current.get('original_writer_scope_current') is not True or current.get('original_operation_window_unexpired') is not True:
                raise PermissionError('original write scope/window no longer current')
            self._time(deadline)
            return result
        except BaseException:
            if attempted:
                raise MigrationOutcomeUnknown('Migration outcome unknown; reconcile the exact command read-only; never resend') from None
            raise

    def register_v1(self, inventory_bytes, command_id, receipt, *, caller_deadline):
        if self.settings.config.operation != 'snapshot-register':
            raise PermissionError('own snapshot registration required')
        parse_canonical_object_v1(inventory_bytes,limit=64*1024*1024)
        return self._write('register_migration_inventory_v1',(inventory_bytes,),command_id,receipt,caller_deadline)

    def prepare_v1(self, inventory_id, expected_head, command_id, receipt, *, caller_deadline):
        if (self.settings.config.operation != 'batch-prepare' or type(inventory_id) is not UUID
                or type(expected_head) is not int or expected_head < 0):
            raise PermissionError('own exact batch CAS required')
        return self._write('prepare_migration_batch_v1',(inventory_id,expected_head),command_id,receipt,caller_deadline)

    def observe_v1(self, intent_id, intake_config_sha256, command_id, receipt, *, caller_deadline):
        if self.settings.config.operation != 'batch-observe' or type(intent_id) is not UUID:
            raise PermissionError('own installed observation role required')
        raw = canonical_bytes({'schema_version':1,'intake_config_sha256':intake_config_sha256})
        return self._write('observe_migration_intake_v1',(intent_id,raw),command_id,receipt,caller_deadline)

    def resolve_v1(self, failure_event, evidence_receipt, expected_head, command_id, receipt, *, caller_deadline):
        if (self.settings.config.operation != 'batch-observe' or type(failure_event) is not UUID
                or type(evidence_receipt) is not UUID or type(expected_head) is not int or expected_head < 0):
            raise PermissionError('own evidence-bound resolution CAS required')
        return self._write('record_migration_resolution_v1',(failure_event,evidence_receipt,expected_head),command_id,receipt,caller_deadline)

    def citation_metadata_v1(self, inventory_id, legacy_citation_id, *, caller_deadline):
        if (self.settings.config.operation != 'citation-read' or type(inventory_id) is not UUID
                or type(legacy_citation_id) is not str or not 1 <= len(legacy_citation_id) <= 256):
            raise PermissionError('own exact citation mapping consumer required')
        result = self._read('resolve_migration_citation_v1',(legacy_citation_id,inventory_id),caller_deadline)
        if result.get('independent_viewer_check_required') is not True or result.get('inventory_id') != str(inventory_id):
            raise PermissionError('citation mapping cannot substitute for original viewer')
        return result
