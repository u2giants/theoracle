"""Fixed own-role durable participation SQL consumer. Never sends or issues authority.

A committed claim's body is one-use data. Any lost write/close/current readback
becomes UNKNOWN and cannot be used as permission to resend a provider request.
"""
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import UUID
import hashlib
import ipaddress
import os
import re
import stat
from typing import Callable

import psycopg
from psycopg.types.json import Jsonb
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.protected_sql_connection_v1 import _connection_v1
from oracle_brain.operating_model.request_deadline_v1 import sql_execute_v1

_PUBLIC = (
    'meeting_capture_current_turn_v1(uuid,text,uuid,timestamp with time zone)',
    'meeting_participation_observe_audience_v1(uuid,text,integer,uuid,jsonb,timestamp with time zone)',
    'meeting_participation_control_v1(uuid,text,integer,uuid,text,jsonb,timestamp with time zone)',
    'meeting_participation_prepare_v1(uuid,text,integer,uuid,jsonb,jsonb,timestamp with time zone)',
    'meeting_participation_claim_v1(uuid,text,uuid,integer,uuid,timestamp with time zone)',
    'meeting_participation_observe_v1(uuid,text,uuid,uuid,uuid,jsonb,timestamp with time zone)',
    'meeting_participation_status_v1(uuid,text,uuid,timestamp with time zone)',
)
_PRIVATE = (
    '_replacement_request_context()',
    '_replacement_private_context(oracle2.hosting_request_principal_admissions,timestamp with time zone)',
    '_replacement_metadata_json(jsonb)',
    '_meeting_capture_admission_v1(uuid,text,text,timestamp with time zone)',
    '_meeting_capture_lineage_v1(oracle2.meeting_capture_admissions_v1)',
    '_meeting_participant_epoch_current_v1(oracle2.meeting_capture_admissions_v1,timestamp with time zone)',
    '_meeting_workspace_actor_current_v1(uuid,uuid,timestamp with time zone)',
    '_meeting_capture_current_v1(uuid,text,timestamp with time zone)',
    '_meeting_participation_turn_v1(oracle2.meeting_participation_admissions_v1,uuid,jsonb,timestamp with time zone)',
    '_meeting_participation_admission_v1(uuid,text,text,timestamp with time zone)',
    '_meeting_participation_lineage_v1(oracle2.meeting_participation_admissions_v1)',
    '_meeting_participation_peer_current_v1(oracle2.meeting_participation_admissions_v1,text)',
    '_meeting_participation_host_v1(oracle2.meeting_participation_admissions_v1,integer,timestamp with time zone)',
    '_meeting_participation_prepare_binding_v1(oracle2.meeting_participation_admissions_v1,oracle2.meeting_participation_heads_v1,timestamp with time zone)',
    '_meeting_participation_capture_v1(oracle2.meeting_participation_admissions_v1,timestamp with time zone)',
    '_meeting_participation_observation_v1(oracle2.meeting_participation_admissions_v1,uuid,jsonb,timestamp with time zone)',
    '_meeting_participation_current_v1(oracle2.meeting_participation_admissions_v1,uuid,timestamp with time zone)',
    '_meeting_participation_revoke_lock_v1()',
)
CAPABILITIES = tuple('oracle2.' + signature for signature in (*_PUBLIC, *_PRIVATE))
_HASH = re.compile(r'^[a-f0-9]{64}$')
_ROLE = re.compile(r'^[a-z][a-z0-9_]{0,62}$')
TURN_KEYS = frozenset({'capture_event_id','capture_event_sha256','capture_revision','raw_sha256',
    'normalized_sha256','participant_epoch_id','participant_epoch_revision','participant_epoch_sha256',
    'participant_set_sha256','provider_speaker_id','actor_id'})

def participation_operation_policy_sha256_v1(composer_sha256,capability_hashes):
    """Closed installed program/capability fingerprint, never send authority."""
    if type(composer_sha256) is not str or re.fullmatch(r'[a-f0-9]{64}',composer_sha256) is None:
        raise PermissionError('exact installed composer fingerprint required')
    if (type(capability_hashes) is not tuple or len(capability_hashes)!=len(CAPABILITIES)
            or any(type(item) is not tuple or len(item)!=2 or type(item[0]) is not str
                or type(item[1]) is not str or re.fullmatch(r'[a-f0-9]{64}',item[1]) is None
                for item in capability_hashes)):
        raise PermissionError('complete exact installed SQL capability fingerprints required')
    values=dict(capability_hashes)
    if len(values)!=len(capability_hashes) or set(values)!=set(CAPABILITIES):
        raise PermissionError('complete exact installed SQL capability fingerprints required')
    descriptor=dict(purpose='meeting-participation-body-policy-v1',composer_sha256=composer_sha256,
        sql_capability_sha256s={key:values[key] for key in sorted(values)},to='everyone',max_codepoints=4096,
        presentation='escape-amp-lt-gt-v1',max_proactive=3,cooldown_seconds=120)
    return hashlib.sha256(canonical_bytes(descriptor)).hexdigest()



def _uuid(value):
    return type(value) is str and str(UUID(value)) == value


def _turn_frame(value):
    if type(value) is not dict or set(value) != TURN_KEYS:
        raise PermissionError('exact immutable own turn provenance required')
    try:
        valid = (all(_uuid(value[k]) for k in ('capture_event_id','participant_epoch_id','actor_id'))
            and all(type(value[k]) is str and _HASH.fullmatch(value[k]) for k in
                ('capture_event_sha256','raw_sha256','normalized_sha256','participant_epoch_sha256','participant_set_sha256'))
            and all(type(value[k]) is int and 1 <= value[k] <= 999999999 for k in ('capture_revision','participant_epoch_revision'))
            and type(value['provider_speaker_id']) is str
            and 1 <= len(value['provider_speaker_id']) <= 256
            and value['provider_speaker_id'].strip() == value['provider_speaker_id']
            and not any(ord(c)<32 or ord(c)==127 for c in value['provider_speaker_id']))
    except (ValueError,TypeError,AttributeError):
        valid = False
    if not valid:
        raise PermissionError('strict current event epoch and actor provenance required')
    return dict(value)


class ParticipationOutcomeUnknown(PermissionError):
    """Only read-only reconciliation is safe; this never authorizes a new send."""


@dataclass(frozen=True)
class ParticipationSQLBindingV1:
    admission_id: UUID
    admission_sha256: str
    principal_id: UUID
    workspace_id: UUID
    meeting_id: UUID
    session_login: str
    expected_owner: str
    kind: str
    runtime_hash: str
    registry_hash: str
    ca_path: str
    ca_sha256: str
    original_horizon: datetime
    capability_hashes: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if (any(type(v) is not UUID for v in (self.admission_id, self.principal_id, self.workspace_id, self.meeting_id))
                or self.kind not in {'host', 'sender', 'observer'}
                or type(self.session_login) is not str or type(self.expected_owner) is not str
                or not _ROLE.fullmatch(self.session_login) or not _ROLE.fullmatch(self.expected_owner)
                or self.session_login == self.expected_owner
                or type(self.capability_hashes) is not tuple
                or any(type(p) is not tuple or len(p) != 2 for p in self.capability_hashes)
                or len(dict(self.capability_hashes)) != len(self.capability_hashes)
                or set(dict(self.capability_hashes)) != set(CAPABILITIES)
                or not isinstance(self.original_horizon, datetime)
                or self.original_horizon.tzinfo is None or self.original_horizon.utcoffset() is None):
            raise PermissionError('exact independent finite participation installation required')
        if any(type(v) is not str or not _HASH.fullmatch(v) for v in (
                self.admission_sha256, self.runtime_hash, self.registry_hash, self.ca_sha256,
                *(v for _, v in self.capability_hashes))):
            raise PermissionError('exact independently pinned participation hashes required')


@dataclass(frozen=True)
class ParticipationClaimV1:
    """Created only after committed claim/current readback; not a supplier key."""
    metadata: dict
    body: bytes | None
    valid_until: datetime
    bot_id: UUID | None = None


def _instant(value):
    if type(value) is not str:
        raise PermissionError('actual SQL finite deadline required')
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None or at.utcoffset() is None:
        raise PermissionError('aware original deadline required')
    return at


class ParticipationAuthorityV1:
    def __init__(self, url, *, binding, _runtime_recheck: Callable[[], None] | None = None):
        if type(binding) is not ParticipationSQLBindingV1:
            raise PermissionError('fixed installed participation binding required')
        self.binding, self._url, self._runtime_recheck = binding, url, _runtime_recheck
        params = psycopg.conninfo.conninfo_to_dict(url)
        if (set(params) - {'host','hostaddr', 'port', 'dbname', 'user', 'password', 'sslmode', 'sslrootcert'}
                or not all(params.get(k) for k in ('host','port','dbname','password'))
                or params.get('sslmode') != 'verify-full' or params.get('sslrootcert') != binding.ca_path
                or params.get('user') != binding.session_login):
            raise PermissionError('fixed verify-full own-role URL required')
        try:
            address=params.get('hostaddr',params['host'])
            parsed=ipaddress.ip_address(address)
            if str(parsed)!=address or '%' in address or parsed.is_unspecified or parsed.is_multicast:
                raise ValueError()
            if ',' in params['host'] or not 1<=int(params.get('port','5432'))<=65535:
                raise ValueError()
        except ValueError:
            raise PermissionError('single installed numeric SQL target or exact pinned hostaddr required') from None
        self._target=params
        self._ca()

    @contextmanager
    def _connection(self,deadline):
        self._guard(deadline)
        with _connection_v1(self._url,deadline) as connection:
            yield connection
        self._guard(deadline)

    def _ca(self):
        path = Path(self.binding.ca_path)
        info = path.lstat()
        if (not path.is_absolute() or path.resolve() != path or not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077
                or hashlib.sha256(path.read_bytes()).hexdigest() != self.binding.ca_sha256):
            raise PermissionError('protected pinned participation CA changed')

    def _guard(self, deadline):
        self._ca()
        if not datetime.now(timezone.utc) < deadline <= self.binding.original_horizon:
            raise PermissionError('original participation window elapsed')
        # Restrictive only: it cannot skip or replace any SQL/catalog/root check,
        # supply identities, change a deadline, issue a grant or dispatch a send.
        if self._runtime_recheck is not None:
            self._runtime_recheck()
        from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
        request_remaining_v1(required=False)

    @staticmethod
    def _remaining(deadline):
        from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
        original=request_remaining_v1(required=False)
        wall=(deadline-datetime.now(timezone.utc)).total_seconds()
        return min(wall,original) if original is not None else wall

    def _deadline(self, deadline):
        if (not isinstance(deadline, datetime) or deadline.tzinfo is None or deadline.utcoffset() is None
                or deadline > datetime.now(timezone.utc) + timedelta(seconds=30)):
            raise PermissionError('original absolute bounded deadline required')
        self._guard(deadline)
        return deadline

    def _check(self, connection, deadline):
        self._guard(deadline)
        remaining = max(1, min(2000, int(self._remaining(deadline)*1000)))
        b = self.binding
        actual=connection.info;t=self._target
        if (not connection.pgconn.ssl_in_use or actual.host!=t['host'] or actual.dbname!=t['dbname']
                or actual.user!=t['user'] or actual.port!=int(t.get('port',5432))
                or t.get('hostaddr') and actual.hostaddr!=t['hostaddr']
                or sql_execute_v1(connection,deadline,'SELECT SESSION_USER,CURRENT_USER').fetchone() != (b.session_login, b.session_login)):
            raise PermissionError('actual own-role verified TLS session required')
        sql_execute_v1(connection,deadline,"SELECT pg_catalog.set_config('statement_timeout',%s,true),pg_catalog.set_config('lock_timeout',%s,true)",
                           (str(remaining)+'ms', str(remaining)+'ms'))
        rows = sql_execute_v1(connection,deadline,'''SELECT wanted.sig,n.nspname,p.proname,r.rolname,p.prosecdef,p.proconfig,
          pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p.prosrc,'UTF8')),'hex'),
          ARRAY(SELECT CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee)::text END||':'||x.privilege_type||':'||x.is_grantable::text
            FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) x ORDER BY 1)
          FROM pg_catalog.unnest(%s::text[]) wanted(sig)
          LEFT JOIN pg_catalog.pg_proc p ON p.oid=pg_catalog.to_regprocedure(wanted.sig)
          LEFT JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
          LEFT JOIN pg_catalog.pg_roles r ON r.oid=p.proowner''', (list(CAPABILITIES),)).fetchall()
        if len(rows) != len(CAPABILITIES) or {row[0] for row in rows} != set(CAPABILITIES):
            raise PermissionError('exact participation catalog required')
        for signature, namespace, name, owner, defin, config, body_hash, acl in rows:
            private = signature in {'oracle2.'+s for s in _PRIVATE}
            expected_acl = [b.expected_owner+':EXECUTE:false']
            if not private:
                expected_acl += ['oracle2_replacement_requester:EXECUTE:false']
            if (namespace != 'oracle2' or name != signature.split('(', 1)[0].split('.')[1]
                    or owner != b.expected_owner
                    or defin is not (signature != 'oracle2._meeting_participation_revoke_lock_v1()')
                    or config != ['search_path=pg_catalog, oracle2']
                    or body_hash != dict(b.capability_hashes)[signature] or acl != sorted(expected_acl)):
                raise PermissionError('fixed participation capability identity/owner/ACL changed')
        self._guard(deadline)

    def _context(self, value, deadline):
        if type(value) is not dict or 'context' not in value or 'valid_until' not in value:
            raise PermissionError('actual private participation envelope required')
        context = value['context']; b = self.binding
        keys = {'principal_id','workspace_id','session_role','runtime_hash','source_registry_hash','checked_at','valid_until'}
        if (type(context) is not dict or set(context) != keys
                or context['principal_id'] != str(b.principal_id) or context['workspace_id'] != str(b.workspace_id)
                or context['session_role'] != b.session_login or context['runtime_hash'] != b.runtime_hash
                or context['source_registry_hash'] != b.registry_hash):
            raise PermissionError('actual current participant context changed')
        until = min(_instant(value['valid_until']), _instant(context['valid_until']))
        now = datetime.now(timezone.utc)
        if not _instant(context['checked_at']) <= now < until <= min(deadline,b.original_horizon):
            raise PermissionError('actual participation context expired')
        return until

    def _status(self, wanted, deadline):
        b = self.binding
        with self._connection(deadline) as connection:
            self._check(connection, deadline)
            result = sql_execute_v1(connection,deadline,'SELECT oracle2.meeting_participation_status_v1(%s,%s,%s,%s)',
                                        (b.admission_id,b.admission_sha256,wanted,deadline)).fetchone()[0]
            until = self._context(result, deadline)
            self._check(connection, deadline)
        self._guard(min(deadline,until))
        self._public_metadata(result)
        if result['meeting_id']!=str(self.binding.meeting_id) or result['intent_id']!=(str(wanted) if wanted is not None else None):
            raise PermissionError('actual own metadata selector changed')
        return result, until

    @staticmethod
    def _public_metadata(result):
        keys = {'meeting_id','head_revision','generation','host_enabled','proactive_enabled','proactive_count',
                'intent_id','state','outcome','delivery_revision','claim_event_id','claim_current','request_sha256',
                'visible_message_proven','remote_stop_proven','executable','valid_until','context','observation_id','observation_revision','observation_sha256','observation_valid_until','turn_binding','intent_proactive','intent_current','receipt_permitted','receipt_bot_id','prepare_binding','reconcile_intent_id'}
        if (set(result) != keys or result['executable'] is not False
                or result['visible_message_proven'] is not False or result['remote_stop_proven'] is not False
                or type(result['host_enabled']) is not bool or type(result['proactive_enabled']) is not bool
                or type(result['claim_current']) is not bool
                or type(result['intent_current']) is not bool
                or result['claim_current'] and not result['intent_current']
                or type(result['receipt_permitted']) is not bool
                or any(type(result[k]) is not int or result[k]<0 for k in ('head_revision','generation','proactive_count'))
                or result['state'] not in (None,'intent','inflight','provider-response-observed','UNKNOWN','suppressed')
                or result['outcome']!={'inflight':'UNKNOWN','intent':'not-dispatched'}.get(result['state'],result['state'])
                or result['proactive_count']>3
                or (result['delivery_revision'] is not None and (type(result['delivery_revision']) is not int or result['delivery_revision']<0))):
            raise PermissionError('bounded truthful control/receipt metadata required')
        try:
            if not _uuid(result['meeting_id']) or any(result[k] is not None and not _uuid(result[k])
                    for k in ('intent_id','claim_event_id','observation_id','receipt_bot_id')):
                raise ValueError('identity')
            if any(result[k] is not None and (type(result[k]) is not str or not _HASH.fullmatch(result[k]))
                    for k in ('request_sha256','observation_sha256')):
                raise ValueError('hash')
            if (result['claim_event_id'] is not None and result['receipt_permitted']) != (result['receipt_bot_id'] is not None):
                raise ValueError('exact claimed receipt bot identity')
            if type(result['observation_revision']) is not int or result['observation_revision'] < 0:
                raise ValueError('revision')
            if result['intent_id'] is None:
                if any(result[k] is not None for k in ('turn_binding','intent_proactive','state','delivery_revision','request_sha256','claim_event_id')) or result['claim_current'] or result['intent_current']:
                    raise ValueError('empty intent')
            else:
                _turn_frame(result['turn_binding'])
                if type(result['intent_proactive']) is not bool:
                    raise ValueError('actual immutable intent mode')
            if result['observation_id'] is None:
                if result['observation_revision'] != 0 or result['observation_sha256'] is not None or result['observation_valid_until'] is not None:
                    raise ValueError('empty observation')
            elif result['observation_revision'] < 1 or result['observation_sha256'] is None or result['observation_valid_until'] is None:
                raise ValueError('incomplete observation')
            _instant(result['valid_until'])
            if result['reconcile_intent_id'] is not None and not _uuid(result['reconcile_intent_id']):
                raise ValueError('own reconciliation selector')
            binding=result['prepare_binding']
            if binding is not None:
                if (type(binding) is not dict or set(binding)!={'capture_event_id','head_revision','generation','existing_intent_id','valid_until'}
                        or not _uuid(binding['capture_event_id'])
                        or binding['existing_intent_id'] is not None and not _uuid(binding['existing_intent_id'])
                        or any(type(binding[k]) is not int or binding[k]<0 for k in ('head_revision','generation'))
                        or binding['head_revision']!=result['head_revision'] or binding['generation']!=result['generation']
                        or result['host_enabled'] is not True or result['observation_id'] is None
                        or result['observation_valid_until'] is None
                        or _instant(binding['valid_until'])>_instant(result['observation_valid_until'])
                        or _instant(binding['valid_until'])>_instant(result['valid_until'])):
                    raise ValueError('current own preparation binding')
            if result['observation_valid_until'] is not None:
                _instant(result['observation_valid_until'])
        except (ValueError,TypeError,AttributeError):
            raise PermissionError('strict own participation metadata required') from None
        return {k:v for k,v in result.items() if k not in {'context','turn_binding','intent_proactive','intent_current','receipt_permitted','receipt_bot_id','prepare_binding','reconcile_intent_id'}}

    def _latest_prepare_binding_v1(self, *, deadline):
        if self.binding.kind != 'sender':
            raise PermissionError('exact installed composer required')
        self._deadline(deadline)
        result,until=self._status(None,deadline)
        binding=result['prepare_binding']
        if binding is None:
            from .participation_runtime_v1 import ParticipationDeclined
            raise ParticipationDeclined('current host/chat/source preparation permission unavailable')
        self._guard(min(until,_instant(binding['valid_until'])))
        return dict(binding),result['proactive_enabled']

    def status_latest_v1(self, *, deadline):
        self._deadline(deadline)
        result,_=self._status(None,deadline)
        if result['reconcile_intent_id'] is None:
            return self._public_metadata(result)
        return self.status_v1(UUID(result['reconcile_intent_id']),deadline=deadline)

    def receipt_identity_v1(self,wanted,claim,*,deadline):
        """Own immutable receipt identity; currentness remains a separate fact."""
        if self.binding.kind!='sender' or any(type(v) is not UUID for v in (wanted,claim)):
            raise PermissionError('exact own claimed receipt selectors required')
        self._deadline(deadline)
        value,until=self._status(wanted,deadline)
        if value['receipt_permitted'] is not True or value['claim_event_id']!=str(claim) or not _uuid(value['receipt_bot_id']):
            raise PermissionError('exact own finite forensic receipt identity denied')
        self._guard(min(deadline,until))
        return UUID(value['receipt_bot_id']),self._public_metadata(value)

    def _current_receipt_binding_v1(self, wanted, claim, *, deadline):
        if self.binding.kind != 'sender' or any(type(v) is not UUID for v in (wanted,claim)):
            raise PermissionError('exact own receipt selector required')
        self._deadline(deadline)
        result,until=self._status(wanted,deadline)
        if result['receipt_permitted'] is not True or result['claim_event_id'] != str(claim):
            raise PermissionError('actual own finite forensic receipt permission required')
        return result['request_sha256'],until

    def _current_turn_binding_v1(self, wanted, *, deadline):
        """Hosting-only restrictive S07 reopen selector; never a public DTO/body."""
        if self.binding.kind != 'sender' or type(wanted) is not UUID:
            raise PermissionError('exact own sender reconciliation required')
        self._deadline(deadline)
        result, until = self._status(wanted, deadline)
        if result['intent_current'] is not True:
            raise PermissionError('current own host/source/observer permission required before bytes')
        return _turn_frame(result['turn_binding']), result['intent_proactive'], until

    def status_v1(self, wanted, *, deadline):
        if wanted is not None and type(wanted) is not UUID:
            raise ValueError('opaque exact own intent selector required')
        self._deadline(deadline)
        result, _ = self._status(wanted, deadline)
        return self._public_metadata(result)

    def _write(self, statement, arguments, *, wanted, deadline, claim=False, expected_metadata=None):
        """Internal fixed SQL only; no request/transport-selected function name."""
        self._deadline(deadline)
        mutation_attempted = False
        try:
            with self._connection(deadline) as connection:
                self._check(connection, deadline)
                # The guarded send may finish after the original deadline and
                # refuse before returning its result. Never present that as
                # a safe-to-resubmit denial, even if rollback may have occurred.
                mutation_attempted = True
                result = sql_execute_v1(connection,deadline,statement, arguments).fetchone()[0]
                until = self._context(result, deadline)
                self._check(connection, deadline)
            # Every failure after a possible commit is uncertain, including the
            # complete second connection/fresh read/close/current-settings path.
            self._guard(min(deadline,until))
            fresh, fresh_until = self._status(wanted, deadline)
            if expected_metadata is not None and any(fresh.get(k)!=v for k,v in expected_metadata.items()):
                raise PermissionError('committed participation metadata changed before return')
            if claim and result.get('executable') is True:
                if (result.get('created') is not True or type(result.get('body')) is not str
                        or not _uuid(result.get('bot_id'))
                        or fresh.get('claim_current') is not True or fresh.get('claim_event_id')!=result.get('claim_event_id')
                        or fresh.get('request_sha256')!=result.get('request_sha256')
                        or fresh.get('delivery_revision')!=result.get('revision')
                        or hashlib.sha256(result['body'].encode('utf8')).hexdigest()!=result.get('request_sha256')):
                    raise PermissionError('exact committed claim is no longer current')
                self._guard(min(until,fresh_until))
                return ParticipationClaimV1(self._public_metadata(fresh),result['body'].encode('utf8'),min(until,fresh_until),UUID(result['bot_id']))
            if 'body' in result or result.get('executable') not in (None,False):
                raise PermissionError('replay must not contain executable provider bytes')
            self._guard(min(until,fresh_until))
            metadata=self._public_metadata(fresh)
            return ParticipationClaimV1(metadata,None,min(until,fresh_until)) if claim else metadata
        except Exception as exc:
            if mutation_attempted or isinstance(exc,(psycopg.OperationalError,psycopg.InterfaceError,OSError,TimeoutError)):
                raise ParticipationOutcomeUnknown('participation outcome UNKNOWN; read-only reconciliation only, no resend') from None
            raise

    def control_v1(self, *, expected_head, operation, enabled, proactive_enabled=False, cooldown_seconds=120,max_proactive=3,observation_id=None,deadline):
        if self.binding.kind!='host' or type(enabled) is not bool or type(expected_head) is not int or expected_head<0 or type(operation) is not UUID:
            raise PermissionError('exact current host action required')
        if (type(proactive_enabled) is not bool or type(cooldown_seconds) is not int or not 120 <= cooldown_seconds <= 86400
                or type(max_proactive) is not int or not 0 <= max_proactive <= 3
                or (enabled and type(observation_id) is not UUID)
                or (not enabled and (proactive_enabled or cooldown_seconds != 120 or max_proactive != 3 or observation_id is not None))):
            raise PermissionError('closed bounded host participation controls required')
        body={} if not enabled else dict(proactive_enabled=proactive_enabled,cooldown_seconds=cooldown_seconds,max_proactive=max_proactive,observation_id=str(observation_id))
        b=self.binding
        return self._write('SELECT oracle2.meeting_participation_control_v1(%s,%s,%s,%s,%s,%s,%s)',
            (b.admission_id,b.admission_sha256,expected_head,operation,'enable' if enabled else 'disable',Jsonb(body),deadline),wanted=None,deadline=deadline)

    def claim_v1(self, *, intent_id, expected_revision, operation, deadline):
        if self.binding.kind!='sender' or type(intent_id) is not UUID or type(operation) is not UUID or type(expected_revision) is not int or expected_revision<0:
            raise PermissionError('exact own sender claim required')
        b=self.binding
        return self._write('SELECT oracle2.meeting_participation_claim_v1(%s,%s,%s,%s,%s,%s)',
            (b.admission_id,b.admission_sha256,intent_id,expected_revision,operation,deadline),wanted=intent_id,deadline=deadline,claim=True)

    def receipt_v1(self, *, intent_id, claim_event_id, operation, wire, deadline):
        if self.binding.kind!='sender' or any(type(v) is not UUID for v in (intent_id,claim_event_id,operation)) or type(wire) is not dict:
            raise PermissionError('exact own forensic receipt required')
        b=self.binding
        return self._write('SELECT oracle2.meeting_participation_observe_v1(%s,%s,%s,%s,%s,%s,%s)',
            (b.admission_id,b.admission_sha256,intent_id,claim_event_id,operation,Jsonb(wire),deadline),wanted=intent_id,deadline=deadline)

    def observe_audience_v1(self, *, expected_revision, observation_id, observation, deadline):
        """Fixed independently installed observer only; no host-facing route.

        This consumer does not supply a provider observation producer. Until an
        actual qualified owner exists, production facts remain UNKNOWN/declined.
        """
        if (self.binding.kind != 'observer' or type(expected_revision) is not int or expected_revision < 0
                or type(observation_id) is not UUID or type(observation) is not dict
                or len(canonical_bytes(observation)) > 262144):
            raise PermissionError('exact bounded independently appointed observation required')
        b = self.binding
        return self._write('SELECT oracle2.meeting_participation_observe_audience_v1(%s,%s,%s,%s,%s,%s)',
            (b.admission_id,b.admission_sha256,expected_revision,observation_id,Jsonb(observation),deadline),
            wanted=None,deadline=deadline,expected_metadata={'observation_id':str(observation_id),
                'observation_sha256':hashlib.sha256(canonical_bytes(observation)).hexdigest()})

    def _prepare_current_turn_v1(self, *, expected_head, operation, intent_id, frame,
                                 text, proactive, observation_id, composer_sha256, deadline):
        """Hosting-only actual protected S07 bytes; never a public body API."""
        if (self.binding.kind != 'sender' or type(expected_head) is not int or expected_head < 0
                or any(type(v) is not UUID for v in (operation,intent_id,observation_id))
                or type(text) is not str or type(proactive) is not bool
                or type(composer_sha256) is not str or not _HASH.fullmatch(composer_sha256)):
            raise PermissionError('exact installed same-turn composer required')
        frame = _turn_frame(frame)
        if hashlib.sha256(text.encode('utf8')).hexdigest() != frame['normalized_sha256']:
            raise PermissionError('protected normalized bytes differ')
        # Same deterministic owner as hosting; SQL only repeats the fixed
        # presentation fence for its authenticated installed composer admission.
        from .participation_runtime_v1 import compose_current_turn_v1
        compose_current_turn_v1(text,proactive=proactive)
        answer = dict(intent_id=str(intent_id),proactive=proactive,observation_id=str(observation_id),
                      composer_sha256=composer_sha256,turn_text=text)
        b = self.binding
        return self._write('SELECT oracle2.meeting_participation_prepare_v1(%s,%s,%s,%s,%s,%s,%s)',
            (b.admission_id,b.admission_sha256,expected_head,operation,Jsonb(frame),Jsonb(answer),deadline),
            wanted=intent_id,deadline=deadline)
