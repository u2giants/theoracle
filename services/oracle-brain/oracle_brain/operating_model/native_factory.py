"""Native-only provider broker: immutable jobs, one key, one actual ledger.

Only the trusted broker owns the existing provider credential. Executor RPC
clients supply an opaque job identifier and matching sealed request, never a
sender, allowance, price, permission claim or pre-reserved billing ticket.
Registry issuance, current job resolution and authority are coordinator duties;
this module does not manufacture any of those proofs.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal
from uuid import UUID

import psycopg
from pydantic import AwareDatetime, Field

from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest, authorize
from .contracts import StrictRecord, canonical_bytes, digest
from .key_coverage import VerifiedKeyCoverage
from .native_provider import NativeOpenRouter
from .provider_adapter import AdmittedProvider, Budget, Pricing


class LedgerRegistry(StrictRecord):
    key_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    host: str = Field(min_length=1)
    port: int = Field(strict=True, gt=0, le=65535)
    database: str = Field(min_length=1)
    role: str = Field(min_length=1)
    cluster_identifier: str = Field(pattern=r'^[0-9]+$')
    namespace_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    transport: Literal['verify-full-tls', 'owned-synthetic-loopback']
    transport_receipt_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    dedicated_single_key: Literal[True]
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime


class NativeDispatchJob(StrictRecord):
    dispatch_id: UUID
    workspace_id: UUID
    artifact_id: UUID
    batch_id: UUID
    purpose: Literal['source-census', 'source-extraction', 'operating-audit', 'independent-source-semantic-acceptance']
    attempt: Literal[1, 2]
    request: dict
    request_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    processing_request: ProcessingRequest
    approvals: tuple[ProcessingApproval, ...]
    pricing: Pricing
    register_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    input_tokens_upper_bound: int = Field(strict=True, gt=0)


class _AuthorizedNative(NativeOpenRouter):
    """Keep the exact native send/allowance methods; gate immediately at POST."""
    def __init__(self,*args,before_private_dispatch,**kwargs):
        super().__init__(*args,**kwargs)
        self._before_private_dispatch=before_private_dispatch

    def _request(self,path,body=None):
        if path in {'/chat/completions','/embeddings'}:
            self._before_private_dispatch()
            self._coverage(datetime.now(timezone.utc))
        response=super()._request(path,body)
        if path in {'/models','/embeddings/models'}:
            self._models_snapshot=response
        return response


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


def _deny_constant(_value):
    raise ValueError('nonfinite JSON value')


def ledger_namespace_hash(connection) -> str:
    """Read-only structural fingerprint, excluding row contents and secrets."""
    rows = connection.execute("""SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        WHERE n.nspname='oracle2' AND c.relname IN
          ('operating_dispatch_reservations','operating_dispatch_receipts','operating_dispatch_diagnoses')
          AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum""").fetchall()
    constraints = connection.execute("""SELECT c.relname,pg_get_constraintdef(k.oid)
        FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='oracle2'
          AND c.relname IN ('operating_dispatch_reservations','operating_dispatch_receipts','operating_dispatch_diagnoses')
        ORDER BY c.relname,pg_get_constraintdef(k.oid)""").fetchall()
    triggers = connection.execute("""SELECT c.relname,pg_get_triggerdef(t.oid),pg_get_functiondef(t.tgfoid)
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='oracle2' AND NOT t.tgisinternal
          AND c.relname IN ('operating_dispatch_reservations','operating_dispatch_receipts','operating_dispatch_diagnoses')
        ORDER BY c.relname,pg_get_triggerdef(t.oid)""").fetchall()
    if {row[0] for row in rows} != {'operating_dispatch_reservations','operating_dispatch_receipts','operating_dispatch_diagnoses'}:
        raise PermissionError('complete current billing namespace required')
    return digest({'columns':rows,'constraints':constraints,'triggers':triggers})


def verify_ledger(url: str, registry: LedgerRegistry, *, trusted_registry_hash: str,
                  key_fingerprint: str, now: datetime) -> str:
    """External registry asserts exclusivity; actual SQL proves target identity.

    No role grant, schema write, or self-issuance occurs during this preflight.
    Missing least-privilege metadata access denies, rather than being bypassed.
    """
    identity = digest(registry.model_dump(mode='json'))
    if (identity != trusted_registry_hash or registry.key_fingerprint != key_fingerprint
            or registry.issuer_actor == registry.reviewer_actor or registry.dedicated_single_key is not True
            or now.tzinfo is None or registry.expires_at <= now):
        raise PermissionError('independent current single-key ledger registry required')
    parts = psycopg.conninfo.conninfo_to_dict(url)
    if (parts.get('host') != registry.host or int(parts.get('port','5432')) != registry.port
            or parts.get('dbname') != registry.database or parts.get('user') != registry.role):
        raise PermissionError('actual ledger connection target differs from registry')
    if registry.transport == 'owned-synthetic-loopback':
        if registry.host not in {'127.0.0.1','localhost'} or not registry.database.startswith('oracle_operating_model_test_'):
            raise PermissionError('synthetic ledger must be owned loopback test namespace')
    elif parts.get('sslmode') != 'verify-full':
        raise PermissionError('production ledger requires verified TLS hostname')
    with psycopg.connect(url, connect_timeout=5) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        database, role, superuser, create_role, create_db, replication, bypass_rls = connection.execute("SELECT current_database(),current_user,rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        if (database,role) != (registry.database,registry.role) or any((superuser,create_role,create_db,replication,bypass_rls)):
            raise PermissionError('actual least-privilege ledger role required')
        memberships=connection.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname<>current_user AND pg_has_role(current_user,oid,'MEMBER'))").fetchone()[0]
        if memberships:
            raise PermissionError('billing role cannot inherit unbounded role capabilities')
        if registry.transport == 'verify-full-tls' and not connection.pgconn.ssl_in_use:
            raise PermissionError('production ledger connection is not TLS')
        cluster = connection.execute('SELECT system_identifier::text FROM pg_catalog.pg_control_system()').fetchone()[0]
        if cluster != registry.cluster_identifier or ledger_namespace_hash(connection) != registry.namespace_hash:
            raise PermissionError('actual ledger cluster or namespace changed')
        for table in ('operating_dispatch_reservations','operating_dispatch_receipts','operating_dispatch_diagnoses'):
            privileges = connection.execute("SELECT has_table_privilege(current_user,%s,'SELECT'),has_table_privilege(current_user,%s,'INSERT'),has_table_privilege(current_user,%s,'UPDATE'),has_table_privilege(current_user,%s,'DELETE')",('oracle2.'+table,)*4).fetchone()
            if privileges != (True,True,False,False):
                raise PermissionError('append-only least billing privileges required')
        broad_access=connection.execute("""SELECT EXISTS(SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='oracle2' AND c.relkind IN ('r','p','v','m')
              AND c.relname NOT IN ('operating_dispatch_reservations','operating_dispatch_receipts','operating_dispatch_diagnoses')
              AND (has_table_privilege(current_user,c.oid,'SELECT') OR has_table_privilege(current_user,c.oid,'INSERT')
                   OR has_table_privilege(current_user,c.oid,'UPDATE') OR has_table_privilege(current_user,c.oid,'DELETE')))""").fetchone()[0]
        if broad_access:
            raise PermissionError('billing role cannot have broad original-ledger access')
    return identity


class NativeBrokerEgress:
    """Trusted mTLS ingress adapter; reserve and fixed send occur in one broker."""
    def __init__(self, *, api_key: str, ledger_url: str, registry: LedgerRegistry,
                 trusted_registry_hash: str, coverage_receipt: Callable[[], VerifiedKeyCoverage],
                 trusted_coverage_hash: str, resolve_job: Callable[[UUID], NativeDispatchJob],
                 authorize_current_job: Callable[[NativeDispatchJob], bool],
                 validate_response: Callable[[NativeDispatchJob, object], None], private_receipts: Path):
        self._key = api_key
        self._key_fingerprint = hashlib.sha256(api_key.encode()).hexdigest()
        self._url,self._registry,self._registry_hash = ledger_url,registry,trusted_registry_hash
        self._coverage,self._coverage_hash = coverage_receipt,trusted_coverage_hash
        self._resolve,self._authorize = resolve_job,authorize_current_job
        if not callable(validate_response):
            raise PermissionError('trusted response validator required before provider reads')
        self._validate_response = validate_response
        self._receipts = Path(private_receipts)
        if (not api_key or not self._receipts.is_dir() or self._receipts.is_symlink()
                or self._receipts.stat().st_mode & 0o077):
            raise PermissionError('existing key and protected private receipt directory required')

    def _capture_wire(self, job: NativeDispatchJob, raw: bytes, reservation_id, *, complete: bool):
        if (not isinstance(reservation_id,UUID) or type(raw) is not bytes or len(raw)>16*1024*1024
                or type(complete) is not bool):
            raise PermissionError('bounded raw wire and existing reservation required')
        wire=self._receipts/(str(job.dispatch_id)+'.wire')
        metadata=self._receipts/(str(job.dispatch_id)+'.wire.json')
        binding={'dispatch_id':str(job.dispatch_id),'reservation_id':str(reservation_id),
                 'request_hash':job.request_hash,'permission_hash':job.permission_hash,
                 'job_hash':digest(job.model_dump(mode='json')),'key_fingerprint':self._key_fingerprint,
                 'ledger_identity_hash':self._registry_hash,'raw_sha256':hashlib.sha256(raw).hexdigest(),
                 'captured_bytes':len(raw),'complete':complete,'truncated':not complete}
        for path,data in ((wire,raw),(metadata,canonical_bytes(binding))):
            descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
        directory=os.open(self._receipts,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
        if wire.read_bytes()!=raw or json.loads(metadata.read_bytes())!=binding:
            raise PermissionError('durable exact wire readback failed')

    def _record(self, job: NativeDispatchJob, raw: str | None, reservation_id, *, failed: bool):
        dispatch_id=job.dispatch_id
        record = {'dispatch_id':str(dispatch_id),'reservation_id':str(reservation_id),
                  'failed':failed,'raw_response':raw,
                  'request_hash':job.request_hash,'permission_hash':job.permission_hash,
                  'job_hash':digest(job.model_dump(mode='json')),'register_hash':job.register_hash,
                  'pricing_hash':digest(job.pricing.model_dump(mode='json')),
                  'key_fingerprint':self._key_fingerprint,'ledger_identity_hash':self._registry_hash,
                  'raw_response_hash':None if raw is None else hashlib.sha256(raw.encode()).hexdigest()}
        wire_metadata=self._receipts/(str(dispatch_id)+'.wire.json')
        record['wire_custody']=json.loads(wire_metadata.read_bytes()) if wire_metadata.exists() else None
        path = self._receipts / (str(dispatch_id)+'.json')
        descriptor = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(canonical_bytes(record));stream.flush();os.fsync(stream.fileno())

    def dispatch(self, body: bytes) -> bytes:
        if len(body)>2_000_000:
            raise PermissionError('bounded provider envelope required')
        try:
            envelope = json.loads(body,object_pairs_hook=_unique_object,parse_constant=_deny_constant)
            if not isinstance(envelope,dict) or set(envelope)!={'dispatch_id','request_hash','request'}:
                raise ValueError
            dispatch_id=UUID(envelope['dispatch_id'])
            if str(dispatch_id)!=envelope['dispatch_id']:
                raise ValueError
            job=self._resolve(dispatch_id)
            if not isinstance(job,NativeDispatchJob) or job.dispatch_id!=dispatch_id:
                raise ValueError
            # Do not retain shared mutable dictionaries returned by a resolver.
            job=NativeDispatchJob.model_validate_json(job.model_dump_json())
            encoded=canonical_bytes(envelope['request'])
            if (hashlib.sha256(encoded).hexdigest()!=job.request_hash
                    or envelope['request_hash']!=job.request_hash or encoded!=canonical_bytes(job.request)):
                raise ValueError
        except (ValueError,TypeError,KeyError):
            raise PermissionError('provider request differs from immutable admitted job') from None
        job_seal=digest(job.model_dump(mode='json'))
        def currently_authorized():
            return (digest(job.model_dump(mode='json'))==job_seal and self._authorize(job) is True
                    and digest(job.model_dump(mode='json'))==job_seal)
        if not currently_authorized():
            raise PermissionError('current job authority unavailable')
        if any((self._receipts/(str(dispatch_id)+suffix)).exists() for suffix in ('.json','.wire','.wire.json')):
            raise PermissionError('dispatch identity already has a retained response')
        # Processing permission precedes all provider pricing/key reads.
        authorize(job.processing_request,list(job.approvals))
        if (job.processing_request.account!='key-sha256:'+self._key_fingerprint
                or job.processing_request.provider!='openrouter'
                or job.processing_request.endpoint!='https://openrouter.ai/api/v1'
                or job.processing_request.purpose!=job.purpose or job.processing_request.fallback):
            raise PermissionError('exact existing key and source-only processing admission required')
        if self._registry.transport=='owned-synthetic-loopback' and not job.processing_request.data_classes<=frozenset({'synthetic'}):
            raise PermissionError('synthetic ledger cannot dispatch private company data')
        ledger_identity=verify_ledger(self._url,self._registry,trusted_registry_hash=self._registry_hash,
                                     key_fingerprint=self._key_fingerprint,now=datetime.now(timezone.utc))
        request=job.request
        embedding=request.get('model')=='openai/text-embedding-3-small'
        expected={'model','input','dimensions','encoding_format','store','provider'} if embedding else {'model','messages','max_tokens','response_format','store','stream','provider'}
        payload=request.get('input') if embedding else request.get('messages')
        output_bound=1 if embedding else request.get('max_tokens')
        policy={'only':['openai'],'allow_fallbacks':False,'require_parameters':True,'data_collection':'deny'}
        if (set(request)!=expected or request['provider']!=policy or request['store'] is not False
                or not isinstance(payload,list) or not payload
                or job.input_tokens_upper_bound<len(encoded)+1024*len(payload)):
            raise PermissionError('exact bounded native provider request required')
        if embedding:
            if (type(request['dimensions']) is not int or request['dimensions']!=256
                    or request['encoding_format']!='float'
                    or any(not isinstance(text,str) or not text for text in payload)):
                raise PermissionError('fixed bounded embedding input required')
        elif (request['stream'] is not False or request['response_format']!={'type':'json_object'}
                or request['model'] not in {'openai/gpt-6.1-sol','openai/gpt-6-astra'}
                or type(output_bound) is not int or not 1<=output_bound<=8192):
            raise PermissionError('exact bounded native chat request required')
        def before_private_dispatch():
            if not currently_authorized():
                raise PermissionError('current job authority changed before private POST')
            authorize(job.processing_request,list(job.approvals))
        def capture_paid_wire(raw,*,complete):
            rid=getattr(provider,'last_reservation_id',None)
            self._capture_wire(job,raw,rid,complete=complete)
        native=_AuthorizedNative(self._key,coverage_receipt=self._coverage,paid_wire_receiver=capture_paid_wire,
                               before_private_dispatch=before_private_dispatch,
                               trusted_coverage_hash=self._coverage_hash,ledger_identity_hash=ledger_identity)
        native._coverage(datetime.now(timezone.utc))
        current=native.pricing(model=request['model'],max_output_tokens=output_bound,register_hash=job.register_hash)
        model=[item for item in native._models_snapshot.get('data',[]) if item.get('id')==request['model']]
        lengths=([model[0].get('context_length')] if embedding else [model[0].get('context_length'),model[0].get('top_provider',{}).get('context_length')]) if len(model)==1 else []
        if (len(lengths)!=(1 if embedding else 2) or any(type(value) is not int or value<=0 for value in lengths)
                or job.input_tokens_upper_bound+(0 if embedding else output_bound)>min(lengths)):
            raise PermissionError('current complete model context cannot cover admitted input/output bounds')
        if (job.pricing.expires_at<=datetime.now(timezone.utc)
                or current.model_dump(exclude={'expires_at'})!=job.pricing.model_dump(exclude={'expires_at'})):
            raise PermissionError('current actual pricing differs from admitted job')
        provider=AdmittedProvider(request=job.processing_request,approvals=list(job.approvals),pricing=job.pricing,
            budget=Budget(self._url,ledger_identity_hash=ledger_identity),sender=native.embed if embedding else native.send,operation='embedding' if embedding else 'chat',
            remaining_daily_allowance=native.allowance,admitted_register_hash=job.register_hash)
        # Recheck immediately before reservation/send, after all preflight work.
        if not currently_authorized():
            raise PermissionError('job authority changed during preflight')
        validation_failed = False
        def validate_paid_response(content):
            nonlocal validation_failed
            try:
                if not currently_authorized():
                    raise ValueError('current validation authority unavailable')
                if embedding:
                    validate_embedding_response(content,count=len(payload))
                self._validate_response(job, content)
                if not currently_authorized():
                    raise ValueError('immutable job changed during validation')
            except Exception:
                validation_failed = True
                raise ValueError('trusted output validation rejected response') from None
        try:
            provider.extract(workspace_id=job.workspace_id,artifact_id=job.artifact_id,batch_id=job.batch_id,
                purpose=job.purpose,attempt=job.attempt,input_tokens_upper_bound=job.input_tokens_upper_bound,
                messages=payload,response_validator=validate_paid_response)
        except Exception:
            if hasattr(provider,'last_reservation_id'):
                self._record(job,getattr(native,'last_response_text',None),provider.last_reservation_id,failed=True)
            raise
        raw=getattr(native,'last_response_text',None)
        self._record(job,raw,provider.last_reservation_id,failed=validation_failed)
        authorize(job.processing_request,list(job.approvals))
        if not currently_authorized() or not isinstance(raw,str):
            raise PermissionError('current access to paid response unavailable')
        if validation_failed:
            raise ValueError('trusted output validation rejected response; diagnosis required')
        return raw.encode()


def validate_embedding_response(response, *, count):
    """Exact native vector identity and complete finite 256-dimension coverage."""
    from decimal import Decimal
    if (not isinstance(response,dict) or response.get('model')!='openai/text-embedding-3-small'
            or response.get('object')!='list' or not isinstance(response.get('data'),list)
            or len(response['data'])!=count):
        raise ValueError('embedding response identity/count mismatch')
    seen=set()
    for row in response['data']:
        if (not isinstance(row,dict) or set(row)!={'object','index','embedding'} or row['object']!='embedding'
                or type(row['index']) is not int or not 0<=row['index']<count or row['index'] in seen
                or not isinstance(row['embedding'],list) or len(row['embedding'])!=256):
            raise ValueError('embedding vector schema/dimension/index mismatch')
        seen.add(row['index'])
        for value in row['embedding']:
            if isinstance(value,bool) or not isinstance(value,(int,float,Decimal)) or not Decimal(str(value)).is_finite():
                raise ValueError('embedding vector contains nonfinite/non-numeric values')
