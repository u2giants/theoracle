"""Fixed raw-original SQL capabilities; constructors never issue appointments."""
from dataclasses import dataclass
from datetime import datetime,timezone
import re
from uuid import UUID

from pydantic import BaseModel,ConfigDict,Field,AwareDatetime,model_validator
from .contracts import canonical_bytes
from .original_qualification_v1 import RawOriginalPopulationV1
from .authority_adapter import ProcessingSourceResolver


class OriginalPopulationSnapshotV1(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    population:RawOriginalPopulationV1
    original_allocation_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    original_horizon:AwareDatetime
    actual_principal_id:UUID
    session_role:str=Field(pattern=r'^[a-z_][a-z0-9_]{0,62}$')
    checked_at:AwareDatetime
    valid_until:AwareDatetime

    @model_validator(mode='after')
    def current_original_limits(self):
        if not self.checked_at<self.valid_until<=self.population.expires_at<=self.original_horizon:
            raise ValueError('actual raw population current horizon required')
        return self


@dataclass(frozen=True)
class OriginalSourceBindingV1:
    population:RawOriginalPopulationV1
    principal:UUID
    purpose:str
    expected_owner_role:str
    expected_session_role:str
    original_allocation_hash:str
    original_horizon:datetime
    expires_at:datetime

    def __post_init__(self):
        if (type(self.population) is not RawOriginalPopulationV1 or type(self.principal) is not UUID
            or self.purpose not in {'source-original-reading','source-original-review'}
            or any(type(v) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',v)
                for v in (self.expected_owner_role,self.expected_session_role))
            or type(self.original_allocation_hash) is not str or not re.fullmatch(r'[0-9a-f]{64}',self.original_allocation_hash)
            or any(type(v) is not datetime or v.tzinfo is None or v.utcoffset() is None for v in (self.original_horizon,self.expires_at))
            or not self.expires_at<=self.population.expires_at<=self.original_horizon):
            raise PermissionError('complete immutable original phase binding required')


class OriginalSourceResolverV1:
    """Own actual login, complete registered population and current rooted grants.

    Protected startup must independently authenticate every binding pin. No raw
    file is opened here. The locator capability remains private to its consumer.
    """
    _signatures={
        'oracle2.original_population_current_v1(uuid)':frozenset({'oracle2_source_original_reader','oracle2_source_original_reviewer'}),
        'oracle2.original_revision_read_v1(uuid,integer)':frozenset({'oracle2_source_original_reader'}),
        'oracle2.original_revision_review_input_v1(uuid,integer)':frozenset({'oracle2_source_original_reviewer'}),
        'oracle2.commit_original_reading_response_v1(bytea)':frozenset({'oracle2_source_original_reader'}),
        'oracle2.commit_original_review_response_v1(bytea)':frozenset({'oracle2_source_original_reviewer'}),
        'oracle2.finalize_original_reading_qualification_v1(text,text,text)':frozenset({'oracle2_source_original_reviewer'}),
        'oracle2._commit_original_response(bytea,boolean)':frozenset(),
        'oracle2._original_model_identity_v1(text,text,name,text,uuid,text)':frozenset(),
        'oracle2._original_revision_access(uuid,integer,text)':frozenset(),
        'oracle2._original_revision_member_access(uuid,integer,text)':frozenset(),
        'oracle2._replacement_scope(uuid,uuid,text)':frozenset(),
        'oracle2._replacement_metadata_json(jsonb)':frozenset(),
    }

    def __init__(self,url,*,binding):
        if type(binding) is not OriginalSourceBindingV1:raise PermissionError('fixed original binding required')
        self.url,self.binding=url,binding
        with self._connection() as c:self._check(c)

    def _connection(self,connection=None):
        # Reuse the retained exact host/address/database/user/port comparison;
        # this helper supplies no processing profile or authority.
        return ProcessingSourceResolver._connection(self,connection)

    def _check(self,c):
        b=self.binding
        if datetime.now(timezone.utc)>=b.expires_at:raise PermissionError('original caller binding expired')
        params=c.info.get_parameters()
        if not c.pgconn.ssl_in_use or params.get('sslmode')!='verify-full':
            raise PermissionError('original authenticated verify-full TLS required')
        c.execute("SELECT set_config('statement_timeout',CASE WHEN current_setting('statement_timeout')='0' OR current_setting('statement_timeout')::interval>interval '5 seconds' THEN '5s' ELSE current_setting('statement_timeout') END,true)")
        c.execute("SELECT set_config('lock_timeout',CASE WHEN current_setting('lock_timeout')='0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN '2s' ELSE current_setting('lock_timeout') END,true)")
        group='oracle2_source_original_'+('reader' if b.purpose=='source-original-reading' else 'reviewer')
        role=c.execute('SELECT session_user,current_user,rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=session_user').fetchone()
        if not role or role[0]!=b.expected_session_role or role[1] not in {role[0],group} or not role[2] or any(role[3:]):
            raise PermissionError('actual original login differs')
        reachable=c.execute("SELECT rolname::text FROM pg_roles WHERE pg_has_role(session_user,oid,'MEMBER') OR pg_has_role(session_user,oid,'SET') OR pg_has_role(session_user,oid,'USAGE')").fetchall()
        if {r[0] for r in reachable}!={b.expected_session_role,group}:raise PermissionError('exclusive original group required')
        flags=c.execute('SELECT rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s',(group,)).fetchone()
        if flags is None or any(flags):raise PermissionError('fixed original group flags differ')
        owner=c.execute("SELECT r.rolname,pg_has_role(session_user,r.oid,'MEMBER') FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='oracle2'").fetchone()
        if owner!=(b.expected_owner_role,False):raise PermissionError('trusted original schema owner differs')
        ProcessingSourceResolver._check_function_signatures(self,c,self._signatures)

    def original_population_current_v1(self,population_id,*,connection=None):
        b=self.binding
        if type(population_id) is not UUID or population_id!=b.population.population_id:
            raise PermissionError('exact appointed raw population required')
        with self._connection(connection) as c:
            self._check(c)
            row=c.execute('SELECT oracle2.original_population_current_v1(%s)',(population_id,)).fetchone()
            self._check(c)
        if not row:raise PermissionError('current complete original population unavailable')
        snapshot=OriginalPopulationSnapshotV1.model_validate_json(canonical_bytes(row[0]))
        if (snapshot.population!=b.population or snapshot.actual_principal_id!=b.principal
            or snapshot.session_role!=b.expected_session_role or snapshot.original_allocation_hash!=b.original_allocation_hash
            or snapshot.original_horizon!=b.original_horizon):
            raise PermissionError('actual original appointment differs from protected pins')
        deadline=min(snapshot.valid_until,b.expires_at)
        if datetime.now(timezone.utc)>=deadline:raise PermissionError('current original population expired')
        return snapshot.model_copy(update={'valid_until':deadline})

    def original_revision_access_v1(self,source_id,revision,*,connection=None):
        b=self.binding;matches=[r for r in b.population.raw_refs if (r.source_id,r.revision)==(source_id,revision)]
        if type(source_id) is not UUID or type(revision) is not int or len(matches)!=1:
            raise PermissionError('exact appointed raw revision required')
        with self._connection(connection) as c:
            before=self.original_population_current_v1(b.population.population_id,connection=c)
            function='original_revision_read_v1' if b.purpose=='source-original-reading' else 'original_revision_review_input_v1'
            from psycopg import sql
            row=c.execute(sql.SQL('SELECT oracle2.{}(%s,%s)').format(sql.Identifier(function)),(source_id,revision)).fetchone()
            after=self.original_population_current_v1(b.population.population_id,connection=c)
            self._check(c)
        if not row or not isinstance(row[0],dict):raise PermissionError('private original capability unavailable')
        value=row[0];ref=matches[0]
        expected={'workspace_id':str(ref.workspace_id),'source_id':str(source_id),'revision':revision,
            'principal_id':str(b.principal),'population_id':str(b.population.population_id),'original_sha256':ref.original_sha256,
            'byte_count':ref.byte_count,'media_type':ref.media_type,'runtime_hash':b.population.runtime_hash,'registry_hash':b.population.source_registry_hash}
        if any(value.get(k)!=v for k,v in expected.items()):raise PermissionError('private original identity differs')
        deadline=min(before.valid_until,after.valid_until,datetime.fromisoformat(value['valid_until']))
        if datetime.now(timezone.utc)>=deadline:raise PermissionError('private original capability expired')
        return value|{'valid_until':deadline.isoformat()}


    def _write_original(self, operation):
        """Own transaction only. Return solely after the real connection commits."""
        import psycopg
        attempted=False
        try:
            with self._connection() as c:
                self.original_population_current_v1(self.binding.population.population_id,connection=c)
                self._check(c)
                attempted=True
                value=operation(c)
                self.original_population_current_v1(self.binding.population.population_id,connection=c)
                self._check(c)
            return value
        except (psycopg.OperationalError,psycopg.InterfaceError) as exc:
            if attempted and (exc.sqlstate is None or exc.sqlstate.startswith('08')):
                raise OriginalWriteOutcomeUnknownV1('original SQL write outcome UNKNOWN; no automatic retry') from exc
            raise

    def _commit_response_v1(self, raw, phase):
        from .original_qualification_v1 import parse_original_response_commit_v1
        import hashlib
        if type(raw) is not bytes or not 0<len(raw)<=65536:
            raise ValueError('bounded exact canonical commitment bytes required')
        commit=parse_original_response_commit_v1(raw,phase=phase)
        import json
        if canonical_bytes(json.loads(raw))!=raw:
            raise ValueError('canonical fixed commitment bytes required')
        b=self.binding
        if b.purpose!='source-original-'+phase:
            raise PermissionError('own exact original phase required')
        p=b.population
        if (commit.raw_ref not in p.raw_refs or commit.population_id!=p.population_id
                or commit.operation_registry_hash!=p.operation_registry_hash
                or commit.original_root_hash!=p.original_root_hash
                or commit.allocation_hash!=b.original_allocation_hash
                or commit.population_hash!=p.population_digest
                or commit.source_registry_hash!=p.source_registry_hash
                or commit.original_horizon!=b.original_horizon):
            raise PermissionError('complete current original commitment pins differ')
        def write(c):
            from psycopg import sql
            name='commit_original_'+phase+'_response_v1'
            row=c.execute(sql.SQL('SELECT oracle2.{}(%s)').format(sql.Identifier(name)),(raw,)).fetchone()
            if not row:raise PermissionError('actual original phase seal unavailable')
            seal=OriginalPhaseSealV1.model_validate_json(canonical_bytes(row[0]))
            if (seal.commit_sha256!=hashlib.sha256(raw).hexdigest() or seal.principal_id!=b.principal
                    or seal.session_role!=b.expected_session_role or seal.runtime_hash!=p.runtime_hash
                    or seal.population_id!=p.population_id or seal.operation_registry_hash!=p.operation_registry_hash
                    or seal.valid_until>b.expires_at or datetime.now(timezone.utc)>=seal.valid_until):
                raise PermissionError('actual original phase seal differs')
            return seal
        return self._write_original(write)

    def commit_original_reading_response_v1(self, raw):
        return self._commit_response_v1(raw,'reading')

    def commit_original_review_response_v1(self, raw):
        return self._commit_response_v1(raw,'review')

    def finalize_original_reading_qualification_v1(self, reading_seal, review_seal, reading_text):
        """SQL014 is the sole custody owner; no shared/borrowed transaction."""
        import hashlib
        b=self.binding
        if (b.purpose!='source-original-review' or type(reading_seal) is not OriginalPhaseSealV1
                or type(review_seal) is not OriginalPhaseSealV1
                or type(reading_text) is not str or not reading_text.strip()
                or len(reading_text.encode('utf-8'))>25*1024*1024):
            raise PermissionError('own reviewer and exact completed reading/seals required')
        if (review_seal.principal_id!=b.principal or review_seal.session_role!=b.expected_session_role
                or review_seal.population_id!=b.population.population_id
                or review_seal.runtime_hash!=b.population.runtime_hash
                or review_seal.operation_registry_hash!=b.population.operation_registry_hash
                or reading_seal.principal_id==review_seal.principal_id
                or reading_seal.session_role==review_seal.session_role):
            raise PermissionError('actual own independent review seal required')
        def write(c):
            row=c.execute('SELECT oracle2.finalize_original_reading_qualification_v1(%s,%s,%s)',
                (reading_seal.commit_sha256,review_seal.commit_sha256,reading_text)).fetchone()
            if not row:raise PermissionError('actual original qualification unavailable')
            seal=OriginalQualificationSealV1.model_validate_json(canonical_bytes(row[0]))
            matches=[ref for ref in b.population.raw_refs if
                (ref.workspace_id,ref.source_id,ref.revision,ref.original_sha256)==
                (seal.workspace_id,seal.source_id,seal.revision,seal.original_sha256)]
            if (len(matches)!=1 or seal.reading_sha256!=hashlib.sha256(reading_text.encode()).hexdigest()
                    or seal.reader_principal_id!=reading_seal.principal_id
                    or seal.reviewer_principal_id!=review_seal.principal_id
                    or seal.reader_commit!=reading_seal.commit_sha256
                    or seal.reviewer_commit!=review_seal.commit_sha256
                    or seal.valid_until>b.expires_at or datetime.now(timezone.utc)>=seal.valid_until):
                raise PermissionError('actual committed original qualification differs')
            return seal
        return self._write_original(write)


class OriginalWriteOutcomeUnknownV1(RuntimeError):
    """A write may have committed; do not retry or borrow a requester getter."""


class OriginalPhaseSealV1(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    commit_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    principal_id:UUID
    session_role:str=Field(pattern=r'^[a-z_][a-z0-9_]{0,62}$')
    runtime_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    population_id:UUID
    operation_registry_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    checked_at:AwareDatetime
    valid_until:AwareDatetime

    @model_validator(mode='after')
    def finite_window(self):
        if not self.checked_at<self.valid_until:
            raise ValueError('finite actual phase seal required')
        return self


class OriginalQualificationSealV1(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True,populate_by_name=False)
    schema_version:int=Field(ge=1,le=1)
    workspace_id:UUID=Field(alias='workspaceId')
    source_id:UUID=Field(alias='sourceId')
    revision:int=Field(ge=1)
    original_sha256:str=Field(alias='originalSha256',pattern=r'^[0-9a-f]{64}$')
    reading_sha256:str=Field(alias='readingSha256',pattern=r'^[0-9a-f]{64}$')
    parser_id:str=Field(alias='parserId',min_length=1,max_length=255)
    reader_principal_id:UUID=Field(alias='readerPrincipalId')
    reviewer_principal_id:UUID=Field(alias='reviewerPrincipalId')
    reader_commit:str=Field(alias='readerCommit',pattern=r'^[0-9a-f]{64}$')
    reviewer_commit:str=Field(alias='reviewerCommit',pattern=r'^[0-9a-f]{64}$')
    qualified:bool
    checked_at:AwareDatetime
    valid_until:AwareDatetime

    @model_validator(mode='after')
    def actual_distinct_review(self):
        if (self.qualified is not True or self.reader_principal_id==self.reviewer_principal_id
                or not self.checked_at<self.valid_until):
            raise ValueError('actual independent finite qualification required')
        return self

    @property
    def source_ref(self):
        from .source_receipts import SourceRef
        return SourceRef(workspace_id=self.workspace_id,source_id=self.source_id,revision=self.revision,
            original_sha256=self.original_sha256,reading_sha256=self.reading_sha256,parser_id=self.parser_id)
