"""Fixed technical channel export. Not a human Auth session or source grant.

No source DDL, JWT/role impersonation, callback, admin/storage client or wildcard.
Actual source RLS/SELECT denial remains denial. Document bytes require the
separate fixed ordinary-session current-capture owner; metadata is insufficient.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
import hashlib
import psycopg
from pydantic import AwareDatetime, Field, model_validator, field_validator

from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes, digest
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1, _pinned, _parse
from oracle_brain.operating_model.protected_sql_connection_v1 import _connection_v1
from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1, sql_execute_v1
from .migration_authority_v1 import MigrationAuthorityV1

SOURCE_TABLES = ('employees','employee_identities','channels','channel_participants','messages','message_attachments','documents')
IDENTITY_SQL = """SELECT e.id,ei.auth_user_id,ei.auth_provider::text,e.disabled_at,c.id,c.status::text,cp.employee_id
 FROM public.employees e JOIN public.employee_identities ei ON ei.employee_id=e.id
 JOIN public.channel_participants cp ON cp.employee_id=e.id JOIN public.channels c ON c.id=cp.channel_id
 WHERE e.id=%s AND ei.auth_user_id=%s AND ei.auth_provider::text=%s AND c.id=%s
 AND e.disabled_at IS NULL AND c.status::text='active'"""
MESSAGE_SQL = """SELECT id,channel_id,employee_id,role::text,
 CASE WHEN octet_length(content) BETWEEN 1 AND 1048576 AND sum(octet_length(content)) OVER()<=%s THEN content ELSE NULL END,
 octet_length(content),edited_at,deleted_at,created_at
 FROM public.messages WHERE id=ANY(%s::uuid[]) AND channel_id=%s AND role::text='user' AND deleted_at IS NULL ORDER BY id"""
DOCUMENT_SQL = """SELECT d.id,d.uploader_id,d.file_name,d.file_type,d.storage_bucket,d.storage_path,d.created_at,
 a.id,a.message_id,m.channel_id,m.employee_id,m.role::text,m.deleted_at,m.edited_at
 FROM public.documents d JOIN public.message_attachments a ON a.document_id=d.id JOIN public.messages m ON m.id=a.message_id
 WHERE d.id=ANY(%s::uuid[]) AND m.id=ANY(%s::uuid[]) AND m.channel_id=%s
 AND m.role::text='user' AND m.deleted_at IS NULL ORDER BY d.id,a.id"""


class TechnicalLegacyScopeV1(StrictRecord):
    @field_validator('schema_version', mode='before')
    @classmethod
    def _exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('exact schema version required')
        return value

    source_database_identity: UUID
    employee_id: UUID
    auth_user_id: UUID
    auth_provider: Literal['microsoft','google','authentik','magic_link_dev']
    channel_id: UUID
    message_ids: tuple[UUID, ...] = Field(max_length=10000)
    document_ids: tuple[UUID, ...] = Field(max_length=10000)

    @model_validator(mode='after')
    def _finite(self):
        if (len(self.message_ids)+len(self.document_ids)>10000
                or any(len(ids)!=len(set(ids)) or ids!=tuple(sorted(ids,key=str)) for ids in (self.message_ids,self.document_ids))):
            raise ValueError('one finite deterministic source allowlist required')
        return self

    def sql_scope_v1(self):
        return self.model_dump(mode='json',exclude={'schema_version'})


class LegacyExportProfileV1(StrictRecord):
    @field_validator('schema_version', mode='before')
    @classmethod
    def _exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('exact schema version required')
        return value

    purpose: Literal['technical-legacy-channel-export-v1']
    permission_producer_kind: Literal['technical-channel-v1']
    source_scope: TechnicalLegacyScopeV1
    database_url: ProtectedInputV1
    database_ca: ProtectedInputV1
    session_role: str = Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    source_catalog_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_program_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    document_capture_profile: ProtectedInputV1 | None = None
    max_original_bytes: int = Field(strict=True,ge=1,le=64*1024*1024)
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def _window(self):
        if (not self.valid_from<self.expires_at<=self.original_horizon
                or any(v.utcoffset()!=timezone.utc.utcoffset(v) for v in (self.valid_from,self.expires_at,self.original_horizon))):
            raise ValueError('original finite technical export lease required')
        return self


def actual_export_program_sha256_v1():
    base = Path(__file__).resolve().parents[1]
    paths = ('migration/legacy_export_reader_v1.py','migration/migration_authority_v1.py','migration/migration_settings_v1.py','hosting/legacy_migration_v1.py',
        'migration/legacy_storage_capture_v1.py','migration/_legacy_s3_signing_v1.py',
        'operating_model/protected_http_wire_v1.py',
        'operating_model/contracts.py','operating_model/protected_inputs_v1.py',
        'operating_model/protected_sql_connection_v1.py','operating_model/request_deadline_v1.py')
    return digest({p:hashlib.sha256((base/p).read_bytes()).hexdigest() for p in paths})


def _message_metadata_v1(row):
    # Bound JSON work independently of raw UTF8 escaping. Exact original bytes
    # still participate by their actually observed hash/count, not caller hash.
    if row is None:
        return None
    if type(row) not in (list, tuple) or len(row) != 9:
        raise PermissionError('exact actual message row required')
    body = row[4]
    if body is not None and type(body) is not str:
        raise PermissionError('exact actual source text required')
    raw = body.encode('utf8') if body is not None else None
    if type(row[5]) is not int or row[5] < 0 or raw is not None and len(raw) != row[5]:
        raise PermissionError('actual source byte count differs')
    return [*row[:4], {'observed_sha256':hashlib.sha256(raw).hexdigest() if raw is not None else None,
        'available':raw is not None}, *row[5:]]


def _json(value):
    if isinstance(value, UUID):return str(value)
    if isinstance(value, datetime):return value.isoformat()
    if isinstance(value, (list,tuple)):return [_json(v) for v in value]
    if isinstance(value,dict):return {k:_json(v) for k,v in value.items()}
    return value


@dataclass(frozen=True)
class ExportedLegacyMessageV1:
    legacy_id: UUID
    metadata_sha256: str
    original_sha256: str
    byte_count: int
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class ExportedLegacyDocumentV1:
    legacy_id: UUID
    metadata_sha256: str
    original_sha256: str
    byte_count: int
    data: bytes = field(repr=False)
    capture: dict = field(repr=False)
    media_type: Literal['application/pdf'] = 'application/pdf'


def stable_inventory_entries_v1(entries):
    # Recapture observations are documentary history, never a new original
    # version or a reason to make every subsequent currentness pass unequal.
    return [{k:v for k,v in entry.items() if k!='capture'} for entry in entries]


@dataclass(frozen=True)
class TechnicalLegacySnapshotV1:
    inventory_bytes: bytes = field(repr=False)
    messages: tuple[ExportedLegacyMessageV1,...] = field(repr=False)
    projection_sha256: str
    valid_until: datetime
    human_auth_session_proven: Literal[False] = False
    qualified_source: Literal[False] = False
    consistent_boundary_proven: Literal[False] = False
    documents: tuple[ExportedLegacyDocumentV1,...] = field(default=(),repr=False)


class TechnicalLegacyExportReaderV1:
    def __init__(self, profile_path, profile_sha256, authority):
        if type(authority) is not MigrationAuthorityV1 or authority.settings.config.operation!='snapshot-register':
            raise TypeError('actual own current snapshot/export SQL consumer required')
        self.path,self.sha256,self.authority = Path(profile_path),profile_sha256,authority
        self.profile = _parse(LegacyExportProfileV1,_pinned(self.path,self.sha256,2*1024*1024))
        self.url = _pinned(self.profile.database_url.path,self.profile.database_url.sha256,16384).decode('utf8')
        self.params = psycopg.conninfo.conninfo_to_dict(self.url)
        allowed = {'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','application_name'}
        if (set(self.params)-allowed or any(not self.params.get(k) for k in ('host','port','dbname','user','password'))
                or self.params['user']!=self.profile.session_role or self.params.get('sslmode')!='verify-full'
                or self.params.get('sslrootcert')!=self.profile.database_ca.path):
            raise PermissionError('fixed private readonly source target required')
        self._installed()
        self.document_capture = None
        if self.profile.document_capture_profile is not None:
            from .legacy_storage_capture_v1 import LegacyDocumentCaptureV1
            selected=self.profile.document_capture_profile
            self.document_capture=LegacyDocumentCaptureV1(selected.path,selected.sha256,self)

    def _installed(self):
        value = _parse(LegacyExportProfileV1,_pinned(self.path,self.sha256,2*1024*1024))
        c = self.authority.settings.config
        if (value!=self.profile or c.descriptor_sha256!=self.sha256
                or c.source_scope_sha256!=digest(value.source_scope.sql_scope_v1())
                or c.source_program_sha256!=value.source_program_sha256
                or actual_export_program_sha256_v1()!=value.source_program_sha256):
            raise PermissionError('actual fixed export program/scope/installation changed')
        if value.document_capture_profile is not None:
            selected=value.document_capture_profile
            _pinned(selected.path,selected.sha256,131072)
        _pinned(value.database_ca.path,value.database_ca.sha256,131072)
        _pinned(value.database_url.path,value.database_url.sha256,16384)
        now=datetime.now(timezone.utc)
        if not value.valid_from<=now<min(value.expires_at,value.original_horizon):
            raise PermissionError('original technical export installation expired')
        return min(value.expires_at,value.original_horizon)

    def _time(self, deadline):
        bound=self._installed()
        self.authority._time(deadline)
        if deadline>bound:raise PermissionError('original export deadline exceeds installation')
        return request_remaining_v1()

    def _execute(self, connection, deadline, query, params=()):
        self._time(deadline)
        value=sql_execute_v1(connection,deadline,query,params)
        self._time(deadline)
        return value

    def _check(self, connection, deadline):
        self._time(deadline)
        actual=connection.info.get_parameters()
        if (any(str(actual.get(k,''))!=str(self.params.get(k,'')) for k in ('host','dbname','user','sslmode','sslrootcert'))
                or connection.info.hostaddr!=(self.params.get('hostaddr') or self.params['host'])
                or not connection.pgconn.ssl_in_use or connection.info.host!=self.params['host']
                or connection.info.port!=int(self.params['port']) or connection.info.dbname!=self.params['dbname']):
            raise PermissionError('actual source TLS/target differs')
        role=self._execute(connection,deadline,"""SELECT SESSION_USER,current_user,current_database(),r.rolcanlogin,
          r.rolsuper,r.rolbypassrls,r.rolcreatedb,r.rolcreaterole,r.rolreplication,
          EXISTS(SELECT 1 FROM pg_roles x WHERE x.oid<>r.oid AND(pg_has_role(r.oid,x.oid,'MEMBER') OR pg_has_role(r.oid,x.oid,'SET') OR pg_has_role(r.oid,x.oid,'USAGE'))),
          current_setting('transaction_read_only'),current_setting('transaction_isolation') FROM pg_roles r WHERE r.rolname=SESSION_USER""").fetchone()
        if role!=(self.profile.session_role,self.profile.session_role,self.params['dbname'],True,False,False,False,False,False,False,'on','repeatable read'):
            raise PermissionError('actual non-bypass direct readonly source role required')
        catalog=self._execute(connection,deadline,"""SELECT c.relname,pg_get_userbyid(c.relowner),c.relrowsecurity,c.relforcerowsecurity,
          coalesce((SELECT jsonb_agg(jsonb_build_array(a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull) ORDER BY a.attnum)
            FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),'[]'::jsonb),
          coalesce((SELECT jsonb_agg(jsonb_build_array(p.polname,p.polcmd,p.polpermissive,p.polroles,pg_get_expr(p.polqual,p.polrelid),pg_get_expr(p.polwithcheck,p.polrelid)) ORDER BY p.polname)
            FROM pg_policy p WHERE p.polrelid=c.oid),'[]'::jsonb),
          coalesce((SELECT jsonb_agg(jsonb_build_array(CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable) ORDER BY x.grantee,x.privilege_type,x.is_grantable)
            FROM aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x),'[]'::jsonb),
          has_table_privilege(SESSION_USER,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname=ANY(%s::text[]) ORDER BY c.relname""",(list(SOURCE_TABLES),)).fetchall()
        if (len(catalog)!=len(SOURCE_TABLES) or {r[0] for r in catalog}!=set(SOURCE_TABLES)
                or any(r[1]==self.profile.session_role or r[2] is not True or r[-1] is not False for r in catalog)
                or digest(_json(catalog))!=self.profile.source_catalog_sha256):
            raise PermissionError('actual readonly source catalog/RLS/policy changed')

    def _pass(self, deadline):
        p=self.profile;s=p.source_scope
        self._time(deadline)
        with _connection_v1(self.url,deadline) as connection:
            # First logical SQL after common BEGIN. No auth/session claims/role.
            self._execute(connection,deadline,'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            self._check(connection,deadline)
            identity=self._execute(connection,deadline,IDENTITY_SQL,(s.employee_id,s.auth_user_id,s.auth_provider,s.channel_id)).fetchall()
            if len(identity)!=1:raise PermissionError('actual current technical identity/channel/member unavailable')
            messages=self._execute(connection,deadline,MESSAGE_SQL,(p.max_original_bytes,list(s.message_ids),s.channel_id)).fetchall()
            documents=self._execute(connection,deadline,DOCUMENT_SQL,(list(s.document_ids),list(s.message_ids),s.channel_id)).fetchall()
            observed=self._execute(connection,deadline,"SELECT transaction_timestamp(),pg_current_snapshot()::text").fetchone()
            self._check(connection,deadline)
        # Both actual source socket and every target socket are closed before
        # processing original buffers or crossing into private target storage.
        self._time(deadline)
        if len(messages)!=len({r[0] for r in messages}) or len(documents)!=len({(r[0],r[7]) for r in documents}):
            raise PermissionError('duplicate actual source identity/link')
        if (any(r[0] not in s.message_ids or r[1]!=s.channel_id or r[3]!='user' or r[7] is not None for r in messages)
                or any(r[0] not in s.document_ids or r[8] not in s.message_ids or r[9]!=s.channel_id or r[11]!='user' or r[12] is not None for r in documents)):
            raise PermissionError('actual finite source row membership differs')
        projection=digest(_json({'identity':identity,'messages':[_message_metadata_v1(r) for r in messages],'documents':documents}))
        return projection,messages,documents,observed

    def snapshot_v1(self, *, caller_deadline):
        self._time(caller_deadline)
        before=self.authority.source_context_v1(caller_deadline=caller_deadline)
        if before.get('permission_producer_kind')!='technical-channel-v1':
            raise PermissionError('actual technical source-export kind not independently admitted')
        first=self._pass(caller_deadline)
        second=self._pass(caller_deadline)
        if first[0]!=second[0]:raise PermissionError('current source membership/content/permission/attachment changed')
        current=self.authority.source_context_v1(caller_deadline=caller_deadline)
        self._time(caller_deadline)
        scope=self.profile.source_scope;permission=digest(_json({'scope':scope.sql_scope_v1(),'projection':second[0]}))
        rows=[];bodies=[];documents=[];messages={row[0]:row for row in second[1]}
        for selected in scope.message_ids:
            row=messages.get(selected);data=None
            if row is not None and type(row[4]) is str:
                candidate=row[4].encode('utf8')
                if 1<=len(candidate)<=1048576 and candidate.decode('utf8').strip() and b'\0' not in candidate:
                    data=candidate
            metadata=digest(_json({'kind':'message','legacy_id':selected,'record':_message_metadata_v1(row),'permission':permission}))
            sha=hashlib.sha256(data).hexdigest() if data is not None else None
            rows.append(dict(legacy_kind='message',legacy_id=str(selected),metadata_sha256=metadata,permission_sha256=permission,
                original_sha256=sha,byte_count=len(data) if data is not None else None,media_type='text/plain' if data is not None else None,capture=None,disposition='message-eligible' if data is not None else ('source-bytes-unavailable' if row is not None else 'missing')))
            if data is not None:bodies.append(ExportedLegacyMessageV1(selected,metadata,sha,len(data),data))
        for selected in scope.document_ids:
            linked=[r for r in second[2] if r[0]==selected]
            metadata=digest(_json({'kind':'document','legacy_id':selected,'links':linked,'permission':permission}))
            captured=None;reason='document-custody-unavailable' if linked else 'missing'
            if linked and self.document_capture is not None:
                from .legacy_storage_capture_v1 import LegacyCaptureUnavailable
                try:
                    used=sum(m.byte_count for m in bodies)+sum(d.byte_count for d in documents)
                    captured=self.document_capture.capture_document_v1(selected,caller_deadline=caller_deadline,
                        remaining_aggregate_bytes=max(0,self.profile.max_original_bytes-used))
                except LegacyCaptureUnavailable as error:
                    reason=error.reason
            if captured is not None:
                documents.append(ExportedLegacyDocumentV1(selected,metadata,captured.original_sha256,
                    captured.byte_count,captured.data,captured.capture))
            rows.append(dict(legacy_kind='document',legacy_id=str(selected),metadata_sha256=metadata,
                permission_sha256=permission,original_sha256=captured.original_sha256 if captured else None,
                byte_count=captured.byte_count if captured else None,media_type='application/pdf' if captured else None,
                capture=captured.capture if captured else None,disposition='document-current-capture-eligible' if captured else reason))
        final=self._pass(caller_deadline)
        if final[0]!=second[0]:raise PermissionError('current source changed during private document capture')
        current=self.authority.source_context_v1(caller_deadline=caller_deadline)
        self._time(caller_deadline)
        rows.sort(key=lambda r:(r['legacy_kind'],r['legacy_id']))
        c=self.authority.settings.config
        raw=canonical_bytes(dict(schema_version=1,inventory_id=str(uuid4()),descriptor_sha256=c.descriptor_sha256,
            source_scope_sha256=c.source_scope_sha256,source_program_sha256=c.source_program_sha256,
            source_observation_sha256=digest(_json({'first':first[3],'second':second[3],'projection':second[0]})),
            source_observed_at=second[3][0].astimezone(timezone.utc).isoformat(),declared_count=len(rows),entries=rows))
        if len(raw)>64*1024*1024:raise PermissionError('bounded complete inventory unavailable; never truncate')
        return TechnicalLegacySnapshotV1(raw,tuple(bodies),second[0],min(caller_deadline,datetime.fromisoformat(current['valid_until'])),documents=tuple(documents))
