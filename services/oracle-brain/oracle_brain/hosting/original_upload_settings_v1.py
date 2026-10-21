"""External chunk transport/spool installation, no role or grant issuance."""
from pathlib import Path
from typing import Literal
import os,stat
from pydantic import Field
from .replacement_request_service_v1 import RequesterPeerProfileV1,_load_peer_settings_v1
from .original_intake_v1 import _pinned
from oracle_brain.operating_model.contracts import canonical_bytes

class OriginalUploadPeerV1(RequesterPeerProfileV1):
    purpose:Literal['original-upload-chunks-peer-v1']
    spool_root:str
    spool_device:int=Field(strict=True,ge=0)
    spool_inode:int=Field(strict=True,gt=0)
    spool_uid:int=Field(strict=True,ge=0)
    spool_initialization_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


def check_upload_spool_v1(settings):
    settings.current();p=settings.profile;root=Path(p.spool_root)
    if not root.is_absolute() or root.resolve()!=root:raise PermissionError('exact upload spool required')
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode&0o077 or (info.st_dev,info.st_ino,info.st_uid)!=(p.spool_device,p.spool_inode,p.spool_uid) or info.st_uid!=os.getuid():raise PermissionError('appointed upload spool differs')
    lock=root/'upload.lock';i=lock.lstat()
    if not stat.S_ISREG(i.st_mode) or i.st_mode&0o077 or i.st_uid!=os.getuid() or i.st_nlink!=1 or lock.resolve()!=lock:raise PermissionError('protected upload lock required')
    expected=dict(schema_version=1,purpose='original-upload-spool-v1',workspace_id=str(p.workspace_id),principal_id=str(p.principal_id),runtime_hash=p.runtime_hash,registry_hash=p.registry_hash,lock_device=i.st_dev,lock_inode=i.st_ino,lock_uid=i.st_uid)
    if _pinned(root/'initialization.json',p.spool_initialization_sha256)!=canonical_bytes(expected):raise PermissionError('external upload initialization differs')
    return root


def load_original_upload_settings_v1(intake,path,sha256):
    s=_load_peer_settings_v1(intake,path,sha256,OriginalUploadPeerV1)
    check_upload_spool_v1(s);return s
