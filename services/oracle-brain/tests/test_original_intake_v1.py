"""Private local source controls, not SQL authority or browser acceptance."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import hashlib,os,json
import pytest
from oracle_brain.operating_model.artifact_storage import FileBlobStore,OriginalObjectRefV1,ReservationOriginalObjectRefV1
from oracle_brain.operating_model.contracts import canonical_bytes

# oracle_brain.hosting pulls in Unix-only fcntl via custody; skip on Windows.
try:
    from oracle_brain.hosting.original_intake_v1 import OriginalIntakeConfigV1,OriginalIntakeAppointmentV1,OriginalIntakeRequestV1,IntakeReservationV1,load_original_intake_settings_v1,reservation_original_ref_v1
    HOSTING_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - platform import guard
    HOSTING_IMPORT_ERROR = exc

requires_hosting = pytest.mark.skipif(
    HOSTING_IMPORT_ERROR is not None,
    reason=f"Windows-blocked: oracle_brain.hosting requires fcntl ({HOSTING_IMPORT_ERROR})")
pytestmark = requires_hosting

def settings(tmp_path):
    root=tmp_path/'already-provisioned';root.mkdir(mode=0o700);info=root.stat();now=datetime.now(timezone.utc);expires=now+timedelta(minutes=1)
    def parse(cls,value):return cls.model_validate_json(json.dumps(dict(schema_version=1,**value),default=str))
    common=dict(auth_issuer='https://invented.invalid/auth/v1',auth_project_id='invented',auth_user_id=uuid4(),employee_id=uuid4(),principal_id=uuid4(),workspace_id=uuid4(),expected_session_role='invented_requester',runtime_hash='a'*64,registry_hash='b'*64,storage_profile_hash='c'*64,original_horizon=expires,expires_at=expires)
    c=parse(OriginalIntakeConfigV1,dict(purpose='original-intake-factory-v1',**common,expected_owner_role='invented_owner',database_url=dict(path='/missing/private/db',sha256='d'*64),database_ca=dict(path='/missing/private/ca',sha256='e'*64),storage_root=str(root),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=info.st_uid))
    cpath=tmp_path/'config';craw=canonical_bytes(c.model_dump(mode='json'));cpath.write_bytes(craw);cpath.chmod(0o600);ch=hashlib.sha256(craw).hexdigest();issuer=uuid4();reviewer=uuid4()
    a=parse(OriginalIntakeAppointmentV1,dict(purpose='original-intake-factory-v1',config_sha256=ch,**common,issuer_actor=issuer,reviewer_actor=reviewer,operations=['create','replace'],valid_from=now-timedelta(seconds=1)))
    apath=tmp_path/'appointment';araw=canonical_bytes(a.model_dump(mode='json'));apath.write_bytes(araw);apath.chmod(0o600)
    return load_original_intake_settings_v1(cpath,ch,apath,hashlib.sha256(araw).hexdigest(),issuer,reviewer)

def records(s,data):
    request=OriginalIntakeRequestV1(source_id=None,expected_head=0,idempotency_key=uuid4(),filename='original.pdf',original_sha256=hashlib.sha256(data).hexdigest(),byte_count=len(data))
    source=uuid4();reservation=uuid4()
    r=IntakeReservationV1(reservation_id=reservation,source_id=source,revision=1,expires_at=s.config.expires_at,private_object_key=f'source-originals/{s.config.workspace_id}/{source}/1/{reservation}')
    return request,r

def test_exact_reservation_private_write_readback_and_legacy_key_unchanged(tmp_path):
    s=settings(tmp_path);data=b'%PDF-1.7\nprivate\x00\xff';q,r=records(s,data);ref,deadline=reservation_original_ref_v1(s,q,r,data)
    store=FileBlobStore(Path(s.config.storage_root));assert store._put_original_bytes(ref,data)==ref;assert store._read_original_bytes(ref)==data;assert store._put_original_bytes(ref,data)==ref
    assert ref.key==r.private_object_key and ref.original.key.endswith(q.original_sha256+'.bin')
    assert deadline<=s.config.expires_at
    with pytest.raises(ValueError):store._put_original_bytes(ref,data+b'x')

@pytest.mark.parametrize('damage',['key','revision','expired','bytes','hash','source'])
def test_reservation_substitution_denies_before_write(tmp_path,damage):
    s=settings(tmp_path);data=b'original';q,r=records(s,data)
    if damage=='key':r=r.model_copy(update={'private_object_key':'source-originals/foreign'})
    elif damage=='revision':r=r.model_copy(update={'revision':2})
    elif damage=='expired':r=r.model_copy(update={'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)})
    elif damage=='bytes':data=b'different'
    elif damage=='hash':q=q.model_copy(update={'original_sha256':'f'*64})
    else:q=q.model_copy(update={'source_id':uuid4(),'expected_head':1})
    with pytest.raises((ValueError,PermissionError)):reservation_original_ref_v1(s,q,r,data)
    assert not (Path(s.config.storage_root)/'source-originals').exists()

@pytest.mark.parametrize('damage',['config','appointment','root-mode','root-symlink','root-replaced'])
def test_startup_pin_and_storage_drift_denies(tmp_path,damage):
    s=settings(tmp_path);root=Path(s.config.storage_root)
    if damage=='config':s.config_path.write_bytes(b'{}')
    elif damage=='appointment':s.appointment_path.write_bytes(b'{}')
    elif damage=='root-mode':root.chmod(0o755)
    elif damage=='root-symlink':root.rename(tmp_path/'original-root');root.symlink_to(tmp_path/'original-root')
    else:root.rename(tmp_path/'original-root');root.mkdir(mode=0o700)
    with pytest.raises((PermissionError,ValueError)):s.current()

def test_private_reservation_ref_is_closed_not_arbitrary_key():
    with pytest.raises(ValueError):ReservationOriginalObjectRefV1(object(),uuid4())

@pytest.mark.parametrize('field',['principal_id','workspace_id','session_role','runtime_hash','source_registry_hash','expired','future'])
def test_sql_context_projection_must_match_all_actual_startup_pins(tmp_path,field):
    from oracle_brain.hosting.original_intake_v1 import RequesterContextV1,_context_horizon
    s=settings(tmp_path);c=s.config;now=datetime.now(timezone.utc)
    value=dict(principal_id=c.principal_id,workspace_id=c.workspace_id,session_role=c.expected_session_role,runtime_hash=c.runtime_hash,source_registry_hash=c.registry_hash,checked_at=now,valid_until=c.expires_at)
    if field in ('principal_id','workspace_id'):value[field]=uuid4()
    elif field=='session_role':value[field]='foreign_requester'
    elif field in ('runtime_hash','source_registry_hash'):value[field]='f'*64
    elif field=='expired':value['valid_until']=now-timedelta(seconds=1)
    else:value['checked_at']=now+timedelta(seconds=1)
    proof=RequesterContextV1(**value)
    with pytest.raises(PermissionError):_context_horizon(s,proof)

def test_missing_actual_sql_target_cannot_write_original(tmp_path):
    from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1
    s=settings(tmp_path);q,_=records(s,b'original');factory=OriginalIntakeFactoryV1(s)
    with pytest.raises((FileNotFoundError,PermissionError)):
        factory.intake_pdf_v1(source_id=q.source_id,expected_head=q.expected_head,idempotency_key=q.idempotency_key,filename=q.filename,original_sha256=q.original_sha256,data=b'original')
    assert not (Path(s.config.storage_root)/'source-originals').exists()

def test_reservation_extension_preserves_legacy_json_and_closed_types(tmp_path):
    data=b'original';store=FileBlobStore(tmp_path/'owned');original=OriginalObjectRefV1(uuid4(),uuid4(),1,hashlib.sha256(data).hexdigest(),len(data),'application/pdf','a'*64)
    store._put_original_bytes(original,data);assert store._read_original_bytes(original)==data
    key,seal=store.put(original.workspace_id,{'reading':'设计'})
    assert store.read(key,seal)=='{"reading":"设计"}'.encode()
    class Borrowed(ReservationOriginalObjectRefV1):pass
    with pytest.raises(ValueError):store._put_original_bytes(Borrowed(original,uuid4()),data)

def test_intake_public_snapshot_has_no_private_context_or_schema_fields():
    from oracle_brain.hosting.original_intake_v1 import OriginalIntakeSnapshotV1
    value=OriginalIntakeSnapshotV1(sourceId=uuid4(),revision=1,originalSha256='a'*64,byteCount=1,mediaType='application/pdf',filename='original.pdf',state='awaiting_original_reading',qualifiedSourceRef=None)
    assert set(value.model_dump(mode='json'))=={'sourceId','revision','originalSha256','byteCount','mediaType','filename','state','qualifiedSourceRef'}
    with pytest.raises(ValueError):OriginalIntakeSnapshotV1.model_validate(value.model_dump()|{'private_object_key':'forbidden'})

def test_provisioned_private_store_never_recreates_root_and_detects_open_race(tmp_path):
    root=tmp_path/'provisioned';root.mkdir(mode=0o700);info=root.stat();identity=(info.st_dev,info.st_ino,info.st_uid)
    store=FileBlobStore._from_provisioned_original_root(root,identity)
    original=OriginalObjectRefV1(uuid4(),uuid4(),1,hashlib.sha256(b'x').hexdigest(),1,'application/pdf','a'*64);ref=ReservationOriginalObjectRefV1(original,uuid4())
    root.rename(tmp_path/'original');root.mkdir(mode=0o700)
    with pytest.raises(PermissionError):store._put_original_bytes(ref,b'x')
    assert not (root/'source-originals').exists()
    root.rmdir()
    with pytest.raises(FileNotFoundError):FileBlobStore._from_provisioned_original_root(root,identity)
    assert not root.exists()


@pytest.mark.parametrize('kind',['naive','string','expired','excessive'])
def test_caller_absolute_deadline_cannot_extend_existing_intake_scope(tmp_path,kind):
    from oracle_brain.hosting.original_intake_v1 import _intake_current_deadline
    s=settings(tmp_path);value=datetime.now(timezone.utc)+timedelta(seconds=5)
    if kind=='naive':value=value.replace(tzinfo=None)
    elif kind=='string':value=value.isoformat()
    elif kind=='expired':value=datetime.now(timezone.utc)-timedelta(seconds=1)
    else:value=s.config.original_horizon+timedelta(seconds=1)
    with pytest.raises(PermissionError):_intake_current_deadline(s,value)
