"""Source-only failure proofs; no Docker, SQL or network is invoked."""
import json,stat,subprocess
from unittest.mock import patch
import pytest
from dev.oracle2 import test_worker_postgres_fixture as owner

BASE='oracle2-synthetic-intent-proof'
CONTAINER='a'*64

def retained(directory):
    path=directory/'startup-intent.json'
    value=json.loads(path.read_bytes())
    assert set(value)=={'project','worker','synthetic_only'}
    assert value['project'].startswith(BASE+'-w') and len(value['project'])==len(BASE)+14
    assert value['worker']=='documentary-01' and value['synthetic_only'] is True
    assert stat.S_IMODE(path.stat().st_mode)==0o600
    assert stat.S_IMODE(directory.stat().st_mode)==0o700
    return value,path.read_bytes()

def fixture_run(directory,calls,fail=None):
    def run(*args,env=None):
        calls.append(args)
        if args[:3]==('docker','ps','-aq'):return ''
        if 'up' in args:
            value,_=retained(directory)
            assert args[args.index('-p')+1]==value['project']
            if fail=='up':raise subprocess.CalledProcessError(1,args)
            return ''
        if 'down' in args:
            retained(directory)
            if fail=='down':raise subprocess.CalledProcessError(1,args)
            return ''
        if 'ps' in args:return CONTAINER
        if args[:2]==('docker','inspect'):
            project=retained(directory)[0]['project']
            return json.dumps([{'Config':{'Labels':{'com.docker.compose.project':project,'com.docker.compose.service':'postgres','oracle.operating.synthetic':'true'}},'NetworkSettings':{'Networks':{project+'_default':{}},'Ports':{'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'12345'}]}}}])
        raise AssertionError(args)
    return run

@pytest.mark.parametrize('failure',['up','bootstrap'])
def test_startup_failure_retains_pre_effect_owner_and_attempts_exact_cleanup(tmp_path,failure):
    directory=tmp_path/'worker';calls=[]
    def bootstrap(*args):
        retained(directory)
        raise RuntimeError('invented bootstrap failure')
    with patch.object(owner,'run',fixture_run(directory,calls,failure)),patch.object(owner,'bootstrap',bootstrap):
        with pytest.raises((subprocess.CalledProcessError,RuntimeError)):
            with owner.worker_postgres({'COMPOSE_PROJECT_NAME':BASE},directory,'documentary-01'):
                raise AssertionError('startup must not yield')
    value,raw=retained(directory)
    downs=[c for c in calls if 'down' in c]
    assert len(downs)==1 and downs[0][downs[0].index('-p')+1]==value['project']
    assert raw==json.dumps(value,sort_keys=True).encode()+b'\n'

@pytest.mark.parametrize('failed_operation',['open','fsync'])
def test_intent_write_failure_prevents_all_compose_effects(tmp_path,failed_operation):
    calls=[];directory=tmp_path/'worker'
    with patch.object(owner,'run',fixture_run(directory,calls)),patch.object(owner.os,failed_operation,side_effect=OSError('invented receipt write failure')):
        with pytest.raises(OSError,match='receipt write failure'):
            with owner.worker_postgres({'COMPOSE_PROJECT_NAME':BASE},directory,'documentary-01'):
                raise AssertionError('write failure must not yield')
    assert not any('up' in c or 'down' in c for c in calls)

def test_success_retains_same_receipt_bytes_after_owned_cleanup(tmp_path):
    calls=[];directory=tmp_path/'worker'
    with patch.object(owner,'run',fixture_run(directory,calls)),patch.object(owner,'bootstrap',return_value={'fixture':'invented'}):
        with owner.worker_postgres({'COMPOSE_PROJECT_NAME':BASE},directory,'documentary-01') as (_,identity):
            value,raw=retained(directory)
            assert value['project']==identity['project']
        assert retained(directory)[1]==raw
    assert sum('down' in c for c in calls)==1

def test_cleanup_failure_propagates_and_retains_owner_without_absence_claim(tmp_path):
    calls=[];directory=tmp_path/'worker'
    with patch.object(owner,'run',fixture_run(directory,calls,'down')),patch.object(owner,'bootstrap',return_value={}):
        with pytest.raises(subprocess.CalledProcessError):
            with owner.worker_postgres({'COMPOSE_PROJECT_NAME':BASE},directory,'documentary-01'):pass
    retained(directory)
    assert sum('down' in c for c in calls)==1

def test_reader_missing_intent_is_unknown_not_empty_inventory(tmp_path):
    directory=tmp_path/'worker';directory.mkdir(mode=0o700)
    with pytest.raises(FileNotFoundError):owner.worker_startup_intent(directory,BASE,'documentary-01')

@pytest.mark.parametrize('change',['project','worker','boolean','extra','duplicate','mode','symlink'])
def test_reader_refuses_unowned_or_changed_evidence(tmp_path,change):
    directory=tmp_path/'worker';calls=[]
    with patch.object(owner,'run',fixture_run(directory,calls,'up')):
        with pytest.raises(subprocess.CalledProcessError):
            with owner.worker_postgres({'COMPOSE_PROJECT_NAME':BASE},directory,'documentary-01'):pass
    path=directory/'startup-intent.json';value,raw=retained(directory)
    assert owner.worker_startup_intent(directory,BASE,'documentary-01')==value
    if change=='project':value['project']='oracle2-synthetic-foreign-w'+'a'*12
    elif change=='worker':value['worker']='event'
    elif change=='boolean':value['synthetic_only']=1
    elif change=='extra':value['extra']='not admitted'
    if change in ('project','worker','boolean','extra'):path.write_text(json.dumps(value,sort_keys=True)+'\n')
    elif change=='duplicate':path.write_bytes(raw[:-2]+b',"synthetic_only":true}\n')
    elif change=='mode':path.chmod(0o644)
    elif change=='symlink':
        other=directory/'other';path.rename(other);path.symlink_to(other)
    with pytest.raises((PermissionError,ValueError)):owner.worker_startup_intent(directory,BASE,'documentary-01')
