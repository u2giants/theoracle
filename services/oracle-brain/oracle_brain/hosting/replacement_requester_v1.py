"""Fixed per-principal SQL control metadata. No listener, authority or result path.

Only existing independently appointed intake settings are consumed. Calls never
retry: an uncertain commit/close remains unavailable and requires observation.
"""
from datetime import datetime, timezone
import json
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes
from .replacement_public_view_v1 import Public
from .original_intake_v1 import (
    OriginalIntakeSettingsV1, RequesterContextV1, _pinned, _context_horizon,
)

HASH = r'^[a-f0-9]{64}$'
MAX_REVISION = 2147483647
ControlState = Literal['pending', 'processing', 'delivered', 'revision_pending', 'cancelled', 'error',
                       'awaiting-external-authority', 'missing-evidence', 'cancel-requested', 'failed', 'UNKNOWN']


class _Wire(StrictRecord):
    schema_version: Literal[1]

    @field_validator('schema_version', mode='before')
    @classmethod
    def version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('exact requester version required')
        return value


class RequesterSourceSelectorV1(Public):
    source_id: UUID
    revision: int = Field(strict=True, ge=1, le=MAX_REVISION)


class ReserveRequesterV1(_Wire):
    operation: Literal['reserve']
    source_selectors: tuple[RequesterSourceSelectorV1, ...] = Field(min_length=1, max_length=100)
    population_sha256: str = Field(pattern=HASH)
    idempotency_key: UUID
    caller_deadline: AwareDatetime

    @model_validator(mode='after')
    def unique_sources(self):
        if len({s.source_id for s in self.source_selectors}) != len(self.source_selectors):
            raise ValueError('distinct exact source selectors required')
        return self


class StatusRequesterV1(_Wire):
    operation: Literal['status']
    run_id: UUID
    caller_deadline: AwareDatetime


class CancelRequesterV1(_Wire):
    operation: Literal['cancel']
    run_id: UUID
    expected_revision: int = Field(strict=True, ge=1, le=MAX_REVISION)
    reason: str = Field(min_length=1, max_length=1600)
    idempotency_key: UUID
    caller_deadline: AwareDatetime


RequesterRequestV1 = ReserveRequesterV1 | StatusRequesterV1 | CancelRequesterV1


def parse_requester_request_v1(raw: bytes) -> RequesterRequestV1:
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise ValueError('bounded canonical requester bytes required')

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate requester field')
            value[key] = item
        return value

    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('finite requester fields required')))
    if type(value) is not dict or canonical_bytes(value) != raw:
        raise ValueError('canonical requester object required')
    cls = {'reserve': ReserveRequesterV1, 'status': StatusRequesterV1,
           'cancel': CancelRequesterV1}.get(value.get('operation'))
    if cls is None:
        raise ValueError('fixed requester operation required')
    return cls.model_validate_json(raw)


class _ReserveEnvelope(_Wire):
    run_id: UUID
    journey_revision: int = Field(strict=True, ge=1, le=MAX_REVISION)
    state: Literal['pending']
    # Existing SQL idempotency return deliberately omits this field.
    population_sha256: str | None = Field(default=None, pattern=HASH)
    context: RequesterContextV1

    @field_validator('population_sha256', mode='before')
    @classmethod
    def absent_population_only(cls, value):
        if value is None:
            raise ValueError('reserve population may be absent, never null')
        return value


class _CancelEnvelope(_Wire):
    run_id: UUID
    journey_revision: int = Field(strict=True, ge=1, le=MAX_REVISION)
    state: Literal['cancelled']
    cancel_requested: Literal[True]
    paid_cost_retained: Literal[True]
    in_flight_attempt_retained: bool = Field(strict=True)
    remote_stop_proof: Literal[False]
    message: Literal['cancellation requested; in-flight attempt retained',
                     'cancellation completed; no in-flight attempt']
    context: RequesterContextV1

    @field_validator('cancel_requested', 'paid_cost_retained', 'remote_stop_proof', mode='before')
    @classmethod
    def boolean(cls, value):
        if type(value) is not bool:
            raise ValueError('actual SQL boolean required')
        return value

    @model_validator(mode='after')
    def message_binding(self):
        expected = ('cancellation requested; in-flight attempt retained' if self.in_flight_attempt_retained
                    else 'cancellation completed; no in-flight attempt')
        if self.message != expected:
            raise ValueError('actual cancellation observation differs')
        return self


class _MetadataEnvelope(_Wire):
    run_id: UUID
    journey_revision: int = Field(strict=True, ge=1, le=MAX_REVISION)
    state: ControlState
    population_sha256: str = Field(pattern=HASH)
    cancel_requested: bool = Field(strict=True)
    paid_cost_retained: bool = Field(strict=True)
    context: RequesterContextV1


class RequesterControlMetadataV1(Public):
    """Control metadata only. Delivered/cancelled never proves result/remote stop."""
    runId: UUID
    journeyRevision: int = Field(strict=True, ge=1, le=MAX_REVISION)
    controlState: ControlState
    populationSha256: str = Field(pattern=HASH)
    cancelRequested: bool = Field(strict=True)
    remoteStopProven: Literal[False] = False
    resultAvailable: Literal[False] = False


class ReplacementRequesterUnavailable(PermissionError):
    """No success observation; mutation/commit may be UNKNOWN. Never retry here."""


_FUNCTIONS = (
    'oracle2.reserve_replacement_journey(jsonb,uuid)',
    'oracle2.current_replacement_journey_metadata(uuid)',
    'oracle2.request_replacement_cancel(uuid,integer,text,uuid)',
)


class ReplacementRequesterFactoryV1:
    def __init__(self, settings: OriginalIntakeSettingsV1):
        if type(settings) is not OriginalIntakeSettingsV1:
            raise TypeError('existing exact intake settings required')
        settings.current()
        self.settings = settings

    def execute_v1(self, raw: bytes) -> RequesterControlMetadataV1:
        # Parse before connecting or any SQL mutation. No body-selected identity.
        request = parse_requester_request_v1(raw)
        s = self.settings
        c = s.config
        original_deadline = request.caller_deadline

        def current(context=None):
            _pinned(c.database_url.path, c.database_url.sha256, 16384)
            _pinned(c.database_ca.path, c.database_ca.sha256, 131072)
            bound = s.current() if context is None else _context_horizon(s, context)
            now = datetime.now(timezone.utc)
            if not now < original_deadline <= min(c.original_horizon, c.expires_at, s.appointment.expires_at):
                raise PermissionError('original requester deadline expired or excessive')
            if now >= min(bound, original_deadline):
                raise PermissionError('requester authority expired')

        try:
            import psycopg
            from psycopg.conninfo import conninfo_to_dict
            current()
            url = _pinned(c.database_url.path, c.database_url.sha256, 16384).decode('utf-8')
            _pinned(c.database_ca.path, c.database_ca.sha256, 131072)
            target = conninfo_to_dict(url)
            if (set(target) - {'host', 'hostaddr', 'port', 'dbname', 'user', 'password', 'sslmode', 'sslrootcert', 'connect_timeout'}
                    or target.get('sslmode') != 'verify-full'
                    or target.get('sslrootcert') != c.database_ca.path
                    or target.get('user') != c.expected_session_role
                    or not target.get('host') or not target.get('dbname')):
                raise PermissionError('fixed requester SQL target required')
            with psycopg.connect(url, connect_timeout=5) as conn:
                actual = conn.info
                if (not conn.pgconn.ssl_in_use or actual.host != target['host']
                        or actual.dbname != target['dbname'] or actual.user != target['user']
                        or actual.port != int(target.get('port', 5432))
                        or (target.get('hostaddr') and actual.hostaddr != target['hostaddr'])):
                    raise PermissionError('actual requester SQL target differs')
                current()
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_catalog.set_config('statement_timeout','5000',true),pg_catalog.set_config('lock_timeout','2000',true)")
                    cur.execute("SELECT SESSION_USER::text,CURRENT_USER::text,(SELECT pg_catalog.pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace WHERE nspname='oracle2')")
                    if cur.fetchone() != (c.expected_session_role, c.expected_session_role, c.expected_owner_role):
                        raise PermissionError('actual requester SQL role differs')
                    cur.execute("SELECT n.nspname,p.proname,pg_catalog.pg_get_userbyid(p.proowner),p.prosecdef FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE p.oid IN (pg_catalog.to_regprocedure('oracle2.reserve_replacement_journey(jsonb,uuid)'),pg_catalog.to_regprocedure('oracle2.current_replacement_journey_metadata(uuid)'),pg_catalog.to_regprocedure('oracle2.request_replacement_cancel(uuid,integer,text,uuid)'))")
                    owners = cur.fetchall()
                    if (len(owners) != 3
                            or {(row[0], row[1]) for row in owners} != {
                                ('oracle2', signature.split('(', 1)[0].split('.', 1)[1])
                                for signature in _FUNCTIONS}
                            or any(row[2] != c.expected_owner_role or row[3] is not True for row in owners)):
                        raise PermissionError('actual requester function owner differs')
                    current()
                    envelope = None
                    if type(request) is ReserveRequesterV1:
                        body = dict(source_selectors=[x.model_dump(mode='json') for x in request.source_selectors],
                                    population_sha256=request.population_sha256,
                                    caller_deadline=original_deadline.isoformat())
                        cur.execute('SELECT oracle2.reserve_replacement_journey(%s::jsonb,%s)',
                                    (canonical_bytes(body).decode('utf-8'), request.idempotency_key))
                        envelope = _ReserveEnvelope.model_validate_json(json.dumps(cur.fetchone()[0]))
                        if envelope.population_sha256 is not None and envelope.population_sha256 != request.population_sha256:
                            raise PermissionError('reserved population differs')
                        run_id = envelope.run_id
                    elif type(request) is CancelRequesterV1:
                        cur.execute('SELECT oracle2.request_replacement_cancel(%s,%s,%s,%s)',
                                    (request.run_id, request.expected_revision, request.reason, request.idempotency_key))
                        envelope = _CancelEnvelope.model_validate_json(json.dumps(cur.fetchone()[0]))
                        if envelope.run_id != request.run_id or envelope.journey_revision != request.expected_revision + 1:
                            raise PermissionError('cancelled journey identity differs')
                        run_id = request.run_id
                    else:
                        run_id = request.run_id
                    if envelope is not None:
                        current(envelope.context)
                    # Reserve idempotency replies can be historical. Always observe
                    # current metadata inside this same transaction, never retry.
                    cur.execute('SELECT oracle2.current_replacement_journey_metadata(%s)', (run_id,))
                    observed = _MetadataEnvelope.model_validate_json(json.dumps(cur.fetchone()[0]))
                    if (observed.run_id != run_id
                            or envelope is not None and observed.journey_revision < envelope.journey_revision):
                        raise PermissionError('current requester journey differs')
                    if type(request) is ReserveRequesterV1 and observed.population_sha256 != request.population_sha256:
                        raise PermissionError('current requester population differs')
                    if type(request) is CancelRequesterV1 and (
                            observed.state != 'cancelled' or not observed.cancel_requested
                            or observed.journey_revision != envelope.journey_revision):
                        raise PermissionError('current requester cancellation differs')
                    current(observed.context)
                current(observed.context)
                conn.commit()
            # A close error or revoked context after commit is UNKNOWN, not success.
            current(observed.context)
            return RequesterControlMetadataV1(
                runId=observed.run_id, journeyRevision=observed.journey_revision,
                controlState=observed.state, populationSha256=observed.population_sha256,
                cancelRequested=observed.cancel_requested)
        except Exception:
            raise ReplacementRequesterUnavailable('Requester outcome unavailable; observe existing state before any new action') from None
