import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).parents[3]/'scripts/oracle2/verify_workflow_integrity.py'
spec=importlib.util.spec_from_file_location('operating_verifier',path)
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)

def test_named_workflow_stages_and_modes_preserve_separate_acceptance():
    for index in range(1,13):
        options=verifier.parse_options(['--stage',f'W{index:02d}','--mode','synthetic','--result','owned-result.json'])
        assert options.stage==f'W{index:02d}' and options.mode=='synthetic'
        assert verifier.required_suites(options.stage)
    assert verifier.required_suites('W10')==verifier.DOCUMENTARY+verifier.EVENT

def test_private_audit_cannot_touch_stores_without_separate_admission(monkeypatch):
    monkeypatch.setattr(verifier.psycopg,'connect',lambda *a,**k:pytest.fail('private gate opened a store'))
    with pytest.raises(PermissionError,match='Independent private-audit admission'):
        verifier.main(['--stage','W10','--mode','private-audit'])

@pytest.fixture
def public_chain_tree(tmp_path,monkeypatch):
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    for relative in verifier.PUBLIC_CHAIN:
        path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'INVENTED PUBLIC SOURCE '+relative.encode())
    return tmp_path

@pytest.mark.parametrize('index',range(4))
@pytest.mark.parametrize('damage',['missing','symlink','fifo','hardlink','directory','oversize'])
def test_required_public_chain_rejects_every_bad_member_before_any_byte_read(public_chain_tree,index,damage,monkeypatch):
    import os
    path=public_chain_tree/verifier.PUBLIC_CHAIN[index]
    path.unlink()
    if damage=='symlink':path.symlink_to(public_chain_tree/verifier.PUBLIC_CHAIN[(index+1)%4])
    elif damage=='fifo':os.mkfifo(path)
    elif damage=='hardlink':os.link(public_chain_tree/verifier.PUBLIC_CHAIN[(index+1)%4],path)
    elif damage=='directory':path.mkdir()
    elif damage=='oversize':
        with path.open('wb') as file:file.truncate(verifier.PUBLIC_SOURCE_LIMIT+1)
    monkeypatch.setattr(verifier.os,'read',lambda *args:pytest.fail('bad closure reached byte hashing'))
    with pytest.raises((RuntimeError,OSError)):verifier.required_public_chain_hashes()

def test_required_public_chain_hashes_exact_fixed_population(public_chain_tree):
    import hashlib
    assert verifier.required_public_chain_hashes()=={name:hashlib.sha256((public_chain_tree/name).read_bytes()).hexdigest() for name in verifier.PUBLIC_CHAIN}

def test_required_public_chain_linked_parent_refuses_before_read(public_chain_tree,monkeypatch):
    parent=public_chain_tree/'scripts/oracle2/contracts';moved=parent.with_name('moved');parent.rename(moved);parent.symlink_to(moved,target_is_directory=True)
    monkeypatch.setattr(verifier.os,'read',lambda *args:pytest.fail('linked parent reached byte hashing'))
    with pytest.raises(OSError):verifier.required_public_chain_hashes()

@pytest.mark.parametrize('damage',['content','mode','replace'])
def test_public_source_mutation_during_fd_hashing_refuses(public_chain_tree,monkeypatch,damage):
    import os
    target=public_chain_tree/verifier.PUBLIC_CHAIN[0];real=os.read;changed=False
    def reader(fd,size):
        nonlocal changed
        result=real(fd,size)
        if not changed:
            changed=True
            if damage=='mode':target.chmod(0o600)
            elif damage=='replace':
                target.rename(target.with_name('old'));target.write_bytes(b'INVENTED REPLACEMENT')
            else:target.write_bytes(b'INVENTED ALTERED CONTENT')
        return result
    monkeypatch.setattr(verifier.os,'read',reader)
    with pytest.raises(RuntimeError,match='changed'):verifier.required_public_chain_hashes()


def test_required_documentary_gate_includes_fresh_original_journey():
    from scripts.oracle2.verify_workflow_integrity import required_suites
    assert 'replacement_documentary_journey' in required_suites('W10')
    assert 'replacement_documentary_journey' in required_suites('documentary')


def test_required_documentary_gate_includes_processing_contract_and_transport():
    assert {'processing_context','processing_profile'} <= set(verifier.required_suites('W10'))


def test_qualified_assembly_suites_are_in_required_documentary_gate():
    assert {'assembly_context','assembly_qualification','observed_assembly_capture'} <= set(verifier.DOCUMENTARY)
    for name in ('assembly_context','assembly_qualification','observed_assembly_capture'):
        assert (Path(__file__).parent/f'test_{name}.py').is_file()


def test_processing_role_and_journey_proofs_are_required_with_explicit_migrations():
    assert {'source_processing_qualification','processing_compiler_capabilities',
        'processing_projection_leases','processing_documentary_journey'} <= set(verifier.DOCUMENTARY)
    assert verifier.SYNTHETIC_MIGRATIONS==('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql',
        '006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql',
        '008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql',
        '010_hosting_job_permissions.sql','011_hosting_source_processing_permissions.sql',
        '012_processing_compiler_capabilities.sql')
