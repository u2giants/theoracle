"""Networkless materializer denies unsealed populations before any write."""
import base64,hashlib,json,os
import pytest
from oracle_brain.hosting import bootstrap

def bundle(profile,values):
    raw=json.dumps({'schema':'oracle-hosted-files/v1','profile':profile,'files':{k:{'bytes_b64':base64.b64encode(v).decode(),'sha256':hashlib.sha256(v).hexdigest()} for k,v in values.items()}}).encode()
    return base64.b64encode(raw).decode(),hashlib.sha256(raw).hexdigest()

@pytest.fixture
def profile(monkeypatch):
    # Avoid changing machine identities in tests; deployment profile remains fixed.
    monkeypatch.setitem(bootstrap.FILES,'candidate',({'server.conf'},os.getuid()))


def test_sealed_files_protected_and_repeatable(tmp_path,profile):
    args=bundle('candidate',{'server.conf':b'invented-only'})
    assert bootstrap.materialize('candidate',*args,root=tmp_path)['materialized']
    target=tmp_path/'server.conf'; assert target.stat().st_mode&0o777==0o600
    assert tmp_path.stat().st_mode&0o777==0o700
    assert bootstrap.materialize('candidate',*args,root=tmp_path)['file_count']==1

@pytest.mark.parametrize('mutation',['hash','population','profile'])
def test_reviewed_bundle_denials(tmp_path,profile,mutation):
    args=bundle('candidate' if mutation!='profile' else 'confirmed',{'server.conf':b'invented'} if mutation!='population' else {'issuer.key':b'never'})
    if mutation=='hash':args=(args[0],'0'*64)
    with pytest.raises(PermissionError):bootstrap.materialize('candidate',*args,root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_symlink_denied_before_writes(tmp_path,profile):
    (tmp_path/'server.conf').symlink_to(tmp_path/'target')
    with pytest.raises(PermissionError):bootstrap.materialize('candidate',*bundle('candidate',{'server.conf':b'invented'}),root=tmp_path)
    assert not (tmp_path/'target').exists()


def test_foreign_or_changed_files_rejected(tmp_path,profile):
    (tmp_path/'server.conf').write_bytes(b'previous-preserved')
    with pytest.raises(PermissionError):bootstrap.materialize('candidate',*bundle('candidate',{'server.conf':b'invented'}),root=tmp_path)
    assert (tmp_path/'server.conf').read_bytes()==b'previous-preserved'


def test_duplicated_bundle_fields_denied(tmp_path,profile):
    raw=b'{"schema":"oracle-hosted-files/v1","schema":"oracle-hosted-files/v1","profile":"candidate","files":{}}'
    with pytest.raises(PermissionError):bootstrap.materialize('candidate',base64.b64encode(raw).decode(),hashlib.sha256(raw).hexdigest(),root=tmp_path)
    assert not list(tmp_path.iterdir())


def test_stage_failure_cannot_publish_partial_runtime_file(tmp_path,profile,monkeypatch):
    monkeypatch.setattr(bootstrap.os,'link',lambda *a,**k:(_ for _ in ()).throw(OSError('invented interruption')))
    with pytest.raises(OSError):bootstrap.materialize('candidate',*bundle('candidate',{'server.conf':b'invented'}),root=tmp_path)
    assert not (tmp_path/'server.conf').exists()
    # Retained staged evidence forces a refused retry, not an overwrite.
    with pytest.raises(PermissionError):bootstrap.materialize('candidate',*bundle('candidate',{'server.conf':b'invented'}),root=tmp_path)


def test_ledger_init_fixed_source_sql_only(tmp_path,monkeypatch):
    from pathlib import Path
    from test_hosting_synthetic_fixture import parameters
    monkeypatch.setitem(bootstrap.FILES,'ledger-init',({'seed-parameters.json'},os.getuid()))
    monkeypatch.setattr(bootstrap,'SQL_ROOT',Path(__file__).resolve().parents[1]/'sql')
    result=bootstrap.materialize('ledger-init',*bundle('ledger-init',{'seed-parameters.json':json.dumps(parameters()).encode()}),root=tmp_path)
    names=sorted(p.name for p in tmp_path.iterdir())
    assert names[0]=='00-empty-owned-preflight.sql' and names[-1]=='90-public-invented-seed.sql'
    assert result['file_count']==9 and 'seed-parameters.json' not in names
    assert 'new empty owned synthetic ledger required' in (tmp_path/names[0]).read_text()
    assert all(p.stat().st_mode&0o777==0o600 for p in tmp_path.iterdir())

@pytest.mark.parametrize('profile',['candidate-data','confirmed-data'])
def test_fixed_store_data_is_empty_owned_volume(tmp_path,monkeypatch,profile):
    monkeypatch.setitem(bootstrap.FILES,profile,(set(),os.getuid()))
    result=bootstrap.materialize(profile,*bundle(profile,{}),root=tmp_path)
    assert result['file_count']==0
    assert tmp_path.stat().st_mode&0o777==0o700
    (tmp_path/'foreign').write_bytes(b'preserved')
    with pytest.raises(PermissionError):bootstrap.materialize(profile,*bundle(profile,{}),root=tmp_path)
    assert (tmp_path/'foreign').read_bytes()==b'preserved'
