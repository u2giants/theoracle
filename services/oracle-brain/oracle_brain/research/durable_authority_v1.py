"""Fixed SQL023 consumer. Registration/rights/roles are independent installation.

This module performs no network fetch, source approval or appointment issuance.
All writes retain uncertain outcomes; a lost claim is never replayed for a body.
"""
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime,timezone
from ipaddress import ip_address
from typing import Literal
from uuid import UUID
import hashlib,os
import psycopg
from psycopg import sql
from pydantic import AwareDatetime,Field,field_validator,model_validator
from ..operating_model.contracts import StrictRecord,canonical_bytes
from ..operating_model.protected_inputs_v1 import ProtectedInputV1,_pinned,_parse
from ..operating_model.request_deadline_v1 import request_remaining_v1,_sql_window_v1,_sql_send_window_v1,sql_execute_v1
from .registry import Source

HASH=r'^[a-f0-9]{64}$'
SIGNATURES=(
 '_research_admission_v1(uuid,text,text,text,text,timestamptz)',
 '_research_context_v1(oracle2.research_admissions_v1)',
 'research_claim_due_v1(uuid,text,text,text,timestamptz)',
 'research_force_due_v1(uuid,text,text,text,timestamptz)',
 'research_pending_queue_v1(uuid,text,text,text,timestamptz)',
 'research_claim_fetch_v1(uuid,uuid,text,text,text,timestamptz)',
 'research_fetch_current_v1(uuid,uuid,uuid,text,text,text,timestamptz)',
 'research_observe_fetch_v1(uuid,uuid,bytea,uuid,text,text,text,timestamptz)',
 'research_current_v1(uuid,text,text,text,timestamptz)',
 'research_latest_reference_v1(uuid,text,text,text,timestamptz)',
 'research_retained_fetch_v1(uuid,uuid,text,text,text,timestamptz)',
 'research_status_v1(uuid,text,text,text,timestamptz)')
_NAMES=frozenset(s.split('(')[0] for s in SIGNATURES)

class ResearchConfigV1(StrictRecord):
    schema_version:Literal[1]
    purpose:Literal['maintained-research-v1']
    admission_id:UUID;principal_id:UUID;workspace_id:UUID;source_id:UUID
    source_revision:int=Field(strict=True,ge=1)
    operation:Literal['schedule','fetch','read']
    session_role:str=Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    expected_owner:str=Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH)
    issuer_actor:UUID;reviewer_actor:UUID
    database_url:ProtectedInputV1;database_ca:ProtectedInputV1
    database_host:str;database_hostaddr:str;database_port:int=Field(strict=True,ge=1,le=65535)
    database_name:str=Field(min_length=1,max_length=63)
    capability_body_hashes:tuple[tuple[str,str],...]
    original_horizon:AwareDatetime;expires_at:AwareDatetime
    fetch_profile:ProtectedInputV1|None=None
    read_profile:ProtectedInputV1|None=None

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact research schema version required')
        return value

    @model_validator(mode='after')
    def independent(self):
        if (self.issuer_actor==self.reviewer_actor or self.principal_id in(self.issuer_actor,self.reviewer_actor)
                or self.session_role==self.expected_owner or self.expires_at>self.original_horizon):
            raise ValueError('independent finite research installation required')
        if (not self.database_host or any(c in self.database_host for c in ',/\\ \t\n\r')
                or str(ip_address(self.database_hostaddr))!=self.database_hostaddr):
            raise ValueError('one independently pinned SQL address required')
        pairs=self.capability_body_hashes
        import re
        if (len(pairs)!=len(_NAMES) or set(dict(pairs))!=_NAMES
                or any(not re.fullmatch(HASH,h) for _,h in pairs)):
            raise ValueError('complete exact research capability fingerprints required')
        return self

@dataclass(frozen=True)
class ResearchSettingsV1:
    config:ResearchConfigV1
    config_path:str
    config_sha256:str

    def current(self,deadline):
        remaining=request_remaining_v1()
        c=_parse(ResearchConfigV1,_pinned(self.config_path,self.config_sha256))
        now=datetime.now(timezone.utc)
        if (c!=self.config or not isinstance(deadline,datetime) or deadline.tzinfo is None
                or not now<deadline<=min(c.expires_at,c.original_horizon)
                or (deadline-now).total_seconds()>30):
            raise PermissionError('current original research request required')
        _pinned(c.database_ca.path,c.database_ca.sha256,131072)
        return min(remaining,(deadline-now).total_seconds())

def load_research_settings_v1(path,seal):
    c=_parse(ResearchConfigV1,_pinned(path,seal))
    return ResearchSettingsV1(c,str(path),seal)

class ResearchOutcomeUnknown(PermissionError):
    """Write may have committed. No replay or replacement fetch is authorized."""

class ResearchAuthorityV1:
    def __init__(self,settings):
        if type(settings) is not ResearchSettingsV1:raise TypeError('exact installed research settings required')
        self.settings=settings

    @contextmanager
    def _connect(self,deadline):
        s=self.settings;c=s.config;remaining=s.current(deadline)
        # libpq enforces a two-second minimum per target. A single hostaddr
        # prevents repeated connect budgets and avoids an unbounded DNS call.
        if remaining<=2.002:raise PermissionError('research connection window too short')
        if any(name.startswith('PG') for name in os.environ):
            raise PermissionError('SQL environment overrides forbidden')
        raw=_pinned(c.database_url.path,c.database_url.sha256).decode('utf-8')
        p=psycopg.conninfo.conninfo_to_dict(raw)
        allowed={'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert'}
        if (set(p)-allowed or p.get('host')!=c.database_host or p.get('hostaddr')!=c.database_hostaddr
                or p.get('port')!=str(c.database_port) or p.get('dbname')!=c.database_name
                or p.get('user')!=c.session_role or p.get('sslmode')!='verify-full'
                or p.get('sslrootcert')!=c.database_ca.path):
            raise PermissionError('exact pinned research SQL target required')
        remaining=s.current(deadline)
        if remaining<=2.002:raise PermissionError('research connection window too short')
        first=max(1,min(2000,int((remaining-2-.001)*1000)))
        with psycopg.connect(raw,connect_timeout=2,tcp_user_timeout=max(1,int(min(2,remaining-2)*1000)),
                options=f'-c statement_timeout={first}ms -c lock_timeout={min(2000,first)}ms',autocommit=True) as connection:
            with _sql_window_v1(connection,deadline,armed_timeout_ms=first):
                s.current(deadline);info=connection.info
                if (not connection.pgconn.ssl_in_use or info.host!=c.database_host or info.hostaddr!=c.database_hostaddr
                        or info.port!=c.database_port or info.dbname!=c.database_name or info.user!=c.session_role):
                    raise PermissionError('actual research connection differs')
                sql_execute_v1(connection,deadline,'BEGIN ISOLATION LEVEL READ COMMITTED')
                yield connection
                s.current(deadline);_sql_send_window_v1(connection,deadline)
        s.current(deadline)

    def _catalog(self,connection,deadline):
        s=self.settings;c=s.config;s.current(deadline)
        if sql_execute_v1(connection,deadline,'SELECT session_user,current_user').fetchone()!=(c.session_role,c.session_role):
            raise PermissionError('actual research login changed')
        s.current(deadline)
        rows=sql_execute_v1(connection,deadline,'''SELECT p.proname,pg_get_userbyid(p.proowner),p.prosecdef,p.proconfig,
          encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),
          NOT EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x
            WHERE x.grantee<>p.proowner AND (left(p.proname,1)='_' OR x.grantee=0 OR x.is_grantable
              OR NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid=x.grantee AND r.rolcanlogin
                AND NOT(r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication)
                AND NOT EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid)))),
          has_function_privilege(current_user,p.oid,'EXECUTE')
          FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='oracle2'
          AND p.oid IN(SELECT to_regprocedure(x) FROM unnest(%s::text[]) x)''',
          (['oracle2.'+x for x in SIGNATURES],)).fetchall()
        if (len(rows)!=len(_NAMES) or {r[0] for r in rows}!=_NAMES
                or any(owner!=c.expected_owner or defin is not True or search!=['search_path=pg_catalog, oracle2']
                    or seal!=dict(c.capability_body_hashes)[name] or acl is not True
                    for name,owner,defin,search,seal,acl,_ in rows)):
            raise PermissionError('pinned research owner/body/searchpath/ACL differs')
        s.current(deadline)

    def _context(self,result,deadline):
        c=self.settings.config
        if type(result) is not dict or result.get('schema_version')!=1 or type(result.get('schema_version')) is not int:
            raise PermissionError('closed research SQL response required')
        context=result.get('context')
        expected=dict(admission_id=str(c.admission_id),principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),
            source_id=str(c.source_id),source_revision=c.source_revision,session_role=c.session_role,operation=c.operation,
            runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,config_hash=self.settings.config_sha256,
            issuer_actor=str(c.issuer_actor),reviewer_actor=str(c.reviewer_actor))
        if type(context) is not dict or set(context)!=set(expected)|{'valid_until'} or any(type(context[k]) is not type(v) or context[k]!=v for k,v in expected.items()):
            raise PermissionError('actual research context differs from installation')
        bound=datetime.fromisoformat(context['valid_until'])
        if not datetime.now(timezone.utc)<bound<=deadline:raise PermissionError('research context expired or renewed')
        self.settings.current(deadline)
        return result

    def _response(self,name,result,deadline):
        self._context(result,deadline)
        base={'schema_version','context'}
        fields={
            'research_current_v1':set(),
            'research_pending_queue_v1':{'state','run_id','queue_authorized','fetch_authorized'},
            'research_latest_reference_v1':{'state','workspace_id','source_id','source_revision','definition','definition_sha256','run_id','claim_id','original_deadline','receipt_event_id','recorded_at','observation','company_policy','semantically_reviewed'},
            'research_retained_fetch_v1':{'run_id','claim_id','state','original_deadline','resend_authorized'},
            'research_fetch_current_v1':{'run_id','claim_id','current','valid_until','resend_authorized'},
            'research_observe_fetch_v1':{'state','run_id','resend_authorized'},
            'research_status_v1':{'workspace_id','source_id','source_revision','publisher','original_url','access','cadence',
                'last_success','next_due','attempts','exhausted','run_id','state','company_policy','semantically_reviewed','valid_until'},
        }
        state=result.get('state')
        if name=='research_claim_due_v1':
            if state not in ('existing','not_due','pending'):raise PermissionError('closed scheduler state required')
            wanted={'state','dispatch_authorized'} | ({'run_id'} if state!='not_due' else set()) | ({'valid_until'} if state=='pending' else set())
        elif name=='research_force_due_v1':
            if state not in ('existing','exhausted','due'):raise PermissionError('closed urgency state required')
            wanted={'state','dispatch_authorized'} | ({'run_id'} if state!='due' else set())
        elif name=='research_claim_fetch_v1':
            if state not in ('INFLIGHT','UNKNOWN'):raise PermissionError('closed fetch state required')
            wanted={'state','run_id','fetch_authorized'}
            if state=='INFLIGHT':wanted|={'claim_id','workspace_id','source_id','source_revision','definition','definition_sha256','valid_until'}
        else:wanted=fields[name]
        if set(result)!=base|wanted:raise PermissionError('closed research response fields required')
        for key in ('dispatch_authorized','queue_authorized','fetch_authorized','current','resend_authorized','exhausted','company_policy','semantically_reviewed'):
            if key in result and type(result[key]) is not bool:raise PermissionError('exact research boolean required')
        if result.get('resend_authorized',False) or result.get('company_policy',False) or result.get('semantically_reviewed',False):
            raise PermissionError('research response cannot confer acceptance or resend authority')
        if 'dispatch_authorized' in result and result['dispatch_authorized'] is not (name=='research_claim_due_v1' and state=='pending'):
            raise PermissionError('dispatch authority differs from durable state')
        if 'fetch_authorized' in result and result['fetch_authorized'] is not (name=='research_claim_fetch_v1' and state=='INFLIGHT'):
            raise PermissionError('fetch authority differs from durable state')
        if name=='research_pending_queue_v1' and (state not in ('idle','pending','INFLIGHT','UNKNOWN','observed')
                or result['queue_authorized'] is not (state=='pending')
                or (state=='idle') is not (result['run_id'] is None)):
            raise PermissionError('closed pending-only opaque queue state required')
        for key in ('run_id','claim_id','workspace_id','source_id','receipt_event_id'):
            if key in result and result[key] is not None:
                if type(result[key]) is not str or str(UUID(result[key]))!=result[key]:raise PermissionError('canonical research identity required')
        for key,expected in (('workspace_id',self.settings.config.workspace_id),('source_id',self.settings.config.source_id),('source_revision',self.settings.config.source_revision)):
            if key in result and (type(result[key]) is not type(str(expected) if isinstance(expected,UUID) else expected) or result[key]!=(str(expected) if isinstance(expected,UUID) else expected)):
                raise PermissionError('research response source differs')
        for key in ('valid_until','last_success','next_due','original_deadline','recorded_at'):
            if key in result and result[key] is not None:
                if type(result[key]) is not str:raise PermissionError('research timestamp string required')
                stamp=datetime.fromisoformat(result[key])
                if stamp.tzinfo is None:raise PermissionError('aware research timestamp required')
                if key=='valid_until' and not datetime.now(timezone.utc)<stamp<=deadline:raise PermissionError('research lease renewed or expired')
        if name=='research_observe_fetch_v1' and state not in ('observed','UNKNOWN','duplicate'):
            raise PermissionError('closed observation state required')
        if name=='research_status_v1':
            if (state not in ('disabled','rights_gap','UNKNOWN','INFLIGHT','pending','observed','idle')
                    or result['access'] not in ('public','licensed','member') or result['cadence'] not in ('weekly','quarterly')
                    or type(result['attempts']) is not int or not 0<=result['attempts']<=4
                    or any(type(result[k]) is not str or not result[k] for k in ('publisher','original_url'))):
                raise PermissionError('closed research metadata required')
        return result

    def _call(self,name,args,deadline,*,write):
        if name not in _NAMES or name.startswith('_'):raise PermissionError('fixed research capability required')
        attempted=False
        try:
            with self._connect(deadline) as connection:
                self._catalog(connection,deadline)
                c=self.settings.config
                parameters=(*args,c.admission_id,c.runtime_hash,c.registry_hash,self.settings.config_sha256,deadline)
                self.settings.current(deadline)
                attempted=write
                result=sql_execute_v1(connection,deadline,sql.SQL('SELECT oracle2.{}({})').format(sql.Identifier(name),
                    sql.SQL(',').join(sql.Placeholder() for _ in parameters)),parameters).fetchone()[0]
                result=self._response(name,result,deadline)
                self._catalog(connection,deadline)
            self.settings.current(deadline)
            # Re-prove actual SQL authority on a new connection after the
            # first commit AND close, before returning any retained metadata.
            # Replaying a body-bearing claim is expressly not this operation.
            with self._connect(deadline) as fresh:
                self._catalog(fresh,deadline)
                c=self.settings.config
                checked=sql_execute_v1(fresh,deadline,'SELECT oracle2.research_current_v1(%s,%s,%s,%s,%s)',
                    (c.admission_id,c.runtime_hash,c.registry_hash,self.settings.config_sha256,deadline)).fetchone()[0]
                self._response('research_current_v1',checked,deadline)
            self.settings.current(deadline)
            return self._response(name,result,deadline)
        except Exception as exc:
            if attempted:raise ResearchOutcomeUnknown('research outcome UNKNOWN; no replay authorized') from exc
            if isinstance(exc,PermissionError):raise
            raise PermissionError('current research authority withheld') from exc

    def schedule_due_v1(self,*,deadline):
        if self.settings.config.operation!='schedule':raise PermissionError('separate scheduler appointment required')
        return self._call('research_claim_due_v1',(),deadline,write=True)

    def pending_queue_v1(self,*,deadline):
        if self.settings.config.operation!='schedule':raise PermissionError('separate scheduler appointment required')
        return self._call('research_pending_queue_v1',(),deadline,write=False)

    def force_due_v1(self,*,deadline):
        if self.settings.config.operation!='schedule':raise PermissionError('separate scheduler appointment required')
        return self._call('research_force_due_v1',(),deadline,write=True)

    def claim_fetch_v1(self,run_id,*,deadline):
        if self.settings.config.operation!='fetch' or type(run_id) is not UUID:raise PermissionError('fixed fetch appointment/run required')
        result=self._call('research_claim_fetch_v1',(run_id,),deadline,write=True)
        if result.get('fetch_authorized') is True:
            try:
                definition=result.get('definition');Source(**definition)
                if hashlib.sha256(canonical_bytes(definition)).hexdigest()!=result.get('definition_sha256'):
                    raise ValueError('definition differs')
            except Exception as exc:
                raise ResearchOutcomeUnknown('claimed definition differs; no replacement claim authorized') from exc
        return result

    def current_fetch_v1(self,run_id,claim_id,*,deadline):
        if self.settings.config.operation!='fetch' or any(type(x) is not UUID for x in(run_id,claim_id)):
            raise PermissionError('fixed fetch claim required')
        result=self._call('research_fetch_current_v1',(run_id,claim_id),deadline,write=False)
        if result.get('current') is not True:raise PermissionError('original fetch claim no longer current')
        bound=datetime.fromisoformat(result['valid_until'])
        if not datetime.now(timezone.utc)<bound<=deadline:raise PermissionError('original fetch lease expired or renewed')
        return bound

    def retained_fetch_v1(self,run_id,*,deadline):
        if self.settings.config.operation!='fetch' or type(run_id) is not UUID:
            raise PermissionError('fixed retained fetch identity required')
        result=self._call('research_retained_fetch_v1',(run_id,),deadline,write=False)
        if result['state'] not in ('INFLIGHT','UNKNOWN','observed'):
            raise PermissionError('retained claim state required')
        return result

    def observe_fetch_v1(self,run_id,claim_id,observation:bytes,*,deadline):
        if (self.settings.config.operation!='fetch' or any(type(x) is not UUID for x in(run_id,claim_id))
                or type(observation) is not bytes or not 1<=len(observation)<=4096):
            raise PermissionError('fixed bounded fetch observation required')
        return self._call('research_observe_fetch_v1',(run_id,claim_id,observation),deadline,write=True)

    def latest_reference_v1(self,*,deadline):
        if self.settings.config.operation!='read':raise PermissionError('separate current reference read appointment required')
        result=self._call('research_latest_reference_v1',(),deadline,write=False)
        if result['state'] not in ('available','unavailable'):
            raise PermissionError('closed current reference availability required')
        definition=result['definition'];Source(**definition)
        if hashlib.sha256(canonical_bytes(definition)).hexdigest()!=result['definition_sha256']:
            raise PermissionError('current reference registration changed')
        keys=('run_id','claim_id','original_deadline','receipt_event_id','recorded_at','observation')
        if result['state']=='unavailable' and any(result[k] is not None for k in keys):
            raise PermissionError('unavailable reference cannot disclose retained custody')
        if result['state']=='available' and any(result[k] is None for k in keys):
            raise PermissionError('complete actual reference receipt required')
        return result

    def status_v1(self,*,deadline):
        if self.settings.config.operation!='read':raise PermissionError('separate research metadata appointment required')
        return self._call('research_status_v1',(),deadline,write=False)
