"""Fixed protected original intake; no reading, qualification, role or storage is issued."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID,uuid4
import hashlib,json,os,stat
from pydantic import AwareDatetime,Field,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.artifact_storage import FileBlobStore,OriginalObjectRefV1,ReservationOriginalObjectRefV1,_write_private_at
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1,protected_file,_pinned,_parse as _strict_parse

HASH=r'^[a-f0-9]{64}$'
MAX_BYTES=25*1024*1024
class OriginalIntakeConfigV1(StrictRecord):
    schema_version:Literal[1]
    purpose:Literal['original-intake-factory-v1']
    auth_issuer:str;auth_project_id:str;auth_user_id:UUID;employee_id:UUID
    principal_id:UUID;workspace_id:UUID
    expected_session_role:str=Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    expected_owner_role:str=Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH)
    database_url:ProtectedInputV1;database_ca:ProtectedInputV1
    storage_root:str;storage_device:int=Field(ge=0);storage_inode:int=Field(gt=0);storage_uid:int=Field(ge=0)
    storage_profile_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime;expires_at:AwareDatetime
    @model_validator(mode='after')
    def independent(self):
        if self.expected_session_role==self.expected_owner_role:raise ValueError('caller cannot be function owner')
        from urllib.parse import urlsplit
        issuer=urlsplit(self.auth_issuer)
        if issuer.scheme!='https' or not issuer.hostname or issuer.path!='/auth/v1' or issuer.username or issuer.password or issuer.query or issuer.fragment:raise ValueError('fixed issuer required')
        return self
class OriginalIntakeAppointmentV1(StrictRecord):
    schema_version:Literal[1]
    purpose:Literal['original-intake-factory-v1']
    config_sha256:str=Field(pattern=HASH)
    auth_issuer:str;auth_project_id:str;auth_user_id:UUID;employee_id:UUID
    principal_id:UUID;workspace_id:UUID;expected_session_role:str
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH)
    storage_profile_hash:str=Field(pattern=HASH)
    issuer_actor:UUID;reviewer_actor:UUID
    operations:tuple[Literal['create','replace'],...]=Field(min_length=1,max_length=2)
    media_types:tuple[Literal['application/pdf','text/plain'],...]=('application/pdf',)
    valid_from:AwareDatetime;original_horizon:AwareDatetime;expires_at:AwareDatetime
    @model_validator(mode='after')
    def independent(self):
        if self.issuer_actor==self.reviewer_actor or self.principal_id in (self.issuer_actor,self.reviewer_actor) or self.valid_from>=self.expires_at or len(set(self.operations))!=len(self.operations) or not self.media_types or len(set(self.media_types))!=len(self.media_types):raise ValueError('independent finite appointment required')
        return self
class OriginalIntakeRequestV1(StrictRecord):
    source_id:UUID|None;expected_head:int=Field(ge=0,le=9007199254740991)
    idempotency_key:UUID;filename:str=Field(min_length=1,max_length=255)
    original_sha256:str=Field(pattern=HASH);byte_count:int=Field(ge=1,le=MAX_BYTES)
    # Selected only by the two fixed protected factory methods. Keep inherited
    # legacy PDF upload wire bytes unchanged; callers cannot choose text there.
    media_type:Literal['application/pdf','text/plain']=Field(default='application/pdf',exclude=True)
    @model_validator(mode='after')
    def shape(self):
        if (self.source_id is None)!=(self.expected_head==0) or any(x in self.filename for x in ('/','\\')) or any(ord(x)<32 for x in self.filename):raise ValueError('exact bounded source selector/filename required')
        return self
class IntakeReservationV1(StrictRecord):
    reservation_id:UUID;source_id:UUID;revision:int=Field(ge=1)
    expires_at:AwareDatetime;private_object_key:str

def _parse(cls,raw):
    try:return _strict_parse(cls,raw)
    except ValueError:
        # Preserve only retained PDF appointments with the old omitted media pin.
        # Full canonical comparison still rejects duplicate/nonfinite/extra bytes.
        if cls is not OriginalIntakeAppointmentV1:raise
        value=cls.model_validate_json(raw)
        if ('media_types' in json.loads(raw)
                or canonical_bytes(value.model_dump(mode='json',exclude={'media_types'}))!=raw):raise
        return value


@dataclass(frozen=True)
class OriginalIntakeSettingsV1:
    config:OriginalIntakeConfigV1
    appointment:OriginalIntakeAppointmentV1
    config_path:Path;config_sha256:str;appointment_path:Path;appointment_sha256:str
    expected_issuer_actor:UUID;expected_reviewer_actor:UUID
    def current(self):
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1(required=False)
        c=_parse(OriginalIntakeConfigV1,_pinned(self.config_path,self.config_sha256))
        a=_parse(OriginalIntakeAppointmentV1,_pinned(self.appointment_path,self.appointment_sha256))
        if c!=self.config or a!=self.appointment or a.config_sha256!=self.config_sha256 or a.issuer_actor!=self.expected_issuer_actor or a.reviewer_actor!=self.expected_reviewer_actor:raise PermissionError('intake startup changed')
        for key in ('auth_issuer','auth_project_id','auth_user_id','employee_id','principal_id','workspace_id','expected_session_role','runtime_hash','registry_hash','storage_profile_hash','original_horizon'):
            if getattr(c,key)!=getattr(a,key):raise PermissionError('intake appointment differs')
        now=datetime.now(timezone.utc);deadline=min(c.expires_at,c.original_horizon,a.expires_at,a.original_horizon)
        if not a.valid_from<=now<deadline:raise PermissionError('intake appointment expired')
        root=Path(c.storage_root)
        if not root.is_absolute() or root.resolve()!=root:raise PermissionError('canonical provisioned root required')
        info=root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_mode&0o077 or (info.st_dev,info.st_ino,info.st_uid)!=(c.storage_device,c.storage_inode,c.storage_uid) or info.st_uid!=os.getuid():raise PermissionError('appointed storage root differs')
        return deadline

def load_original_intake_settings_v1(config_path,expected_config_sha256,appointment_path,expected_appointment_sha256,expected_issuer_actor,expected_reviewer_actor):
    settings=OriginalIntakeSettingsV1(_parse(OriginalIntakeConfigV1,_pinned(config_path,expected_config_sha256)),_parse(OriginalIntakeAppointmentV1,_pinned(appointment_path,expected_appointment_sha256)),Path(config_path),expected_config_sha256,Path(appointment_path),expected_appointment_sha256,expected_issuer_actor,expected_reviewer_actor)
    settings.current();return settings

def reservation_original_ref_v1(settings:OriginalIntakeSettingsV1,request:OriginalIntakeRequestV1,reservation:IntakeReservationV1,data:bytes):
    """Pure exact reservation binding plus current protected startup checks, no grant."""
    if type(settings) is not OriginalIntakeSettingsV1 or type(request) is not OriginalIntakeRequestV1 or type(reservation) is not IntakeReservationV1:raise TypeError('exact intake records required')
    deadline=min(settings.current(),reservation.expires_at)
    if datetime.now(timezone.utc)>=deadline or (request.source_id is not None and reservation.source_id!=request.source_id) or reservation.revision!=request.expected_head+1:raise PermissionError('reservation identity/horizon differs')
    if type(data) is not bytes or len(data)!=request.byte_count or hashlib.sha256(data).hexdigest()!=request.original_sha256:raise ValueError('original bytes differ')
    operation='create' if request.source_id is None else 'replace'
    if request.media_type not in settings.appointment.media_types:raise PermissionError('original media not independently appointed')
    if operation not in settings.appointment.operations:raise PermissionError('intake operation not appointed')
    original=OriginalObjectRefV1(settings.config.workspace_id,reservation.source_id,reservation.revision,request.original_sha256,request.byte_count,request.media_type,settings.config.storage_profile_hash)
    ref=ReservationOriginalObjectRefV1(original,reservation.reservation_id)
    if reservation.private_object_key!=ref.key:raise PermissionError('SQL reservation key differs')
    return ref,deadline

class RequesterContextV1(StrictRecord):
    principal_id:UUID;workspace_id:UUID;session_role:str
    runtime_hash:str=Field(pattern=HASH);source_registry_hash:str=Field(pattern=HASH)
    checked_at:AwareDatetime;valid_until:AwareDatetime
class ReserveEnvelopeV1(StrictRecord):
    schema_version:Literal[1]
    context:RequesterContextV1;reservation:IntakeReservationV1
from .replacement_public_view_v1 import Public
class OriginalIntakeSnapshotV1(Public):
    sourceId:UUID;revision:int=Field(ge=1);originalSha256:str=Field(pattern=HASH)
    byteCount:int=Field(ge=1,le=MAX_BYTES);mediaType:Literal['application/pdf','text/plain'];filename:str
    state:Literal['awaiting_original_reading','reading_failed','qualified']
    qualifiedSourceRef:object
    @model_validator(mode='after')
    def qualified(self):
        from .replacement_public_view_v1 import Source
        ref=self.qualifiedSourceRef
        if (self.state=='qualified')!=(ref is not None):raise ValueError('qualification state differs')
        if ref is not None:
            parsed=Source.model_validate(ref)
            if parsed.sourceId!=str(self.sourceId) or parsed.revision!=self.revision or parsed.originalSha256!=self.originalSha256:raise ValueError('qualified original differs')
            object.__setattr__(self,'qualifiedSourceRef',parsed.model_dump(mode='json'))
        return self
class FinalizeEnvelopeV1(StrictRecord):
    schema_version:Literal[1]
    context:RequesterContextV1;snapshot:OriginalIntakeSnapshotV1
class ReconcileIntakeEnvelopeV1(StrictRecord):
    schema_version:Literal[1]
    context:RequesterContextV1
    status:Literal['pending','expired','finalized']
    reservation_expires_at:AwareDatetime
    snapshot:OriginalIntakeSnapshotV1|None
    @model_validator(mode='after')
    def exact_observation(self):
        if (self.status=='finalized')!=(self.snapshot is not None):raise ValueError('actual intake reconciliation status differs')
        return self
class OriginalIntakeUnavailable(PermissionError):pass
class OriginalIntakeConflict(ValueError):pass

def _expected_context(s):
    c=s.config
    return dict(principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),session_role=c.expected_session_role,runtime_hash=c.runtime_hash,source_registry_hash=c.registry_hash)

def _context_horizon(s,context):
    if type(context) is not RequesterContextV1:raise TypeError('exact current requester context required')
    expected=_expected_context(s)
    for key,value in expected.items():
        if str(getattr(context,key))!=value:raise PermissionError('current SQL requester differs')
    now=datetime.now(timezone.utc)
    if not context.checked_at<=now<context.valid_until or context.checked_at>=context.valid_until:raise PermissionError('SQL current context elapsed')
    return min(s.current(),context.valid_until)

def _intake_current_deadline(settings,deadline,context=None):
    if type(deadline) is not datetime or deadline.tzinfo is None or deadline.utcoffset() is None:
        raise PermissionError('exact aware original intake deadline required')
    bound=settings.current() if context is None else _context_horizon(settings,context)
    now=datetime.now(timezone.utc)
    if not now<deadline<=settings.config.original_horizon or now>=min(bound,deadline):
        raise PermissionError('original intake deadline elapsed or excessive')
    remaining=(min(bound,deadline)-now).total_seconds()
    from ._protected_control_listener_v1 import request_remaining_v1
    original=request_remaining_v1(required=False)
    return min(remaining,original) if original is not None else remaining


class OriginalIntakeFactoryV1:
    """Protected per-principal backend only. Actual SQL, not the settings type, authorizes."""
    def __init__(self,settings):
        if type(settings) is not OriginalIntakeSettingsV1:raise TypeError('fixed intake settings required')
        settings.current();self.settings=settings
    def _call(self,name,arguments,record,*,caller_deadline=None):
        from ._protected_control_listener_v1 import request_remaining_v1
        if request_remaining_v1(required=False) is not None:
            return self._call_protected_v1(name,arguments,record,caller_deadline=caller_deadline)
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        s=self.settings;c=s.config
        deadline=s.current() if caller_deadline is None else caller_deadline
        remaining=_intake_current_deadline(s,deadline)
        if remaining<1:raise PermissionError('original intake connection window elapsed')
        connect_seconds=min(5,int(remaining))
        raw=_pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf-8')
        _pinned(c.database_ca.path,c.database_ca.sha256,131072)
        target=conninfo_to_dict(raw)
        if set(target)-{'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout'} or target.get('sslmode')!='verify-full' or target.get('sslrootcert')!=c.database_ca.path or target.get('user')!=c.expected_session_role or not target.get('host') or not target.get('dbname'):raise PermissionError('fixed intake SQL target required')
        remaining=_intake_current_deadline(s,deadline)
        if remaining<1:raise PermissionError('original intake connection window elapsed')
        connect_seconds=min(5,int(remaining))
        milliseconds=int(remaining*1000)
        with psycopg.connect(raw,connect_timeout=connect_seconds,tcp_user_timeout=milliseconds,
                options=f'-c statement_timeout={min(5000,milliseconds)} -c lock_timeout={min(2000,milliseconds)}') as conn:
            actual=conn.info
            if not conn.pgconn.ssl_in_use or actual.host!=target['host'] or actual.dbname!=target['dbname'] or actual.user!=target['user'] or actual.port!=int(target.get('port',5432)) or (target.get('hostaddr') and actual.hostaddr!=target['hostaddr']):raise PermissionError('actual intake SQL target differs')
            _intake_current_deadline(s,deadline)
            with conn.cursor() as cur:
                def limits():
                    milliseconds=int(_intake_current_deadline(s,deadline)*1000)
                    if milliseconds<1:raise PermissionError('original intake statement window elapsed')
                    cur.execute("SELECT set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
                        (str(min(5000,milliseconds)),str(min(2000,milliseconds))))
                limits()
                cur.execute("SELECT SESSION_USER::text,CURRENT_USER::text,(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2')")
                if cur.fetchone()!=(c.expected_session_role,c.expected_session_role,c.expected_owner_role):raise PermissionError('actual intake SQL role differs')
                cur.execute("SELECT pg_get_userbyid(proowner),prosecdef FROM pg_proc WHERE oid IN (to_regprocedure('oracle2.reserve_source_revision_v1(integer,jsonb,uuid)'),to_regprocedure('oracle2.finalize_source_revision_v1(uuid,integer,jsonb)'))")
                owners=cur.fetchall()
                if len(owners)!=2 or any(owner!=(c.expected_owner_role,True) for owner in owners):raise PermissionError('actual intake function owner differs')
                limits()
                if name=='reserve':cur.execute('SELECT oracle2.reserve_source_revision_v1(%s,%s::jsonb,%s)',arguments)
                elif name=='finalize':cur.execute('SELECT oracle2.finalize_source_revision_v1(%s,%s,%s::jsonb)',arguments)
                else:raise PermissionError('fixed intake function required')
                value=record.model_validate_json(json.dumps(cur.fetchone()[0]))
                _intake_current_deadline(s,deadline,value.context)
            # No subsequent commit after the original caller horizon. A late
            # commit/close is uncertain, never a successful upload or retry.
            _intake_current_deadline(s,deadline,value.context)
            conn.commit()
        _intake_current_deadline(s,deadline,value.context)
        return value
    def _call_protected_v1(self,name,arguments,record,*,caller_deadline=None):
        # One shared original socket/SQL/COMMIT/CLOSE boundary. This method
        # preserves the intake owner's actual identity and catalog checks.
        from psycopg.conninfo import conninfo_to_dict
        from ..operating_model.protected_sql_connection_v1 import _connection_v1
        from ..operating_model.request_deadline_v1 import sql_execute_v1
        s=self.settings;c=s.config
        deadline=s.current() if caller_deadline is None else caller_deadline
        _intake_current_deadline(s,deadline)
        raw=_pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf-8')
        _pinned(c.database_ca.path,c.database_ca.sha256,131072)
        target=conninfo_to_dict(raw)
        if target.get('sslrootcert')!=c.database_ca.path or target.get('user')!=c.expected_session_role:
            raise PermissionError('fixed intake SQL target differs')
        with _connection_v1(raw,deadline) as conn:
            actual=conn.info
            if (not conn.pgconn.ssl_in_use or actual.host!=target['host'] or actual.dbname!=target['dbname']
                    or actual.user!=target['user'] or actual.port!=int(target['port'])
                    or target.get('hostaddr') and actual.hostaddr!=target['hostaddr']):
                raise PermissionError('actual intake SQL target differs')
            execute=lambda statement,args=None:sql_execute_v1(conn,deadline,statement,args)
            row=execute("SELECT SESSION_USER::text,CURRENT_USER::text,(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2')").fetchone()
            if row!=(c.expected_session_role,c.expected_session_role,c.expected_owner_role):raise PermissionError('actual intake SQL role differs')
            names=['oracle2.reserve_source_revision_v1(integer,jsonb,uuid)','oracle2.finalize_source_revision_v1(uuid,integer,jsonb)']
            if name=='reconcile':names.append('oracle2.reconcile_source_intake_v1(uuid)')
            owners=execute('SELECT pg_get_userbyid(proowner),prosecdef FROM pg_proc WHERE oid=ANY(ARRAY(SELECT to_regprocedure(x) FROM unnest(%s::text[]) x))',(names,)).fetchall()
            if len(owners)!=len(names) or any(owner!=(c.expected_owner_role,True) for owner in owners):raise PermissionError('actual intake function owner differs')
            if name=='reserve':cursor=execute('SELECT oracle2.reserve_source_revision_v1(%s,%s::jsonb,%s)',arguments)
            elif name=='finalize':cursor=execute('SELECT oracle2.finalize_source_revision_v1(%s,%s,%s::jsonb)',arguments)
            elif name=='reconcile':cursor=execute('SELECT oracle2.reconcile_source_intake_v1(%s)',arguments)
            else:raise PermissionError('fixed intake function required')
            value=record.model_validate_json(json.dumps(cursor.fetchone()[0]))
            _intake_current_deadline(s,deadline,value.context)
        _intake_current_deadline(s,deadline,value.context)
        return value

    def reconcile_intake_v1(self,idempotency_key,*,caller_deadline):
        # Current own-role read only; it never replays reserve/finalize/bytes.
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1(required=True)
        if type(idempotency_key) is not UUID:raise TypeError('exact own intake idempotency UUID required')
        return self._call('reconcile',(idempotency_key,),ReconcileIntakeEnvelopeV1,caller_deadline=caller_deadline)

    def intake_pdf_v1(self,**kwargs):
        return self._intake_v1(media_type='application/pdf',**kwargs)
    def intake_text_v1(self,**kwargs):
        data=kwargs.get('data')
        if type(data) is not bytes or not 1<=len(data)<=1024*1024:raise ValueError('bounded exact UTF8 original required')
        text=data.decode('utf-8',errors='strict')
        if not text.strip() or '\x00' in text or text.encode('utf-8')!=data:raise ValueError('exact nonempty UTF8 original required')
        return self._intake_v1(media_type='text/plain',**kwargs)
    def _intake_v1(self,*,source_id,expected_head,idempotency_key,filename,original_sha256,data:bytes,media_type,caller_deadline=None):
        from uuid import uuid4
        if type(data) is not bytes:raise TypeError('exact original bytes required')
        q=OriginalIntakeRequestV1(source_id=source_id,expected_head=expected_head,idempotency_key=idempotency_key,filename=filename,original_sha256=original_sha256,byte_count=len(data),media_type=media_type)
        if hashlib.sha256(data).hexdigest()!=q.original_sha256:raise ValueError('original byte hash differs')
        s=self.settings;bound=s.current();written=None
        if q.media_type not in s.appointment.media_types:raise PermissionError('original media not independently appointed')
        original_deadline=bound if caller_deadline is None else caller_deadline
        _intake_current_deadline(s,original_deadline)
        if original_deadline>bound:raise PermissionError('caller intake deadline exceeds existing appointment')
        reserved=self._reserve_original_v1(q, caller_deadline=original_deadline)
        return self._finalize_reserved_original_v1(q, reserved, data, caller_deadline=original_deadline)

    def reserve_pdf_v1(self,q,*,caller_deadline):
        if type(q) is not OriginalIntakeRequestV1 or q.media_type!='application/pdf':raise TypeError('exact PDF intake request required')
        return self._reserve_original_v1(q,caller_deadline=caller_deadline)
    def _reserve_original_v1(self,q,*,caller_deadline):
        """Fresh actual SQL context for the immutable original reservation."""
        if type(q) is not OriginalIntakeRequestV1:raise TypeError('exact intake request required')
        s=self.settings;original_deadline=caller_deadline
        if q.media_type not in s.appointment.media_types:raise PermissionError('original media not independently appointed')
        _intake_current_deadline(s,original_deadline)
        if original_deadline>s.current():raise PermissionError('caller intake deadline exceeds existing appointment')
        intake=dict(source_id=str(q.source_id) if q.source_id else None,filename=q.filename,media_type=q.media_type,byte_count=q.byte_count,caller_deadline=original_deadline.isoformat())
        return self._call('reserve',(q.expected_head,json.dumps(intake),q.idempotency_key),ReserveEnvelopeV1,caller_deadline=original_deadline)

    def finalize_reserved_pdf_v1(self,q,reserved,data,*,caller_deadline):
        if type(q) is not OriginalIntakeRequestV1 or q.media_type!='application/pdf':raise TypeError('exact PDF intake request required')
        return self._finalize_reserved_original_v1(q,reserved,data,caller_deadline=caller_deadline)
    def _finalize_reserved_original_v1(self,q,reserved,data,*,caller_deadline):
        """Reuse existing custody/finalizer; never reserves another source."""
        if type(q) is not OriginalIntakeRequestV1 or type(reserved) is not ReserveEnvelopeV1 or type(data) is not bytes:raise TypeError('exact reserved original required')
        s=self.settings;original_deadline=caller_deadline;written=None
        _intake_current_deadline(s,original_deadline,reserved.context)
        ref,deadline=reservation_original_ref_v1(s,q,reserved.reservation,data)
        deadline=min(original_deadline,deadline,_context_horizon(s,reserved.context))
        try:
            _intake_current_deadline(s,original_deadline,reserved.context)
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('intake write horizon elapsed')
            # No SQL connection or lock remains open during storage I/O.
            store=FileBlobStore._from_provisioned_original_root(Path(s.config.storage_root),(s.config.storage_device,s.config.storage_inode,s.config.storage_uid));store._put_original_bytes(ref,data);written=ref
            _intake_current_deadline(s,original_deadline,reserved.context)
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('intake write completed after original horizon')
            if store._read_original_bytes(ref)!=data:raise ValueError('private original readback differs')
            _intake_current_deadline(s,original_deadline,reserved.context)
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('intake readback horizon elapsed')
            observation=dict(schema_version=1,purpose='original-intake-byte-custody-v1',reservation_id=str(ref.reservation_id),source_id=str(ref.original.source_id),workspace_id=str(ref.original.workspace_id),revision=ref.original.revision,private_object_key=ref.key,original_sha256=ref.original_sha256,byte_count=ref.byte_count,storage_profile_hash=ref.original.storage_profile_hash)
            seal=digest(observation)
            _intake_current_deadline(s,original_deadline,reserved.context)
            _write_private_at(store.root,['intake-observations',str(ref.reservation_id),'custody.json'],canonical_bytes(observation),expected_root=(s.config.storage_device,s.config.storage_inode,s.config.storage_uid))
            _intake_current_deadline(s,original_deadline,reserved.context)
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('intake finalization horizon elapsed')
            custody=dict(original_sha256=q.original_sha256,byte_count=q.byte_count,custody_seal_sha256=seal,expected_context=_expected_context(s),caller_deadline=original_deadline.isoformat())
            final=self._call('finalize',(ref.reservation_id,q.expected_head,json.dumps(custody)),FinalizeEnvelopeV1,caller_deadline=original_deadline)
            _intake_current_deadline(s,original_deadline,final.context)
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('intake original finalization deadline elapsed')
            snapshot=final.snapshot
            if snapshot.sourceId!=ref.original.source_id or snapshot.revision!=ref.original.revision or snapshot.originalSha256!=q.original_sha256 or snapshot.byteCount!=q.byte_count or snapshot.filename!=q.filename or snapshot.mediaType!=q.media_type:raise PermissionError('finalized original identity differs')
            return snapshot
        except BaseException as error:
            if written is not None:
                # Custody fact survives expiry; this private record authorizes no read/delete.
                try:
                    root=Path(s.config.storage_root);info=root.lstat()
                    if root.resolve()!=root or (info.st_dev,info.st_ino,info.st_uid)!=(s.config.storage_device,s.config.storage_inode,s.config.storage_uid) or info.st_mode&0o077:raise PermissionError('orphan record root differs')
                    orphan=dict(schema_version=1,purpose='unadmitted-original-intake-observation-v1',reservation_id=str(ref.reservation_id),private_object_key=ref.key,original_sha256=ref.original_sha256,byte_count=ref.byte_count,failure_class=type(error).__name__,observed_at=datetime.now(timezone.utc).isoformat())
                    _write_private_at(root,['intake-observations',str(ref.reservation_id),str(uuid4())+'.orphan.json'],canonical_bytes(orphan),expected_root=(s.config.storage_device,s.config.storage_inode,s.config.storage_uid))
                except BaseException:raise OriginalIntakeUnavailable('Intake unaccepted; private orphan recording uncertain') from None
            if getattr(error,'sqlstate',None) in ('40001','23505'):raise OriginalIntakeConflict('Refresh original revision before retrying') from None
            raise OriginalIntakeUnavailable('Intake unaccepted; private custody retained') from None
