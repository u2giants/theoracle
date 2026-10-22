"""Pure invented TAR bytes only; no native process, private original or SQL."""
import ast
import hashlib
import inspect
import io
import pytest
from oracle_brain.hosting import private_archive_policy_v1 as policy
from oracle_brain.hosting import forward_recovery as old
from oracle_brain.hosting import restore_receipts
from test_replacement_recovery_archive_v1 import inventory,tar


def test_exact_original_policy_ast_and_same_object_old_forwarder():
    function=ast.parse(inspect.getsource(policy._read_private_archive_v1)).body[0]
    assert hashlib.sha256(ast.dump(function,include_attributes=False).encode()).hexdigest()=='7be9d363dc3763c5e732d969bdeaad363b9b6e09e4f35ac17d06ee9d0447fcf2'
    assert old._read_private_archive_v1 is policy._read_private_archive_v1
    assert policy.require is restore_receipts.require and policy.MAX_TOTAL==old.MAX_TOTAL and policy.MAX_FILE==old.MAX_FILE
    source=ast.parse(inspect.getsource(old))
    assert not any(isinstance(n,ast.FunctionDef) and n.name=='_read_private_archive_v1' for n in source.body)
    callers=[]
    for n in source.body:
        if isinstance(n,ast.FunctionDef) and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Name) and c.func.id=='_read_private_archive_v1' for c in ast.walk(n)):
            callers.append(n.name)
    assert callers==['_unpack_private_archive_v1','_verify_replacement_archive_fd_v1']


def test_extracted_owner_has_no_native_import_or_process_dependency():
    tree=ast.parse(inspect.getsource(policy))
    imports=[(n.module,n.level) if isinstance(n,ast.ImportFrom) else tuple(a.name for a in n.names)
        for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
    assert imports==[('hashlib',),('tarfile',),('pathlib',0),('restore_receipts',1)]
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in {'run','Popen','connect','open'}
        and isinstance(n.func.value,ast.Name) and n.func.value.id in {'subprocess','psycopg','os'} for n in ast.walk(tree))


def test_valid_byte_and_stream_apis_preserve_actual_bytes_and_metadata():
    data={'originals/a.bin':b'invented bytes'*10000,'models/b.json':b'{}'};raw=tar(data);v=inventory(data)
    files,meta=policy._read_private_archive_v1(io.BytesIO(raw),metadata=True,replacement_inventory=v)
    streamed,smeta=policy._read_private_archive_v1(io.BytesIO(raw),metadata=True,replacement_inventory=v,collect=False)
    assert files==data and streamed==dict.fromkeys(data) and smeta==meta
    assert old.unpack_replacement_archive_v1(raw,v)==(files,meta)
    assert old.unpack(tar({'legacy':b'old exact bytes'}))=={'legacy':b'old exact bytes'}


@pytest.mark.parametrize('attack',['missing','extra','hash','size','duplicate','symlink','hardlink','device','absolute','traversal','mode','uid'])
@pytest.mark.parametrize('collect',[True,False])
def test_same_policy_refuses_hostile_invented_archives_in_both_modes(attack,collect):
    import tarfile
    data={'originals/a.bin':b'invented bytes'};expected=inventory(data);actual=dict(data);options={}
    if attack=='missing':actual={}
    elif attack=='extra':actual['models/extra.json']=b'x'
    elif attack=='hash':actual['originals/a.bin']=b'X'*len(data['originals/a.bin'])
    elif attack=='size':actual['originals/a.bin']+=b'x'
    elif attack=='duplicate':options['duplicate']=True
    elif attack in {'symlink','hardlink','device'}:options['kind']={'symlink':tarfile.SYMTYPE,'hardlink':tarfile.LNKTYPE,'device':tarfile.CHRTYPE}[attack]
    elif attack=='absolute':options['name']='/originals/a.bin'
    elif attack=='traversal':options['name']='../originals/a.bin'
    elif attack=='mode':options['mode']=0o644
    elif attack=='uid':options['uid']=0
    with pytest.raises((PermissionError,ValueError)):
        policy._read_private_archive_v1(io.BytesIO(tar(actual,**options)),replacement_inventory=expected,collect=collect)
