"""Actual fixed recommendation SQL consumer; no role or appointment issuance."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import ipaddress
from uuid import UUID
import psycopg

from ..protected_inputs_v1 import _pinned
from ..request_deadline_v1 import request_remaining_v1
from ..request_deadline_v1 import sql_execute_v1
from ..protected_sql_connection_v1 import _connection_v1
from .recommendation_actions_v1 import RecommendationSelectorV1, FeedbackCommandV1, MeasurementCommandV1

FUNCTIONS = (
 '_recommendation_action_context_v1(uuid,text,text,text,text,timestamptz,boolean)',
 '_recommendation_current_sources_v1(oracle2.recommendation_action_admissions_v1,jsonb)',
 '_recommendation_registration_current_v1(oracle2.recommendation_action_admissions_v1,uuid,integer)',
 'register_recommendation_actions_v1(uuid,integer,bytea,bytea,uuid,text,text,text,timestamptz)',
 '_recommendation_own_status_v1(oracle2.recommendation_action_admissions_v1,uuid,integer,uuid)',
 'read_recommendation_actions_v1(uuid,integer,uuid,uuid,text,text,text,timestamptz)',
 'list_recommendation_actions_v1(uuid,text,text,text,timestamptz)',
 '_recommendation_command_v1(bytea,text)',
 '_recommendation_append_v1(oracle2.recommendation_action_admissions_v1,jsonb,bytea,text,jsonb)',
 '_recommendation_receipt_v1(oracle2.recommendation_action_admissions_v1,uuid,integer,uuid,uuid)',
 'reconcile_recommendation_action_v1(uuid,integer,uuid,uuid,uuid,text,text,text,timestamptz)',
 'record_recommendation_feedback_v1(bytea,uuid,text,text,text,timestamptz)',
 'record_recommendation_measurement_v1(bytea,bytea,uuid,text,text,text,timestamptz)',
 '_processing_immutable_artifact_metadata_v1(uuid,uuid,integer,jsonb)',
)
PRIVATE = frozenset(s.split('(')[0] for s in FUNCTIONS if s.startswith('_'))
PUBLIC = {'read': 'read_recommendation_actions_v1', 'register': 'register_recommendation_actions_v1',
          'feedback': 'record_recommendation_feedback_v1', 'measurement': 'record_recommendation_measurement_v1'}


class RecommendationOutcomeUnknown(PermissionError):
    """Possible write/commit completed; read-only reconciliation, never resend."""

class RecommendationActionRefused(PermissionError):
    """Deterministic never-written refusal. No write occurred; this command_id
    was not stored and reconcile will never succeed. Not UNKNOWN."""


@dataclass(frozen=True)
class RecommendationBindingV1:
    appointment_id: UUID
    principal_id: UUID
    workspace_id: UUID
    model_id: UUID
    operation: str
    session_login: str
    expected_owner: str
    runtime_hash: str
    registry_hash: str
    config_hash: str
    ca_path: str
    ca_sha256: str
    original_horizon: datetime
    # Full independently pinned catalog, including all public ACLs. The runtime
    # never derives a pin from whatever database it happened to connect to.
    capability_fingerprints: tuple[tuple[str, str, str], ...]

    def __post_init__(self):
        import re
        expected = {s.split('(')[0] for s in FUNCTIONS}
        if (self.operation not in PUBLIC or any(type(v) is not UUID for v in
                (self.appointment_id, self.principal_id, self.workspace_id, self.model_id))
                or self.session_login == self.expected_owner or not self.session_login or not self.expected_owner
                or self.original_horizon.tzinfo is None or self.original_horizon.utcoffset() is None
                or type(self.capability_fingerprints) is not tuple
                or any(type(row) is not tuple or len(row) != 3 for row in self.capability_fingerprints)
                or {row[0] for row in self.capability_fingerprints} != expected
                or len(self.capability_fingerprints) != len(expected)
                or any(not re.fullmatch('[a-f0-9]{64}', value) for value in
                    (self.runtime_hash, self.registry_hash, self.config_hash, self.ca_sha256,
                     *(value for row in self.capability_fingerprints for value in row[1:])))):
            raise PermissionError('complete independently pinned recommendation consumer required')


class RecommendationAuthorityV1:
    def __init__(self, url, *, binding):
        if type(binding) is not RecommendationBindingV1:
            raise TypeError('exact fixed recommendation consumer required')
        params = psycopg.conninfo.conninfo_to_dict(url)
        allowed = {'user','password','dbname','host','hostaddr','port','sslmode','sslrootcert','application_name'}
        if (set(params)-allowed or any(not params.get(k) for k in ('user','dbname','host','port','password'))
                or params['user'] != binding.session_login or params.get('sslmode') != 'verify-full'
                or params.get('sslrootcert') != binding.ca_path or ',' in params['host']
                or ',' in params['port'] or not params['port'].isdigit()):
            raise PermissionError('one exact pinned verify-full recommendation SQL target required')
        try:
            ipaddress.ip_address(params.get('hostaddr') or params['host'])
        except ValueError:
            raise PermissionError('single numeric host or independently pinned numeric hostaddr required') from None
        self.url, self.binding, self.params = url, binding, params
        _pinned(binding.ca_path, binding.ca_sha256)

    def _time(self, deadline):
        now = datetime.now(timezone.utc)
        if (not isinstance(deadline, datetime) or deadline.tzinfo is None or deadline.utcoffset() is None
                or deadline <= now or deadline > self.binding.original_horizon or deadline > now+timedelta(seconds=30)):
            raise PermissionError('same original finite recommendation deadline required')
        remaining = min((deadline-now).total_seconds(), request_remaining_v1())
        if remaining <= 0:
            raise PermissionError('original recommendation window elapsed')
        return remaining

    def _execute(self, connection, query, params, deadline):
        self._time(deadline)
        result = sql_execute_v1(connection, deadline, query, params)
        self._time(deadline)
        return result

    def _check(self, connection, deadline):
        self._time(deadline); b = self.binding
        _pinned(b.ca_path,b.ca_sha256)
        if (not connection.pgconn.ssl_in_use or connection.info.host != self.params['host']
                or connection.info.port != int(self.params['port']) or connection.info.dbname != self.params['dbname']):
            raise PermissionError('actual recommendation SQL target or TLS changed')
        if self._execute(connection,'SELECT SESSION_USER,current_user,current_database()',(),deadline).fetchone() != (b.session_login,b.session_login,self.params['dbname']):
            raise PermissionError('actual fixed recommendation login required')
        rows = self._execute(connection,'''SELECT n.nspname,p.proname,r.rolname,p.prosecdef,p.proconfig,
            encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),
            encode(sha256(convert_to(coalesce((SELECT string_agg(grantee::text||':'||privilege_type||':'||is_grantable::text,',' ORDER BY grantee,privilege_type,is_grantable)
              FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner)))),'') ,'UTF8')),'hex'),
            NOT EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x WHERE x.grantee<>p.proowner)
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
            WHERE p.oid IN(SELECT to_regprocedure(x) FROM unnest(%s::text[]) x)''',
            (['oracle2.'+signature for signature in FUNCTIONS],),deadline).fetchall()
        expected={name:(body,acl) for name,body,acl in b.capability_fingerprints}
        if (len(rows)!=len(FUNCTIONS) or {row[1] for row in rows}!=set(expected)
                or any(namespace!='oracle2' or owner!=b.expected_owner or security is not True
                    or settings!=['search_path=pg_catalog, oracle2'] or (body,acl)!=expected[name]
                    or name in PRIVATE and private is not True
                    for namespace,name,owner,security,settings,body,acl,private in rows)):
            raise PermissionError('exact recommendation capability owner/body/ACL catalog changed')

    @contextmanager
    def _connection(self, deadline, *, _runtime_recheck=None):
        self._time(deadline)
        with _connection_v1(self.url,deadline) as connection:
            self._check(connection,deadline)
            yield connection
            self._check(connection,deadline)
            if _runtime_recheck is not None:_runtime_recheck()
            self._time(deadline)
        self._time(deadline);_pinned(self.binding.ca_path,self.binding.ca_sha256)
        if _runtime_recheck is not None:_runtime_recheck()

    def _args(self, deadline):
        b=self.binding
        return (b.appointment_id,b.runtime_hash,b.registry_hash,b.config_hash,deadline)

    def _result(self, result, deadline):
        self._time(deadline)
        field='validUntil' if 'validUntil' in result else 'valid_until'
        until=datetime.fromisoformat(result[field])
        if not datetime.now(timezone.utc)<until<=min(deadline,self.binding.original_horizon):
            raise PermissionError('recommendation response currentness expired')
        return result

    def list_v1(self, *, deadline, _runtime_recheck=None):
        if self.binding.operation!='read':raise PermissionError('own independently appointed read consumer required')
        with self._connection(deadline,_runtime_recheck=_runtime_recheck) as connection:
            result=self._execute(connection,'SELECT oracle2.list_recommendation_actions_v1(%s,%s,%s,%s,%s)',self._args(deadline),deadline).fetchone()[0]
        if (result.get('kind')!='recommendation-index-v1' or type(result.get('selectors')) is not list
                or len(result['selectors'])>64 or type(result.get('coverage_gap')) is not bool
                or result.get('list_complete') is not (not result['coverage_gap'])):
            raise PermissionError('bounded current permitted advice index required')
        for selector in result['selectors']:
            from ..contracts import canonical_bytes
            RecommendationSelectorV1.model_validate_json(canonical_bytes(selector))
        return self._result(result,deadline)

    def read_v1(self, selector, *, deadline, _runtime_recheck=None):
        if self.binding.operation!='read' or type(selector) is not RecommendationSelectorV1:
            raise PermissionError('own fixed read consumer required')
        with self._connection(deadline,_runtime_recheck=_runtime_recheck) as connection:
            result=self._execute(connection,'SELECT oracle2.read_recommendation_actions_v1(%s,%s,%s,%s,%s,%s,%s,%s)',
                (selector.artifact_id,selector.artifact_version,selector.recommendation_id,*self._args(deadline)),deadline).fetchone()[0]
        if not result['redacted'] and result['context']['manifest']['content_hash']!=selector.artifact_sha256:
            raise PermissionError('exact selected recommendation body changed')
        return self._result(result,deadline)

    def reconcile_v1(self, artifact, version, recommendation, command, *, deadline, _runtime_recheck=None):
        if self.binding.operation not in {'register','feedback','measurement'}:
            raise PermissionError('same own operation receipt consumer required')
        with self._connection(deadline,_runtime_recheck=_runtime_recheck) as connection:
            result=self._execute(connection,'SELECT oracle2.reconcile_recommendation_action_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (artifact,version,recommendation,command,*self._args(deadline)),deadline).fetchone()[0]
        return self._result(result,deadline)

    def _write(self, query, params, *, deadline, selector, command_id, _runtime_recheck=None):
        attempted=False;complete=False
        try:
            with self._connection(deadline,_runtime_recheck=_runtime_recheck) as connection:
                attempted=True
                result=self._execute(connection,query,params,deadline).fetchone()[0]
                self._result(result,deadline);complete=True
            # A new actual connection after commit+close, with SAME own role.
            # This reads an immutable receipt; it never repeats the writer.
            fresh=self.reconcile_v1(*selector,command_id,deadline=deadline,_runtime_recheck=_runtime_recheck)
            if (fresh['stale'] or fresh['redacted']
                    or {k:v for k,v in fresh.items() if k!='valid_until'}!={k:v for k,v in result.items() if k!='valid_until'}):
                raise PermissionError('committed recommendation receipt no longer current')
            return self._result(fresh,deadline)
        except (psycopg.errors.SerializationFailure,psycopg.errors.UniqueViolation,psycopg.errors.InsufficientPrivilege,psycopg.errors.InvalidParameterValue) as error:
            if complete:raise RecommendationOutcomeUnknown('recommendation write may be committed; read-only reconcile, no resend') from None
            if attempted:raise RecommendationActionRefused(f'never-written recommendation action refused: {error}') from error
            raise
        except Exception as error:
            if complete:raise RecommendationOutcomeUnknown('recommendation write outcome UNKNOWN; read-only reconcile, no resend') from None
            if attempted:raise RecommendationActionRefused(f'never-written recommendation action refused: {error}') from error
            raise

    def feedback_v1(self, command, raw, *, _runtime_recheck=None):
        if self.binding.operation!='feedback' or type(command) is not FeedbackCommandV1:
            raise PermissionError('separate fixed personal feedback consumer required')
        from ..contracts import canonical_bytes
        if canonical_bytes(command.model_dump(mode='json'))!=raw:raise ValueError('exact original feedback bytes required')
        return self._write('SELECT oracle2.record_recommendation_feedback_v1(%s,%s,%s,%s,%s,%s)',
            (raw,*self._args(command.caller_deadline)),deadline=command.caller_deadline,
            selector=(command.selector.artifact_id,command.selector.artifact_version,command.selector.recommendation_id),command_id=command.command_id,_runtime_recheck=_runtime_recheck)

    def measurement_v1(self, command, raw, assertion_bytes, *, _runtime_recheck=None):
        if self.binding.operation!='measurement' or type(command) is not MeasurementCommandV1:
            raise PermissionError('separate fixed source measurement consumer required')
        from ..contracts import canonical_bytes
        if canonical_bytes(command.model_dump(mode='json'))!=raw:raise ValueError('exact original measurement command required')
        return self._write('SELECT oracle2.record_recommendation_measurement_v1(%s,%s,%s,%s,%s,%s,%s)',
            (raw,assertion_bytes,*self._args(command.caller_deadline)),deadline=command.caller_deadline,
            selector=(command.selector.artifact_id,command.selector.artifact_version,command.selector.recommendation_id),command_id=command.command_id,_runtime_recheck=_runtime_recheck)

    def register_v1(self, manifest, payload_bytes, parent_bytes, *, deadline, _runtime_recheck=None):
        if self.binding.operation!='register':raise PermissionError('separately appointed canonical compiler registration required')
        return self._write('SELECT oracle2.register_recommendation_actions_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (manifest.artifact_id,manifest.version,payload_bytes,parent_bytes,*self._args(deadline)),
            deadline=deadline,selector=(manifest.artifact_id,manifest.version,None),command_id=None,_runtime_recheck=_runtime_recheck)
