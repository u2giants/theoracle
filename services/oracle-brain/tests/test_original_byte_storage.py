"""Private local/mock-object I/O only; no lifecycle authority/factory exists."""
import hashlib,io,os
from dataclasses import replace
from uuid import uuid4
import pytest

from test_binary_documents import docx,xlsx,pptx

from oracle_brain.operating_model.artifact_storage import FileBlobStore,ObjectBlobStore,OriginalObjectRefV1

def ref(data):return OriginalObjectRefV1(uuid4(),uuid4(),1,hashlib.sha256(data).hexdigest(),len(data),'application/octet-stream','a'*64)

@pytest.mark.parametrize('data',[docx(),xlsx(),pptx(),b'%PDF-1.7\nprivate binary\x00\xff'])
def test_exact_original_bytes_and_legacy_json_stay_separate(tmp_path,data):
    store=FileBlobStore(tmp_path/'own');r=ref(data)
    assert store._put_original_bytes(r,data)==r
    assert store._put_original_bytes(r,data)==r
    assert store._read_original_bytes(r)==data
    key,seal=store.put(r.workspace_id,{'unicode':'设计'})
    assert store.read(key,seal)=='{"unicode":"设计"}'.encode()
    assert r.key.startswith('source-originals/') and key.startswith('operating-model/')

@pytest.mark.parametrize('damage',['symlink','hardlink','world-readable','oversize','mutated','foreign-owner'])
def test_private_object_path_and_identity_drift_denies(tmp_path,monkeypatch,damage):
    store=FileBlobStore(tmp_path/'own');data=b'original';r=ref(data);store._put_original_bytes(r,data)
    path=store.root/r.key
    if damage=='symlink':
        own=tmp_path/'outside';own.write_bytes(data);path.unlink();path.symlink_to(own)
    elif damage=='hardlink':os.link(path,tmp_path/'other-link')
    elif damage=='world-readable':path.chmod(0o644)
    elif damage=='oversize':path.write_bytes(data+b'x')
    elif damage=='mutated':path.write_bytes(b'changed!')
    else:monkeypatch.setattr(os,'getuid',lambda:os.stat(path).st_uid+1)
    with pytest.raises((PermissionError,ValueError,OSError)):store._read_original_bytes(r)

def test_symlink_parent_root_and_writable_parent_refused(tmp_path):
    store=FileBlobStore(tmp_path/'own');r=ref(b'a');parent=store.root/'source-originals';outside=tmp_path/'outside';outside.mkdir(mode=0o700)
    parent.symlink_to(outside,target_is_directory=True)
    with pytest.raises(OSError):store._put_original_bytes(r,b'a')
    parent.unlink();parent.mkdir(mode=0o777);parent.chmod(0o777)
    with pytest.raises(PermissionError):store._put_original_bytes(r,b'a')
    alias=tmp_path/'alias';alias.symlink_to(store.root,target_is_directory=True)
    with pytest.raises(PermissionError):FileBlobStore(alias)._put_original_bytes(r,b'a')

def test_legacy_json_existing_parent_permissions_are_preserved(tmp_path):
    store=FileBlobStore(tmp_path/'own');workspace=ref(b'a').workspace_id
    parent=store.root/'operating-model'/str(workspace);parent.mkdir(parents=True);parent.chmod(0o755)
    (store.root/'operating-model').chmod(0o755)
    key,h=store.put(workspace,{'legacy':True});path=store.root/key;path.chmod(0o644)
    assert store.put(workspace,{'legacy':True})==(key,h)
    assert store.read(key,h)==b'{"legacy":true}'
    assert parent.stat().st_mode&0o777==0o755 and path.stat().st_mode&0o777==0o644

def test_partial_new_write_failure_removes_only_own_new_link(tmp_path,monkeypatch):
    store=FileBlobStore(tmp_path/'own');r=ref(b'first');store._put_original_bytes(r,b'first')
    fresh=replace(r,revision=2)
    original_sync=os.fsync
    def fail_file(fd):
        import stat
        if stat.S_ISREG(os.fstat(fd).st_mode):raise OSError('synthetic disk failure')
        original_sync(fd)
    monkeypatch.setattr(os,'fsync',fail_file)
    with pytest.raises(OSError):store._put_original_bytes(fresh,b'first')
    assert not (store.root/fresh.key).exists() and store._read_original_bytes(r)==b'first'
    # Idempotent object is never removed by the failed new-file path.
    assert store._put_original_bytes(r,b'first')==r

@pytest.mark.parametrize('field,value',[('revision',True),('revision',0),('byte_count',True),('byte_count',26*1024*1024),
    ('original_sha256','../evil'),('storage_profile_hash',None),('schema_version',True),('workspace_id','not-uuid')])
def test_strict_typed_private_identity(field,value):
    with pytest.raises(ValueError):replace(ref(b'a'),**{field:value})

class Conflict(Exception):
    response={'ResponseMetadata':{'HTTPStatusCode':412}}
class MockObjectClient:
    def __init__(self):self.objects={};self.calls=[];self.bodies=[]
    def put_object(self,**kw):
        self.calls.append(kw)
        assert kw['IfNoneMatch']=='*'
        key=(kw['Bucket'],kw['Key'])
        if key in self.objects:raise Conflict()
        self.objects[key]=kw['Body']
    def get_object(self,**kw):
        body=io.BytesIO(self.objects[(kw['Bucket'],kw['Key'])]);self.bodies.append(body);return {'Body':body}

def test_same_object_client_conditional_write_readback_and_bounded_mismatch():
    client=MockObjectClient();store=ObjectBlobStore(client,'own-mock-private');data=docx();r=ref(data)
    assert store._put_original_bytes(r,data)==r and store._put_original_bytes(r,data)==r
    assert store._read_original_bytes(r)==data and all(b.closed for b in client.bodies)
    assert all(c['Bucket']=='own-mock-private' and c['ContentType']==r.content_type for c in client.calls)
    client.objects[(store.bucket,r.key)]=data+b'x'
    with pytest.raises(ValueError):store._read_original_bytes(r)
    with pytest.raises(ValueError):store._put_original_bytes(r,data)
    assert all(b.closed for b in client.bodies)
