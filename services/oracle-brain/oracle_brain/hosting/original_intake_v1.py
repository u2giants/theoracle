"""Fixed protected original intake; no reading, qualification, role or storage is issued."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import hashlib,json,os,stat
from pydantic import AwareDatetime,Field,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.artifact_storage import FileBlobStore,OriginalObjectRefV1,ReservationOriginalObjectRefV1,_write_private_at
from .runtime import protected_file

HASH=r'^[a-f0-9]{64}$'
MAX_BYTES=25*1024*1024
class ProtectedInputV1(StrictRecord):
    path:str;sha256:str=Field(pattern=HASH)
class OriginalIntakeConfigV1(StrictRecord):
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
    purpose:Literal['original-intake-factory-v1']
    config_sha256:str=Field(pattern=HASH)
    auth_issuer:str;auth_project_id:str;auth_user_id:UUID;employee_id:UUID
    principal_id:UUID;workspace_id:UUID;expected_session_role:str
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH)
    storage_profile_hash:str=Field(pattern=HASH)
    issuer_actor:UUID;reviewer_actor:UUID
    operations:tuple[Literal['create','replace'],...]=Field(min_length=1,max_length=2)
    valid_from:AwareDatetime;original_horizon:AwareDatetime;expires_at:AwareDatetime
    @model_validator(mode='after')
    def independent(self):
        if self.issuer_actor==self.reviewer_actor or self.principal_id in (self.issuer_actor,self.reviewer_actor) or self.valid_from>=self.expires_at or len(set(self.operations))!=len(self.operations):raise ValueError('independent finite appointment required')
        return self
class OriginalIntakeRequestV1(StrictRecord):
    source_id:UUID|None;expected_head:int=Field(ge=0,le=9007199254740991)
    idempotency_key:UUID;filename:str=Field(min_length=1,max_length=255)
    original_sha256:str=Field(pattern=HASH);byte_count:int=Field(ge=1,le=MAX_BYTES)
    @model_validator(mode='after')
    def shape(self):
        if (self.source_id is None)!=(self.expected_head==0) or any(x in self.filename for x in ('/','\\')) or any(ord(x)<32 for x in self.filename):raise ValueError('exact bounded source selector/filename required')
        return self
class IntakeReservationV1(StrictRecord):
    reservation_id:UUID;source_id:UUID;revision:int=Field(ge=1)
    expires_at:AwareDatetime;private_object_key:str

def _pinned(path,seal,limit=65536):
    p=Path(path)
    if not p.is_absolute() or p.resolve()!=p:raise PermissionError('canonical protected input required')
    before=p.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1 or before.st_mode&0o077:raise PermissionError('private owned input required')
    raw=protected_file(p,limit=limit);after=p.lstat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or hashlib.sha256(raw).hexdigest()!=seal:raise PermissionError('protected input changed')
    return raw

def _parse(cls,raw):
    value=cls.model_validate_json(raw)
    if canonical_bytes(value.model_dump(mode='json'))!=raw:raise ValueError('canonical protected record required')
    return value

@dataclass(frozen=True)
class OriginalIntakeSettingsV1:
    config:OriginalIntakeConfigV1
    appointment:OriginalIntakeAppointmentV1
    config_path:Path;config_sha256:str;appointment_path:Path;appointment_sha256:str
    expected_issuer_actor:UUID;expected_reviewer_actor:UUID
    def current(self):
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
    if operation not in settings.appointment.operations:raise PermissionError('intake operation not appointed')
    original=OriginalObjectRefV1(settings.config.workspace_id,reservation.source_id,reservation.revision,request.original_sha256,request.byte_count,'application/pdf',settings.config.storage_profile_hash)
    ref=ReservationOriginalObjectRefV1(original,reservation.reservation_id)
    if reservation.private_object_key!=ref.key:raise PermissionError('SQL reservation key differs')
    return ref,deadline

class RequesterContextV1(StrictRecord):
    principal_id:UUID;workspace_id:UUID;session_role:str
    runtime_hash:str=Field(pattern=HASH);source_registry_hash:str=Field(pattern=HASH)
    checked_at:AwareDatetime;valid_until:AwareDatetime
class ReserveEnvelopeV1(StrictRecord):
    context:RequesterContextV1;reservation:IntakeReservationV1
from .replacement_public_view_v1 import Public
class OriginalIntakeSnapshotV1(Public):
    sourceId:UUID;revision:int=Field(ge=1);originalSha256:str=Field(pattern=HASH)
    byteCount:int=Field(ge=1,le=MAX_BYTES);mediaType:Literal['application/pdf'];filename:str
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
    context:RequesterContextV1;snapshot:OriginalIntakeSnapshotV1
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

class OriginalIntakeFactoryV1:
    """Protected per-principal backend only. Actual SQL, not the settings type, authorizes."""
    def __init__(self,settings):
        if type(settings) is not OriginalIntakeSettingsV1:raise TypeError('fixed intake settings required')
        settings.current();self.settings=settings
    def _call(self,name,arguments,record):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        s=self.settings;c=s.config;s.current()
        raw=_pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf-8')
        _pinned(c.database_ca.path,c.database_ca.sha256,131072)
        target=conninfo_to_dict(raw)
        if set(target)-{'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout'} or target.get('sslmode')!='verify-full' or target.get('sslrootcert')!=c.database_ca.path or target.get('user')!=c.expected_session_role or not target.get('host') or not target.get('dbname'):raise PermissionError('fixed intake SQL target required')
        with psycopg.connect(raw,connect_timeout=5) as conn:
            actual=conn.info
            if not conn.pgconn.ssl_in_use or actual.host!=target['host'] or actual.dbname!=target['dbname'] or actual.user!=target['user'] or actual.port!=int(target.get('port',5432)) or (target.get('hostaddr') and actual.hostaddr!=target['hostaddr']):raise PermissionError('actual intake SQL target differs')
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('statement_timeout','5000',true),set_config('lock_timeout','2000',true)")
                cur.execute("SELECT SESSION_USER::text,CURRENT_USER::text,(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2')")
                if cur.fetchone()!=(c.expected_session_role,c.expected_session_role,c.expected_owner_role):raise PermissionError('actual intake SQL role differs')
                cur.execute("SELECT pg_get_userbyid(proowner),prosecdef FROM pg_proc WHERE oid IN (to_regprocedure('oracle2.reserve_source_revision_v1(integer,jsonb,uuid)'),to_regprocedure('oracle2.finalize_source_revision_v1(uuid,integer,jsonb)'))")
                owners=cur.fetchall()
                if len(owners)!=2 or any(owner!=(c.expected_owner_role,True) for owner in owners):raise PermissionError('actual intake function owner differs')
                s.current()
                if name=='reserve':cur.execute('SELECT oracle2.reserve_source_revision_v1(%s,%s::jsonb,%s)',arguments)
                elif name=='finalize':cur.execute('SELECT oracle2.finalize_source_revision_v1(%s,%s,%s::jsonb)',arguments)
                else:raise PermissionError('fixed intake function required')
                value=record.model_validate_json(json.dumps(cur.fetchone()[0]))
                _context_horizon(s,value.context)
            # Context comparison occurs before transaction commit as well as after.
            conn.commit()
        _context_horizon(s,value.context)
        return value
    def intake_pdf_v1(self,*,source_id,expected_head,idempotency_key,filename,original_sha256,data:bytes):
        from uuid import uuid4
        if type(data) is not bytes:raise TypeError('exact original bytes required')
        q=OriginalIntakeRequestV1(source_id=source_id,expected_head=expected_head,idempotency_key=idempotency_key,filename=filename,original_sha256=original_sha256,byte_count=len(data))
        if hashlib.sha256(data).hexdigest()!=q.original_sha256:raise ValueError('original byte hash differs')
        s=self.settings;s.current();written=None
        intake=dict(source_id=str(q.source_id) if q.source_id else None,filename=q.filename,media_type='application/pdf',byte_count=q.byte_count)
        reserved=self._call('reserve',(q.expected_head,json.dumps(intake),q.idempotency_key),ReserveEnvelopeV1)
        ref,deadline=reservation_original_ref_v1(s,q,reserved.reservation,data)
        deadline=min(deadline,_context_horizon(s,reserved.context))
        try:
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('intake write horizon elapsed')
            # No SQL connection or lock remains open during storage I/O.
            store=FileBlobStore(Path(s.config.storage_root));store._put_original_bytes(ref,data);written=ref
            if store._read_original_bytes(ref)!=data:raise ValueError('private original readback differs')
            observation=dict(schema_version=1,purpose='original-intake-byte-custody-v1',reservation_id=str(ref.reservation_id),source_id=str(ref.original.source_id),workspace_id=str(ref.original.workspace_id),revision=ref.original.revision,private_object_key=ref.key,original_sha256=ref.original_sha256,byte_count=ref.byte_count,storage_profile_hash=ref.original.storage_profile_hash)
            seal=digest(observation)
            _write_private_at(store.root,['intake-observations',str(ref.reservation_id),'custody.json'],canonical_bytes(observation))
            s.current()
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('intake finalization horizon elapsed')
            custody=dict(original_sha256=q.original_sha256,byte_count=q.byte_count,custody_seal_sha256=seal,expected_context=_expected_context(s))
            final=self._call('finalize',(ref.reservation_id,q.expected_head,json.dumps(custody)),FinalizeEnvelopeV1)
            snapshot=final.snapshot
            if snapshot.sourceId!=ref.original.source_id or snapshot.revision!=ref.original.revision or snapshot.originalSha256!=q.original_sha256 or snapshot.byteCount!=q.byte_count or snapshot.filename!=q.filename:raise PermissionError('finalized original identity differs')
            return snapshot
        except BaseException as error:
            if written is not None:
                # Custody fact survives expiry; this private record authorizes no read/delete.
                try:
                    root=Path(s.config.storage_root);info=root.lstat()
                    if root.resolve()!=root or (info.st_dev,info.st_ino,info.st_uid)!=(s.config.storage_device,s.config.storage_inode,s.config.storage_uid) or info.st_mode&0o077:raise PermissionError('orphan record root differs')
                    orphan=dict(schema_version=1,purpose='unadmitted-original-intake-observation-v1',reservation_id=str(ref.reservation_id),private_object_key=ref.key,original_sha256=ref.original_sha256,byte_count=ref.byte_count,failure_class=type(error).__name__,observed_at=datetime.now(timezone.utc).isoformat())
                    _write_private_at(root,['intake-observations',str(ref.reservation_id),str(uuid4())+'.orphan.json'],canonical_bytes(orphan))
                except BaseException:raise OriginalIntakeUnavailable('Intake unaccepted; private orphan recording uncertain') from None
            if getattr(error,'sqlstate',None) in ('40001','23505'):raise OriginalIntakeConflict('Refresh original revision before retrying') from None
            raise OriginalIntakeUnavailable('Intake unaccepted; private custody retained') from None
