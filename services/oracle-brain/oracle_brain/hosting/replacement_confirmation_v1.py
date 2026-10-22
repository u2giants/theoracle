"""Fixed exact-map SQL014 confirmation; no general advance or truth promotion."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import ipaddress
from typing import Literal
from uuid import UUID

import psycopg
from pydantic import AwareDatetime, Field
from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes
from .original_intake_v1 import RequesterContextV1, _context_horizon, _pinned, _parse
from .replacement_requester_v1 import _MetadataEnvelope, RequesterControlMetadataV1
from .replacement_confirmation_settings_v1 import ConfirmationSettingsV1

HASH = r'^[a-f0-9]{64}$'
GROUP = 'oracle2_replacement_requester'
FUNCTIONS = (
    ('compare_and_advance_replacement_journey', 'oracle2.compare_and_advance_replacement_journey(uuid,integer,jsonb,uuid)'),
    ('current_replacement_journey_metadata', 'oracle2.current_replacement_journey_metadata(uuid)'),
)
OWNER_QUERY = 'WITH expected(label,oid) AS (VALUES ' + ','.join(
    "('" + name + "',pg_catalog.to_regprocedure('" + signature + "'))" for name, signature in FUNCTIONS
) + ") SELECT e.label,n.nspname,p.proname,pg_catalog.pg_get_userbyid(p.proowner),p.prosecdef FROM expected e JOIN pg_catalog.pg_proc p ON p.oid=e.oid JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace"


class ConfirmationRequestV1(StrictRecord):
    run_id: UUID
    expected_journey_revision: int = Field(strict=True, ge=1, le=2147483646)
    model_id: UUID
    version: int = Field(strict=True, ge=1, le=2147483647)
    content_hash: str = Field(pattern=HASH)
    ack_event_id: UUID
    workflow_id: str = Field(min_length=1, max_length=200)
    idempotency_key: UUID
    caller_deadline: AwareDatetime


def parse_confirmation_request_v1(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 8192:
        raise ValueError('bounded canonical exact confirmation request required')
    return _parse(ConfirmationRequestV1, raw)


class _ConfirmedEnvelopeV1(StrictRecord):
    run_id: UUID
    journey_revision: int = Field(strict=True, ge=1, le=2147483647)
    state: Literal['delivered']
    population_sha256: str = Field(pattern=HASH)
    context: RequesterContextV1


@dataclass(frozen=True)
class ConfirmationObservationV1:
    metadata: RequesterControlMetadataV1
    valid_until: datetime


class ConfirmationConflictV1(ValueError):
    """Missing/stale CAS or same-key replay cannot be represented as success."""


class ConfirmationUnavailableV1(PermissionError):
    """No successful observation; no retry, authority or eligible badge."""


class ConfirmationOutcomeUnknownV1(RuntimeError):
    """A write may be committed. Never retry or claim rollback/delivery."""


class ReplacementConfirmationFactoryV1:
    def __init__(self, settings):
        if type(settings) is not ConfirmationSettingsV1:
            raise TypeError('independently appointed fixed confirmation settings required')
        settings.current()
        self.settings = settings

    def _check(self, conn, target, current):
        c = self.settings.intake.config
        remaining = current()
        actual = conn.info.get_parameters()
        if (not conn.pgconn.ssl_in_use or conn.info.port != int(target.get('port', 5432))
                or any(str(actual.get(k, '')) != str(target.get(k, '')) for k in ('host', 'dbname', 'user', 'sslmode', 'sslrootcert'))
                or (target.get('hostaddr') and conn.info.hostaddr != target['hostaddr'])):
            raise PermissionError('actual confirmation SQL target differs')
        conn.execute("SELECT pg_catalog.set_config('statement_timeout',%s,true),pg_catalog.set_config('lock_timeout',%s,true)",
            (str(min(5000, remaining)), str(min(2000, remaining))))
        role = conn.execute('SELECT session_user,current_user,rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_catalog.pg_roles WHERE rolname=session_user').fetchone()
        if (not role or role[:2] != (c.expected_session_role, c.expected_session_role)
                or role[2] is not True or any(role[3:])):
            raise PermissionError('actual confirmation caller differs')
        reachable = conn.execute("SELECT rolname::text FROM pg_catalog.pg_roles WHERE pg_catalog.pg_has_role(session_user,oid,'MEMBER') OR pg_catalog.pg_has_role(session_user,oid,'SET') OR pg_catalog.pg_has_role(session_user,oid,'USAGE')").fetchall()
        if {r[0] for r in reachable} != {c.expected_session_role, GROUP}:
            raise PermissionError('exclusive confirmation requester role required')
        flags = conn.execute('SELECT rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_catalog.pg_roles WHERE rolname=%s', (GROUP,)).fetchone()
        if flags is None or any(flags):
            raise PermissionError('fixed requester group flags differ')
        owner = conn.execute("SELECT r.rolname,pg_catalog.pg_has_role(session_user,r.oid,'MEMBER') FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner WHERE n.nspname='oracle2'").fetchone()
        if owner != (c.expected_owner_role, False):
            raise PermissionError('confirmation schema owner differs')
        rows = conn.execute(OWNER_QUERY).fetchall()
        if (len(rows) != 2 or set(rows) != {(name, 'oracle2', name, c.expected_owner_role, True) for name, _ in FUNCTIONS}):
            raise PermissionError('fixed confirmation function owners differ')
        current()

    def execute_v1(self, raw, *, original_start):
        q = parse_confirmation_request_v1(raw)
        now = datetime.now(timezone.utc)
        if (type(original_start) is not datetime or original_start.tzinfo is None
                or not original_start <= now < original_start + timedelta(seconds=30)
                or not now < q.caller_deadline <= original_start + timedelta(seconds=30)):
            raise ConfirmationUnavailableV1('original confirmation deadline unavailable')
        s = self.settings
        c = s.intake.config
        effective_deadline = q.caller_deadline
        attempted = False
        commit_attempted = False

        def current(context=None):
            nonlocal effective_deadline
            bound = s.current()
            if q.caller_deadline > bound:
                raise PermissionError('original confirmation deadline exceeds appointment')
            if context is not None:
                effective_deadline = min(effective_deadline, _context_horizon(s.intake, context))
            now = datetime.now(timezone.utc)
            if now >= min(bound, effective_deadline):
                raise PermissionError('original confirmation window elapsed')
            return max(1, int((min(bound, effective_deadline)-now).total_seconds()*1000))

        try:
            remaining = current()
            url = _pinned(c.database_url.path, c.database_url.sha256, 16384).decode('utf-8')
            target = psycopg.conninfo.conninfo_to_dict(url)
            if (set(target) - {'host', 'hostaddr', 'port', 'dbname', 'user', 'password', 'sslmode', 'sslrootcert', 'connect_timeout'}
                    or target.get('sslmode') != 'verify-full' or target.get('sslrootcert') != c.database_ca.path
                    or target.get('user') != c.expected_session_role or not target.get('dbname')):
                raise PermissionError('fixed confirmation SQL target required')
            ipaddress.ip_address(target.get('hostaddr') or target.get('host', ''))
            remaining = current()
            if remaining < 1000:
                raise PermissionError('insufficient confirmation connection budget')
            with psycopg.connect(url, connect_timeout=min(5, remaining//1000), tcp_user_timeout=remaining,
                    options=f'-c statement_timeout={min(5000, remaining)} -c lock_timeout={min(2000, remaining)}') as conn:
                self._check(conn, target, current)
                binding = dict(target_state='delivered', model_id=str(q.model_id), version=q.version,
                    content_hash=q.content_hash, ack_event_id=str(q.ack_event_id), workflow_id=q.workflow_id)
                remaining = current()
                conn.execute("SELECT pg_catalog.set_config('statement_timeout',%s,true),pg_catalog.set_config('lock_timeout',%s,true)",
                    (str(min(5000, remaining)), str(min(2000, remaining))))
                current()
                attempted = True
                row = conn.execute('SELECT oracle2.compare_and_advance_replacement_journey(%s,%s,%s::jsonb,%s)',
                    (q.run_id, q.expected_journey_revision, canonical_bytes(binding).decode('utf-8'), q.idempotency_key)).fetchone()
                envelope = _ConfirmedEnvelopeV1.model_validate_json(canonical_bytes(row[0]))
                if (envelope.run_id != q.run_id or envelope.journey_revision != q.expected_journey_revision+1):
                    raise PermissionError('confirmed current journey differs')
                current(envelope.context)
                row = conn.execute('SELECT oracle2.current_replacement_journey_metadata(%s)', (q.run_id,)).fetchone()
                observed = _MetadataEnvelope.model_validate_json(canonical_bytes(row[0]))
                if ((observed.run_id, observed.journey_revision, observed.state, observed.population_sha256, observed.cancel_requested) !=
                        (q.run_id, envelope.journey_revision, 'delivered', envelope.population_sha256, False)):
                    raise PermissionError('fresh confirmed control metadata differs')
                current(observed.context)
                self._check(conn, target, current)
                current(observed.context)
                commit_attempted = True
                conn.commit()
            # Protected input/deadline checks AFTER actual commit and close.
            # This control-only observation is never a current badge or grant.
            current(observed.context)
            return ConfirmationObservationV1(RequesterControlMetadataV1(runId=observed.run_id,
                journeyRevision=observed.journey_revision, controlState=observed.state,
                populationSha256=observed.population_sha256, cancelRequested=observed.cancel_requested), effective_deadline)
        except psycopg.errors.SerializationFailure:
            raise ConfirmationConflictV1('confirmation target changed or replay conflicts') from None
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            if attempted and (exc.sqlstate is None or exc.sqlstate.startswith('08')):
                raise ConfirmationOutcomeUnknownV1('confirmation outcome UNKNOWN; no retry') from None
            raise ConfirmationUnavailableV1('confirmation unavailable') from None
        except Exception:
            if commit_attempted:
                raise ConfirmationOutcomeUnknownV1('confirmation observation UNKNOWN after commit; no retry') from None
            raise ConfirmationUnavailableV1('confirmation unavailable') from None
