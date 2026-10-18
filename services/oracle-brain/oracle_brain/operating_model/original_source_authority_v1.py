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
