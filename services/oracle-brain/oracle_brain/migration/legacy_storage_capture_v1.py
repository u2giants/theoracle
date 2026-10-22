"""Fixed CURRENT document capture; not historical-original or read authority.

Actual source SQL/export root, server-validated ordinary technical Auth session
and provider Storage RLS are independent intersections. No token issuance,
service key, employee impersonation, ambient credentials, retry or URL callback.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import threading
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, field_validator, model_validator
from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes, digest
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1, _pinned, _parse
from oracle_brain.operating_model.protected_http_wire_v1 import _artifact_response_v1
from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
from oracle_brain.operating_model.artifact_storage import _write_private_at, _parent_fd, _read_private_at
from ._legacy_s3_signing_v1 import _canonical_object_path_v1, _s3_read_headers_v1, _strong_etag_v1

MAX_PDF_BYTES=25*1024*1024
MAX_AGGREGATE_BYTES=64*1024*1024


class LegacyStorageCaptureProfileV1(StrictRecord):
    purpose: Literal['legacy-storage-current-capture-v1']
    origin_system: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,127}$')
    principal_id: UUID
    workspace_id: UUID
    source_scope_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_program_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    project_ref: str = Field(pattern=r'^[a-z0-9]{20}$')
    auth_subject: UUID
    credential_kind: Literal['externally-issued-ordinary-authenticated-session']
    expected_auth_role: Literal['authenticated']
    session_token: ProtectedInputV1
    anonymous_key: ProtectedInputV1
    auth_address: str
    storage_address: str
    auth_port: int = Field(strict=True,ge=1,le=65535,default=443)
    storage_port: int = Field(strict=True,ge=1,le=65535,default=443)
    region: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+){1,5}$')
    auth_ca: ProtectedInputV1
    storage_ca: ProtectedInputV1
    auth_server_der_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    storage_server_der_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    storage_root: str
    storage_device: int = Field(strict=True,ge=0)
    storage_inode: int = Field(strict=True,ge=1)
    storage_uid: int = Field(strict=True,ge=0)
    max_document_bytes: int = Field(strict=True,ge=1,le=MAX_PDF_BYTES)
    max_aggregate_bytes: int = Field(strict=True,ge=1,le=MAX_AGGREGATE_BYTES)
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def _version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact capture profile version required')
        return value

    @model_validator(mode='after')
    def _closed(self):
        for value in (self.auth_address,self.storage_address):
            addr=ipaddress.ip_address(value)
            if str(addr)!=value or addr.is_multicast or addr.is_unspecified or addr.is_link_local:
                raise ValueError('exact independently pinned unicast address required')
        root=Path(self.storage_root)
        if (not root.is_absolute() or str(root)!=self.storage_root or not self.valid_from<self.expires_at<=self.original_horizon
                or any(t.utcoffset()!=timedelta(0) for t in (self.valid_from,self.expires_at,self.original_horizon))):
            raise ValueError('original finite capture installation required')
        return self


class LegacyCaptureUnavailable(PermissionError):
    def __init__(self, reason):
        if reason not in ('storage-read-unavailable','object-precondition-failed','capture-incomplete','unsupported-document-media','capture-coverage-gap'):
            raise ValueError('closed capture refusal required')
        self.reason=reason
        super().__init__('Current document capture unavailable; no intake or retry authorized')


class _CaptureWireUnknownV1(LegacyCaptureUnavailable):
    def __init__(self,wire):
        super().__init__('capture-incomplete')
        self.wire=bytes(wire[:MAX_PDF_BYTES+16384])


@dataclass(frozen=True)
class LegacyCurrentDocumentV1:
    legacy_id: UUID
    original_sha256: str
    byte_count: int
    media_type: Literal['application/pdf']
    capture: dict = field(repr=False)
    data: bytes = field(repr=False)
    valid_until: datetime
    historical_original_proven: Literal[False] = False
    qualification: Literal[False] = False


def _json_object_v1(raw, maximum):
    if type(raw) is not bytes or not 1<=len(raw)<=maximum:raise PermissionError('bounded actual server object required')
    def unique(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('duplicate actual server field')
            out[k]=v
        return out
    def constant(_):raise ValueError('nonfinite actual server field')
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=constant)
    if type(value) is not dict:raise PermissionError('actual server object required')
    return value


class LegacyDocumentCaptureV1:
    def __init__(self, profile_path, profile_sha256, reader):
        from .legacy_export_reader_v1 import TechnicalLegacyExportReaderV1
        if type(reader) is not TechnicalLegacyExportReaderV1:
            raise TypeError('actual independently admitted technical source reader required')
        self.path,self.sha256,self.reader=Path(profile_path),profile_sha256,reader
        self.profile=_parse(LegacyStorageCaptureProfileV1,_pinned(self.path,self.sha256,131072))
        self._active=None
        self._slot=threading.Lock()
        self._installed()

    def _installed(self):
        from .legacy_export_reader_v1 import actual_export_program_sha256_v1
        p=self.profile;c=self.reader.authority.settings.config
        if (_parse(LegacyStorageCaptureProfileV1,_pinned(self.path,self.sha256,131072))!=p
                or (p.origin_system,p.principal_id,p.workspace_id,p.source_scope_sha256,p.source_program_sha256)!=
                   (c.origin_system,c.principal_id,c.workspace_id,c.source_scope_sha256,c.source_program_sha256)
                or p.source_program_sha256!=actual_export_program_sha256_v1()
                or p.auth_subject==self.reader.profile.source_scope.auth_user_id):
            raise PermissionError('independent actual current capture installation differs')
        for item in (p.session_token,p.anonymous_key,p.auth_ca,p.storage_ca):
            _pinned(item.path,item.sha256,131072)
        now=datetime.now(timezone.utc)
        if not p.valid_from<=now<min(p.expires_at,p.original_horizon):
            raise PermissionError('original capture installation expired')
        info=Path(p.storage_root).lstat()
        import os,stat
        if (Path(p.storage_root).resolve()!=Path(p.storage_root) or not stat.S_ISDIR(info.st_mode)
                or info.st_mode&0o077 or info.st_uid!=os.getuid()
                or (info.st_dev,info.st_ino,info.st_uid)!=(p.storage_device,p.storage_inode,p.storage_uid)):
            raise PermissionError('independent private capture root differs')
        return min(p.expires_at,p.original_horizon)

    def _time(self,deadline):
        self.reader._time(deadline)
        until=self._installed();now=datetime.now(timezone.utc)
        if not now<deadline<=min(until,now+timedelta(seconds=30)):
            raise PermissionError('same original capture deadline required')
        return min(request_remaining_v1(),(deadline-now).total_seconds())

    def _remaining(self,deadline):
        # Per-byte framing guard uses the SAME immutable original window. File
        # and source/role pins are freshly rechecked at every I/O boundary.
        now=datetime.now(timezone.utc)
        if deadline>min(self.profile.expires_at,self.profile.original_horizon):
            raise PermissionError('capture window cannot renew installation')
        remaining=min(request_remaining_v1(),(deadline-now).total_seconds())
        if remaining<=0:raise PermissionError('original capture window elapsed')
        return remaining

    def _source_current(self,deadline):
        self._time(deadline)
        self.reader.authority.source_context_v1(caller_deadline=deadline)
        actual=self.reader._pass(deadline)
        if self._active is None or actual[0]!=self._active['source_projection']:
            raise PermissionError('current actual source/identity/member/link changed')
        self._time(deadline)
        return actual

    def _credentials(self):
        p=self.profile
        values=[]
        for item in (p.session_token,p.anonymous_key):
            value=_pinned(item.path,item.sha256,16384).decode('ascii')
            if re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',value) is None:
                raise PermissionError('independently supplied ordinary session/anonymous key required')
            values.append(value)
        return tuple(values)

    def _exchange(self,kind,method,path,headers,deadline,maximum):
        # Internal closed owner only; no externally injected auth callback or
        # arbitrary target/method. Source sockets close before HTTP bytes.
        if kind not in ('auth','storage') or method not in ('HEAD','GET'):
            raise PermissionError('closed current-capture HTTP operation required')
        p=self.profile
        host=p.project_ref+('.supabase.co' if kind=='auth' else '.storage.supabase.co')
        address=p.auth_address if kind=='auth' else p.storage_address
        port=p.auth_port if kind=='auth' else p.storage_port
        ca=p.auth_ca if kind=='auth' else p.storage_ca
        seal=p.auth_server_der_sha256 if kind=='auth' else p.storage_server_der_sha256
        self._time(deadline)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(cadata=_pinned(ca.path,ca.sha256,131072).decode('utf8'))
        family=socket.AF_INET6 if ipaddress.ip_address(address).version==6 else socket.AF_INET
        active=socket.socket(family,socket.SOCK_STREAM);timer=None;response=None
        try:
            # Watchdog covers connect+TLS+headers/body and EOF, independently of
            # socket idle timeout. The exact active socket alone is closed.
            def stop():
                try:active.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                finally:active.close()
            timer=threading.Timer(self._time(deadline),stop);timer.daemon=True;timer.start()
            active.settimeout(self._remaining(deadline));active.connect((address,port))
            active.settimeout(self._remaining(deadline))
            active=context.wrap_socket(active,server_hostname=host,suppress_ragged_eofs=False,do_handshake_on_connect=False)
            # Watchdog already owns the actual SSLSocket before TLS can block.
            active.do_handshake()
            if hashlib.sha256(active.getpeercert(binary_form=True)).hexdigest()!=seal:
                raise PermissionError('actual capture peer DER differs')
            self._source_current(deadline)
            authority=host if port==443 else host+':'+str(port)
            sent=dict(headers)
            if 'host' in sent and sent['host']!=authority:
                raise PermissionError('signed actual capture Host differs')
            sent['host']=authority;sent['accept-encoding']='identity';sent['connection']='close'
            if any(re.fullmatch(r'[a-z0-9-]+',k) is None or type(v) is not str or re.search(r'[\x00-\x1f\x7f]',v) for k,v in sent.items()):
                raise PermissionError('closed actual request headers required')
            raw=(method+' '+path+' HTTP/1.1\r\n'+''.join(k+': '+v+'\r\n' for k,v in sent.items())+'\r\n').encode('ascii')
            if len(raw)>65536:raise PermissionError('bounded actual request required')
            active.settimeout(self._remaining(deadline));active.sendall(raw)
            response=_artifact_response_v1(active,lambda:self._remaining(deadline),maximum,method=method)
            response.begin();pairs=response.getheaders();seen=set();actual_headers={}
            for k,v in pairs:
                k=k.lower()
                if k in seen:raise LegacyCaptureUnavailable('capture-incomplete')
                seen.add(k);actual_headers[k]=v
            if 'content-encoding' in seen or 'content-range' in seen:
                raise LegacyCaptureUnavailable('capture-incomplete')
            length=actual_headers.get('content-length');transfer=actual_headers.get('transfer-encoding')
            if transfer:
                if method=='HEAD' or transfer!='chunked' or length is not None:raise LegacyCaptureUnavailable('capture-incomplete')
            elif length is None or re.fullmatch(r'0|[1-9][0-9]{0,8}',length) is None or method!='HEAD' and int(length)>maximum:
                raise LegacyCaptureUnavailable('capture-incomplete')
            body=bytearray()
            while method!='HEAD' and len(body)<=maximum:
                active.settimeout(self._remaining(deadline));part=response.read(min(65536,maximum+1-len(body)))
                if not part:break
                body.extend(part)
                if len(body)>maximum:raise LegacyCaptureUnavailable('capture-incomplete')
            if method!='HEAD' and length is not None and len(body)!=int(length):raise LegacyCaptureUnavailable('capture-incomplete')
            active.settimeout(self._remaining(deadline))
            if active.recv(1):raise LegacyCaptureUnavailable('capture-incomplete')
            wire=b''.join(response._oracle_wire_v1.chunks)
            self._time(deadline)
            return dict(status=response.status,headers=actual_headers,body=bytes(body),wire=wire,observed_at=datetime.now(timezone.utc))
        except LegacyCaptureUnavailable:
            wire=b''.join(response._oracle_wire_v1.chunks) if response is not None else b''
            raise _CaptureWireUnknownV1(wire) from None
        except PermissionError:
            raise
        except Exception:
            wire=b''.join(response._oracle_wire_v1.chunks) if response is not None else b''
            raise _CaptureWireUnknownV1(wire) from None
        finally:
            if timer is not None:timer.cancel()
            if response is not None:response.close()
            active.close()
            if timer is not None:
                timer.join(timeout=1)
                if timer.is_alive():raise PermissionError('actual capture socket timer cleanup unknown')

    def _auth(self,deadline):
        token,anonymous=self._credentials()
        actual=self._exchange('auth','GET','/auth/v1/user',{'authorization':'Bearer '+token,'apikey':anonymous},deadline,65536)
        if actual['status']!=200:raise LegacyCaptureUnavailable('storage-read-unavailable')
        user=_json_object_v1(actual['body'],65536)
        if (user.get('id')!=str(self.profile.auth_subject) or user.get('role')!='authenticated'
                or user.get('is_anonymous') is not False):
            raise PermissionError('actual ordinary technical Auth subject/role differs')
        # Only AFTER actual server identity validation may local claims narrow
        # expiry. They authenticate no subject, role or storage permission.
        payload=token.split('.')[1];claims=_json_object_v1(base64.urlsafe_b64decode(payload+'='*((-len(payload))%4)),16384)
        exp=claims.get('exp')
        if type(exp) is not int or not 0<exp<253402300800:
            raise PermissionError('finite actual session expiry required')
        until=datetime.fromtimestamp(exp,timezone.utc)
        if deadline>until:raise PermissionError('original capture exceeds actual session expiry')
        return actual

    def _storage(self,method,path,deadline,etag=None):
        token,anonymous=self._credentials();p=self.profile
        headers=_s3_read_headers_v1(method=method,path=path,host=p.project_ref+'.storage.supabase.co',region=p.region,
            project_ref=p.project_ref,anonymous_key=anonymous,session_token=token,now=datetime.now(timezone.utc),etag=etag,port=p.storage_port)
        return self._exchange('storage',method,path,headers,deadline,p.max_document_bytes if method=='GET' else 0)

    def _put(self,key,data):
        p=self.profile
        _write_private_at(p.storage_root,key.split('/'),data,expected_root=(p.storage_device,p.storage_inode,p.storage_uid))

    def _read_back(self,key,maximum):
        import os
        p=self.profile
        parent=_parent_fd(p.storage_root,key.split('/')[:-1],create=False,
            expected_root=(p.storage_device,p.storage_inode,p.storage_uid))
        try:return _read_private_at(parent,key.split('/')[-1],maximum)
        finally:os.close(parent)

    def capture_document_v1(self,document_id,*,caller_deadline,remaining_aggregate_bytes=None):
        if type(document_id) is not UUID or document_id not in self.reader.profile.source_scope.document_ids:
            raise PermissionError('exact installed document scope required')
        if not self._slot.acquire(blocking=False):raise PermissionError('one active exact capture required')
        capture_id=uuid4();prefix='legacy-original-captures/'+str(self.profile.workspace_id)+'/'+str(capture_id)
        traces=[]
        try:
            self._time(caller_deadline)
            self.reader.authority.source_context_v1(caller_deadline=caller_deadline)
            before=self.reader._pass(caller_deadline)
            links=[r for r in before[2] if r[0]==document_id]
            targets={(r[4],r[5],r[3]) for r in links}
            if not links or len(targets)!=1:raise LegacyCaptureUnavailable('storage-read-unavailable')
            bucket,key,media=next(iter(targets))
            if media!='application/pdf':raise LegacyCaptureUnavailable('unsupported-document-media')
            path=_canonical_object_path_v1(bucket,key)
            self._active=dict(source_projection=before[0])
            traces.append(self._auth(caller_deadline))
            first=self._storage('HEAD',path,caller_deadline);traces.append(first)
            if first['status']!=200:raise LegacyCaptureUnavailable('storage-read-unavailable')
            try:etag=_strong_etag_v1(first['headers'].get('etag'))
            except PermissionError:raise LegacyCaptureUnavailable('capture-incomplete') from None
            length=first['headers'].get('content-length')
            budget=self.profile.max_aggregate_bytes if remaining_aggregate_bytes is None else remaining_aggregate_bytes
            if type(budget) is not int or budget<0:raise PermissionError('restrictive actual aggregate budget required')
            if not length or not length.isdigit() or not 1<=int(length)<=min(self.profile.max_document_bytes,self.profile.max_aggregate_bytes,budget):
                raise LegacyCaptureUnavailable('capture-coverage-gap')
            if first['headers'].get('content-type')!='application/pdf':raise LegacyCaptureUnavailable('unsupported-document-media')
            body=self._storage('GET',path,caller_deadline,etag);traces.append(body)
            if body['status']==412:raise LegacyCaptureUnavailable('object-precondition-failed')
            if (body['status']!=200 or body['headers'].get('etag')!=etag or body['headers'].get('content-type')!='application/pdf'
                    or len(body['body'])!=int(length) or not body['body'].startswith(b'%PDF-')):
                raise LegacyCaptureUnavailable('capture-incomplete')
            last=self._storage('HEAD',path,caller_deadline,etag);traces.append(last)
            if (last['status']!=200 or any(last['headers'].get(k)!=first['headers'].get(k) for k in ('etag','content-length','content-type'))):
                raise LegacyCaptureUnavailable('object-precondition-failed')
            traces.append(self._auth(caller_deadline))
            self._source_current(caller_deadline)
            self.reader.authority.source_context_v1(caller_deadline=caller_deadline)
            original=body['body'];sha=hashlib.sha256(original).hexdigest()
            observations=[]
            for number,trace in enumerate(traces):
                wire_key=prefix+'/'+str(number)+'.wire';self._time(caller_deadline);self._put(wire_key,trace['wire'])
                header_end=trace['wire'].find(b'\r\n\r\n')+4
                if not 4<=header_end<=16384:raise PermissionError('actual observed response header unavailable')
                observations.append(dict(http_status=trace['status'],header_sha256=hashlib.sha256(trace['wire'][:header_end]).hexdigest(),
                    header_byte_count=header_end,wire_sha256=hashlib.sha256(trace['wire']).hexdigest(),
                    wire_byte_count=len(trace['wire']),private_wire_key=wire_key,observed_at=trace['observed_at'].isoformat()))
            body_key=prefix+'/original.pdf';self._time(caller_deadline);self._put(body_key,original)
            self._time(caller_deadline)
            retained=self._read_back(body_key,len(original));self._time(caller_deadline)
            if retained!=original or hashlib.sha256(retained).hexdigest()!=sha:
                raise PermissionError('actual private current capture readback differs')
            original=retained
            receipt=dict(schema_version=1,purpose='legacy-current-original-capture-v1',capture_id=str(capture_id),legacy_id=str(document_id),
                source_projection_sha256=before[0],producer_profile_sha256=self.sha256,auth_subject=str(self.profile.auth_subject),
                etag=etag,original_sha256=sha,byte_count=len(original),media_type='application/pdf',private_body_key=body_key,
                observations=observations,original_deadline=caller_deadline.isoformat(),historical_original_proven=False,qualification=False,company_acceptance=False)
            raw=canonical_bytes(receipt);receipt_key=prefix+'/receipt.json';self._time(caller_deadline);self._put(receipt_key,raw)
            # Filesystem writes may finish late: no subsequent SQL/delivery then.
            self._time(caller_deadline)
            self._source_current(caller_deadline)
            capture=dict(receipt,private_receipt_key=receipt_key,receipt_sha256=hashlib.sha256(raw).hexdigest(),receipt_byte_count=len(raw))
            return LegacyCurrentDocumentV1(document_id,sha,len(original),'application/pdf',capture,original,caller_deadline)
        except _CaptureWireUnknownV1 as error:
            # Preserve only exact own in-flight observation, no renewed read or
            # target intake after timeout. This is NOT canonical intake custody.
            self._time(caller_deadline)
            self._put(prefix+'/UNKNOWN.wire',error.wire)
            # A late filesystem completion cannot authorize any later write,
            # SQL observation, intake or successful capture response.
            self._time(caller_deadline)
            raise LegacyCaptureUnavailable('capture-incomplete') from None
        finally:
            self._active=None
            self._slot.release()
