"""Bounded immutable upload byte/uncertainty custody. SQL owns source admission.

No retry dispatcher, grant, cleanup or resumed writes across process incarnations.
"""
import base64,fcntl,hashlib,json,os,re,stat,time
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID,uuid4
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.artifact_storage import _write_private_at,_parent_fd,_read_private_at
from .original_intake_v1 import OriginalIntakeRequestV1,ReserveEnvelopeV1,OriginalIntakeSnapshotV1,_context_horizon
from .original_upload_settings_v1 import check_upload_spool_v1

CHUNK_BYTES=2*1024*1024
MAX_REQUEST=2850000
HASH=r'^[a-f0-9]{64}$'
now=lambda:datetime.now(timezone.utc)

class UploadVersionV1(StrictRecord):
    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact upload version required')
        return value

class UploadBeginV1(UploadVersionV1,OriginalIntakeRequestV1):
    operation:Literal['begin']
    caller_deadline:AwareDatetime

class UploadActionV1(UploadVersionV1):
    operation:Literal['status','cancel','finalize','chunk']
    reservation_id:UUID;source_id:UUID
    revision:int=Field(strict=True,ge=1,le=9007199254740991)
    begin_sha256:str=Field(pattern=HASH)
    caller_deadline:AwareDatetime

class UploadChunkV1(UploadActionV1):
    operation:Literal['chunk']
    chunk_index:int=Field(strict=True,ge=0,le=12)
    offset:int=Field(strict=True,ge=0,le=24*1024*1024)
    chunk_sha256:str=Field(pattern=HASH)
    data_base64:str=Field(min_length=4,max_length=2796204)
    def decoded(self):
        data=base64.b64decode(self.data_base64,validate=True)
        if not 1<=len(data)<=CHUNK_BYTES or base64.b64encode(data).decode()!=self.data_base64 or hashlib.sha256(data).hexdigest()!=self.chunk_sha256:raise ValueError('canonical chunk bytes differ')
        return data

class UploadResponseV1(UploadVersionV1):
    state:Literal['reserved','receiving','finalizing','committed','cancelled','expired','UNKNOWN']
    reservation_id:UUID;source_id:UUID;revision:int=Field(strict=True,ge=1,le=9007199254740991)
    begin_sha256:str=Field(pattern=HASH)
    received_bytes:int=Field(strict=True,ge=0,le=25*1024*1024)
    next_chunk_index:int=Field(strict=True,ge=0,le=13)
    valid_until:AwareDatetime
    qualification:Literal[False]
    remote_stop_proven:Literal[False]
    observation_only:Literal[True]
    source_snapshot:OriginalIntakeSnapshotV1|None
    @field_validator('qualification','remote_stop_proven','observation_only',mode='before')
    @classmethod
    def literal_flags(cls,value):
        if type(value) is not bool:raise ValueError('literal upload observation flags required')
        return value
    @model_validator(mode='after')
    def snapshot(self):
        if self.next_chunk_index!=(self.received_bytes+CHUNK_BYTES-1)//CHUNK_BYTES or self.state=='reserved' and self.received_bytes!=0 or self.state in ('receiving','committed') and self.received_bytes==0:raise ValueError('exact committed chunk accounting required')
        s=self.source_snapshot
        if s is not None and (self.state!='committed' or s.state!='awaiting_original_reading' or s.qualifiedSourceRef is not None or s.sourceId!=self.source_id or s.revision!=self.revision):raise ValueError('only exact freshly finalized unqualified snapshot')
        return self


def parse_upload_request_v1(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_REQUEST:raise ValueError('bounded upload wire required')
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('duplicate upload field')
            d[k]=v
        return d
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('finite upload request required')))
    if type(value) is not dict or canonical_bytes(value)!=raw:raise ValueError('canonical upload wire required')
    cls=UploadBeginV1 if value.get('operation')=='begin' else UploadChunkV1 if value.get('operation')=='chunk' else UploadActionV1
    result=cls.model_validate_json(raw)
    # Parse/model/render equality closes UUID, datetime and integer normalization.
    if canonical_bytes(result.model_dump(mode='json'))!=raw:raise ValueError('exact rendered upload wire required')
    if type(result) is UploadActionV1 and result.operation=='chunk':raise ValueError('full chunk required')
    return result


class OriginalUploadStoreV1:
    def __init__(self,settings,factory):
        from .original_intake_v1 import OriginalIntakeFactoryV1
        if type(factory) is not OriginalIntakeFactoryV1:raise TypeError('existing actual intake factory required')
        self.settings=settings;self.factory=factory;self.root=check_upload_spool_v1(settings)
        self.windows={}
        self.instance=uuid4() # Descriptive process incarnation, never authority.
        p=settings.profile;self.identity=(p.spool_device,p.spool_inode,p.spool_uid)
    def _write(self,parts,value):
        check_upload_spool_v1(self.settings)
        _write_private_at(self.root,parts,canonical_bytes(value),expected_root=self.identity)
    def _read_bytes(self,parts,limit):
        fd=_parent_fd(self.root,parts[:-1],create=False,strict=True,expected_root=self.identity)
        try:return _read_private_at(fd,parts[-1],limit,strict=True)
        finally:os.close(fd)
    def _read(self,parts):
        raw=self._read_bytes(parts,MAX_REQUEST);v=json.loads(raw)
        if canonical_bytes(v)!=raw:raise PermissionError('upload journal changed')
        return v
    @contextmanager
    def _locked(self):
        root=check_upload_spool_v1(self.settings);p=root/'upload.lock'
        before=p.lstat();fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW)
        try:
            i=os.fstat(fd)
            if (i.st_dev,i.st_ino)!=(before.st_dev,before.st_ino) or not stat.S_ISREG(i.st_mode) or i.st_mode&0o077 or i.st_nlink!=1:raise PermissionError('upload lock changed')
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            check_upload_spool_v1(self.settings)
            if (p.lstat().st_dev,p.lstat().st_ino)!=(i.st_dev,i.st_ino):raise PermissionError('upload lock replaced')
            yield
        finally:os.close(fd)
    def _sessions(self):
        parent=self.root/'uploads'
        if not parent.exists():return []
        i=parent.lstat()
        if not stat.S_ISDIR(i.st_mode) or i.st_mode&0o077 or i.st_uid!=os.getuid() or parent.resolve()!=parent:raise PermissionError('upload journal directory differs')
        entries=list(parent.iterdir())
        if len(entries)>64 or any(not re.fullmatch(r'[a-f0-9-]{36}',x.name) or str(UUID(x.name))!=x.name or not x.is_dir() or x.is_symlink() for x in entries):raise PermissionError('bounded upload inventory required')
        return entries
    def _state(self,path):
        parts=['uploads',path.name];names={x.name for x in path.iterdir()}
        allowed={'begin-intent.json','begin.json','closed.json','finalize-intent.json','finalize.json'}|{f'lease-{i}.json' for i in range(64)}|{f'chunk-{i}{suffix}' for i in range(13) for suffix in ('.bin','-intent.json','.json')}
        if not names<=allowed or 'begin-intent.json' not in names:raise PermissionError('foreign upload journal population')
        intent=self._read(parts+['begin-intent.json'])
        if set(intent)!={'begin'}:raise PermissionError('closed upload begin intent required')
        begin=parse_upload_request_v1(canonical_bytes(intent['begin']))
        if type(begin) is not UploadBeginV1 or path.name!=str(begin.idempotency_key):raise PermissionError('upload begin identity differs')
        if 'begin.json' not in names:return dict(parts=parts,names=names,begin=begin,state='UNKNOWN',count=0,size=0,reserved=None)
        receipt=self._read(parts+['begin.json'])
        if set(receipt)!={'begin_sha256','reserved','instance','valid_until'} or receipt['begin_sha256']!=digest(begin.model_dump(mode='json')):raise PermissionError('upload begin receipt differs')
        reserved=ReserveEnvelopeV1.model_validate_json(json.dumps(receipt['reserved']));instance=UUID(receipt['instance'])
        if canonical_bytes(reserved.model_dump(mode='json'))!=canonical_bytes(receipt['reserved']) or str(instance)!=receipt['instance']:raise PermissionError('canonical reservation receipt required')
        end=datetime.fromisoformat(receipt['valid_until'])
        if end>min(begin.caller_deadline,reserved.reservation.expires_at) or end.tzinfo is None:raise PermissionError('upload lease differs')
        end=self._lease(parts,end,names)
        count=0;size=0;pending=False
        for i in range(13):
            intent=f'chunk-{i}-intent.json';commit=f'chunk-{i}.json';data=f'chunk-{i}.bin'
            if commit in names:
                if pending or i!=count or intent not in names or data not in names:raise PermissionError('upload chunk population differs')
                descriptor=self._read(parts+[intent]);observed=self._read(parts+[commit])
                expected_size=min(CHUNK_BYTES,begin.byte_count-i*CHUNK_BYTES)
                if set(descriptor)!={'request_sha256','chunk_sha256','byte_count','chunk_index'} or descriptor!=observed or type(descriptor['chunk_index']) is not int or type(descriptor['byte_count']) is not int or descriptor['chunk_index']!=i or descriptor['byte_count']!=expected_size or not re.fullmatch(HASH,descriptor['request_sha256']) or not re.fullmatch(HASH,descriptor['chunk_sha256']):raise PermissionError('chunk receipt differs')
                raw=self._read_bytes(parts+[data],CHUNK_BYTES)
                if len(raw)!=expected_size or hashlib.sha256(raw).hexdigest()!=descriptor['chunk_sha256']:raise PermissionError('committed chunk bytes differ')
                count+=1;size+=len(raw)
            elif intent in names or data in names:pending=True
            elif any(f'chunk-{j}{x}' in names for j in range(i+1,13) for x in ('.json','-intent.json','.bin')):raise PermissionError('omitted chunk identity')
        state='reserved' if count==0 else 'receiving'
        if 'finalize.json' in names:
            final=self._read(parts+['finalize.json']);intent=self._read(parts+['finalize-intent.json'])
            if set(final)!={'request_sha256','snapshot'} or intent!={'request_sha256':final['request_sha256']} or size!=begin.byte_count or pending:raise PermissionError('finalize population differs')
            snapshot=OriginalIntakeSnapshotV1.model_validate_json(json.dumps(final['snapshot']))
            if (snapshot.sourceId,snapshot.revision,snapshot.originalSha256,snapshot.byteCount,snapshot.filename,snapshot.state,snapshot.qualifiedSourceRef)!=(reserved.reservation.source_id,reserved.reservation.revision,begin.original_sha256,begin.byte_count,begin.filename,'awaiting_original_reading',None):raise PermissionError('finalized snapshot differs')
            state='committed'
        elif 'finalize-intent.json' in names:pending=True
        if 'closed.json' in names:
            closed=self._read(parts+['closed.json'])
            if set(closed)!={'state'} or closed['state'] not in ('UNKNOWN','cancelled','expired'):raise PermissionError('invalid upload close')
            if state=='committed':raise PermissionError('competing upload terminal states')
            state=closed['state']
        elif state!='committed' and (pending or instance!=self.instance):
            self._write(parts+['closed.json'],dict(state='UNKNOWN'));state='UNKNOWN'
        elif state!='committed' and now()>=end:
            self._write(parts+['closed.json'],dict(state='expired'));state='expired'
        return dict(parts=parts,names=names,begin=begin,reserved=reserved,end=end,state=state,count=count,size=size)
    def _lease(self,parts,end,names=None):
        names=names if names is not None else {x.name for x in self.root.joinpath(*parts).iterdir()}
        leases=sorted(int(n[6:-5]) for n in names if re.fullmatch(r'lease-[0-9]+\.json',n))
        if leases!=list(range(len(leases))) or len(leases)>64:raise PermissionError('lease population differs')
        for i in leases:
            item=self._read(parts+[f'lease-{i}.json'])
            if set(item)!={'valid_until'}:raise PermissionError('lease fields differ')
            value=datetime.fromisoformat(item['valid_until'])
            if value.tzinfo is None or value>=end:raise PermissionError('upload lease renewed')
            end=value
        return end
    def _q(self,begin):
        return OriginalIntakeRequestV1.model_validate_json(canonical_bytes({k:v for k,v in begin.model_dump(mode='json').items() if k not in ('operation','caller_deadline')}))
    def _live(self,begin):
        end=self.windows.get(str(begin.idempotency_key))
        if now()>=begin.caller_deadline or end is not None and time.monotonic()>=end:raise PermissionError('original monotonic upload lease elapsed')
    def _fresh(self,state,peer_until):
        b=state['begin'];self._live(b);fresh=self.factory.reserve_pdf_v1(self._q(b),caller_deadline=b.caller_deadline)
        if state['reserved'] is not None and fresh.reservation!=state['reserved'].reservation:raise PermissionError('actual reserved source differs')
        end=min(b.caller_deadline,state.get('end',b.caller_deadline),fresh.reservation.expires_at,_context_horizon(self.factory.settings,fresh.context),self.settings.current(),peer_until)
        self._live(b)
        if now()>=end:raise PermissionError('upload original lease expired')
        key=str(b.idempotency_key)
        if key in self.windows:self.windows[key]=min(self.windows[key],time.monotonic()+(end-now()).total_seconds())
        current_end=self._lease(state['parts'],datetime.fromisoformat(self._read(state['parts']+['begin.json'])['valid_until'])) if state.get('parts') else end
        end=min(end,current_end)
        if state.get('parts') and end<current_end:
            names={x.name for x in self.root.joinpath(*state['parts']).iterdir()};index=sum(bool(re.fullmatch(r'lease-[0-9]+\.json',n)) for n in names)
            if index>=64:raise PermissionError('bounded lease journal exhausted')
            self._write(state['parts']+[f'lease-{index}.json'],dict(valid_until=end.isoformat()))
        return fresh,end
    def _response(self,state,end,snapshot=None):
        r=state['reserved'].reservation
        end=min(end,self._lease(state['parts'],datetime.fromisoformat(self._read(state['parts']+['begin.json'])['valid_until'])))
        return UploadResponseV1(schema_version=1,state=state['state'],reservation_id=r.reservation_id,source_id=r.source_id,revision=r.revision,begin_sha256=digest(state['begin'].model_dump(mode='json')),received_bytes=state['size'],next_chunk_index=state['count'],valid_until=end,qualification=False,remote_stop_proven=False,observation_only=True,source_snapshot=snapshot)
    def apply(self,request,*,peer_until):
        if type(request) not in (UploadBeginV1,UploadChunkV1,UploadActionV1):raise TypeError('closed upload request required')
        with self._locked():
            sessions=[self._state(p) for p in self._sessions()]
            if type(request) is UploadBeginV1:
                matching=[s for s in sessions if s['begin'].idempotency_key==request.idempotency_key]
                if matching:
                    state=matching[0]
                    if state['begin']!=request or state['reserved'] is None:raise PermissionError('begin collision or unknown reservation')
                    _,end=self._fresh(state,peer_until);return self._response(state,end)
                if len(sessions)>=64 or any(s['state'] not in ('committed','cancelled','expired') for s in sessions):raise PermissionError('one active or unresolved upload required')
                if not now()<request.caller_deadline<=now()+timedelta(seconds=30):raise PermissionError('finite original upload window required')
                self.windows[str(request.idempotency_key)]=time.monotonic()+(request.caller_deadline-now()).total_seconds()
                parts=['uploads',str(request.idempotency_key)]
                self._write(parts+['begin-intent.json'],{'begin':request.model_dump(mode='json')})
                fresh,end=self._fresh(dict(begin=request,reserved=None),peer_until)
                self._write(parts+['begin.json'],dict(begin_sha256=digest(request.model_dump(mode='json')),reserved=fresh.model_dump(mode='json'),instance=str(self.instance),valid_until=end.isoformat()))
                return self._response(self._state(self.root.joinpath(*parts)),end)
            matches=[s for s in sessions if s['reserved'] is not None and s['reserved'].reservation.reservation_id==request.reservation_id]
            if len(matches)!=1:raise PermissionError('exact reservation required')
            state=matches[0];b=state['begin'];r=state['reserved'].reservation
            if (request.source_id,request.revision,request.begin_sha256,request.caller_deadline)!=(r.source_id,r.revision,digest(b.model_dump(mode='json')),b.caller_deadline):raise PermissionError('upload action scope differs')
            fresh,end=self._fresh(state,peer_until)
            if request.operation=='status':return self._response(state,end)
            if type(request) is UploadChunkV1:
                data=request.decoded();i=request.chunk_index
                if request.offset!=i*CHUNK_BYTES or len(data)!=min(CHUNK_BYTES,b.byte_count-i*CHUNK_BYTES):raise ValueError('deterministic original chunk differs')
                descriptor=dict(request_sha256=digest(request.model_dump(mode='json')),chunk_sha256=request.chunk_sha256,byte_count=len(data),chunk_index=i)
                if i<state['count']:
                    if self._read(state['parts']+[f'chunk-{i}.json'])!=descriptor:raise PermissionError('conflicting repeated chunk')
                    return self._response(state,end)
                if state['state'] not in ('reserved','receiving') or i!=state['count']:raise PermissionError('closed or out-of-order upload')
                self._write(state['parts']+[f'chunk-{i}-intent.json'],descriptor)
                self._live(b)
                _write_private_at(self.root,state['parts']+[f'chunk-{i}.bin'],data,expected_root=self.identity)
                if now()>=end:raise PermissionError('chunk wrote after original lease')
                self._fresh(state,peer_until)
                self._write(state['parts']+[f'chunk-{i}.json'],descriptor)
                return self._response(self._state(self.root.joinpath(*state['parts'])),end)
            if state['state'] not in ('reserved','receiving'):raise PermissionError('upload already closed')
            if request.operation=='cancel':
                self._write(state['parts']+['closed.json'],dict(state='cancelled'));return self._response({**state,'state':'cancelled'},end)
            if request.operation!='finalize' or state['size']!=b.byte_count:raise PermissionError('complete original population required')
            data=b''.join(self._read_bytes(state['parts']+[f'chunk-{i}.bin'],CHUNK_BYTES) for i in range(state['count']))
            if len(data)!=b.byte_count or hashlib.sha256(data).hexdigest()!=b.original_sha256 or not data.startswith(b'%PDF-'):raise ValueError('complete original bytes differ')
            self._write(state['parts']+['finalize-intent.json'],dict(request_sha256=digest(request.model_dump(mode='json'))))
            self._live(b)
            snapshot=self.factory.finalize_reserved_pdf_v1(self._q(b),fresh,data,caller_deadline=b.caller_deadline)
            if now()>=end:raise PermissionError('finalize completed outside original lease')
            self._fresh(state,peer_until)
            self._write(state['parts']+['finalize.json'],dict(request_sha256=digest(request.model_dump(mode='json')),snapshot=snapshot.model_dump(mode='json')))
            return self._response({**state,'state':'committed'},end,snapshot)
