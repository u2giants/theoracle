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
        '012_processing_compiler_capabilities.sql','013_processing_purpose_permissions.sql')


def test_parallel_population_is_exact_and_single_set_stages_remain_single():
    for stage in ('W10','W12','all','documentary','W04'):
        groups=verifier.test_groups(stage)
        assert tuple(s for _,values in groups for s in values)==verifier.required_suites(stage)
        assert len({s for _,values in groups for s in values})==len(verifier.required_suites(stage))
        assert len(groups)==(2 if stage in ('W10','W12','all') else 1)


def test_all_workers_share_real_deadline_and_preserve_partial_output(tmp_path):
    import os,sys,time
    jobs=[{'name':name,'command':[sys.executable,'-c',"import time;print('started',flush=True);time.sleep(5)"],'env':os.environ.copy()} for name in ('first','second')]
    start=time.monotonic();results,errors=verifier.run_test_groups(jobs,tmp_path,deadline=start+0.20)
    assert time.monotonic()-start<1.5
    assert not errors and all(r['timed_out'] and r['exit_code'] is not None for r in results)
    assert all((tmp_path/(name+'.stdout')).read_text()=='started\n' for name in ('first','second'))
    outcome=verifier.aggregate_evidence(jobs,results,tmp_path)
    assert outcome['exit_code']==1 and outcome['tests']==0
    assert all(r['stdout_sha256'] and not r['junit_present'] for r in outcome['worker_results'])


@pytest.mark.parametrize('damage',('failed','skipped','missing','malformed','partial-worker'))
def test_parallel_evidence_never_launders_partial_or_failed_results(tmp_path,damage):
    jobs=[{'name':n} for n in ('documentary','event')]
    results=[]
    for name in ('documentary','event'):
        (tmp_path/(name+'.stdout')).write_text('actual synthetic output')
        cases='<testcase name="retained"/>'
        if name=='event' and damage in ('failed','skipped'):
            cases='<testcase name="retained"><'+('failure' if damage=='failed' else 'skipped')+'/></testcase>'
        if not (name=='event' and damage=='missing'):
            (tmp_path/(name+'.xml')).write_text('bad' if name=='event' and damage=='malformed' else '<testsuite>'+cases+'</testsuite>')
        results.append({'name':name,'exit_code':1 if name=='event' and damage=='failed' else 0,'timed_out':False})
    if damage=='partial-worker':results.pop()
    outcome=verifier.aggregate_evidence(jobs,results,tmp_path)
    assert outcome['exit_code']==1 and outcome['evidence_errors']


def test_parallel_success_combines_both_actual_junit_populations(tmp_path):
    jobs=[{'name':n} for n in ('documentary','event')];results=[]
    for name in ('documentary','event'):
        (tmp_path/(name+'.stdout')).write_text('retained '+name)
        (tmp_path/(name+'.xml')).write_text('<testsuites><testsuite><testcase name="'+name+'"/></testsuite></testsuites>')
        results.append({'name':name,'exit_code':0,'timed_out':False})
    outcome=verifier.aggregate_evidence(jobs,results,tmp_path)
    assert outcome['exit_code']==0 and outcome['tests']==2 and not outcome['skipped']
    assert len(outcome['worker_results'])==2 and all(r['junit_sha256'] for r in outcome['worker_results'])


def test_timeout_stops_owned_descendant_session_and_preserves_other_process(tmp_path):
    import os,sys,time,subprocess,psutil
    pidfile=tmp_path/'child-pid'
    code=("import subprocess,sys,time,signal;from pathlib import Path;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True);"
        "Path("+repr(str(pidfile))+").write_text(str(child.pid));"
        "signal.signal(signal.SIGTERM,lambda *a:(child.wait(timeout=2),sys.exit(0)));time.sleep(60)")
    outsider=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
    try:
        jobs=[{'name':'owned','command':[sys.executable,'-c',code],'env':os.environ.copy()}]
        results,errors=verifier.run_test_groups(jobs,tmp_path,deadline=time.monotonic()+0.30)
        assert not errors and results[0]['timed_out']
        assert pidfile.is_file() and not psutil.pid_exists(int(pidfile.read_text()))
        assert outsider.poll() is None
    finally:outsider.terminate();outsider.wait(timeout=2)


def test_worker_launch_failure_preserves_earlier_output_and_fails_closed(tmp_path):
    import os,sys,time
    jobs=[{'name':'first','command':[sys.executable,'-c',"print('first')"],'env':os.environ.copy()},
        {'name':'missing','command':[str(tmp_path/'no-such-program')],'env':os.environ.copy()}]
    results,errors=verifier.run_test_groups(jobs,tmp_path,deadline=time.monotonic()+1)
    assert not errors and len(results)==2 and all(r['launch_error'] for r in results)
    outcome=verifier.aggregate_evidence(jobs,results,tmp_path)
    assert outcome['exit_code']==1 and not outcome['worker_results'][1]['junit_present']


def test_cleanup_wrong_target_cannot_terminate_or_drop_database(monkeypatch):
    queries=[]
    class WrongTarget:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,query,*args):queries.append(str(query));return self
        def fetchone(self):return ('unexpected-database',)
    monkeypatch.setattr(verifier.psycopg,'connect',lambda *a,**k:WrongTarget())
    errors=verifier.cleanup_test_databases('invented',{'dbname':'expected'},['oracle_operating_model_test_owned'])
    assert errors==[{'database':'oracle_operating_model_test_owned','reason':'owned database cleanup failed'}]
    assert queries==['SELECT current_database()']


def test_all_current_versioned_purpose_suites_are_required_once_without_new_runner():
    from collections import Counter
    suites=verifier.required_suites('W10')
    expected={p.stem.removeprefix('test_') for p in Path(__file__).parent.glob('test_purpose_*.py')}
    expected|={'parent_observer_v2','semantic_registry_v3','processing_extraction_runtime_v2','extraction_connection_authority','paid_sdk_embeddings_v3'}
    assert expected==set(verifier.PURPOSE_V2_SUITES)
    assert all(Counter(suites)[name]==1 for name in expected)
    assert set(verifier.PURPOSE_V2_SUITES)<=set(verifier.required_suites('documentary'))
    assert verifier.SYNTHETIC_MIGRATIONS[-1]=='013_processing_purpose_permissions.sql'


def test_runtime_transport_custody_and_policy_mutations_change_recorded_inputs(tmp_path,monkeypatch):
    import hashlib,json,subprocess
    subprocess.run(['git','init','--quiet','--template='],cwd=tmp_path,check=True)
    (tmp_path/'.gitignore').write_text('__pycache__/\n*.private\n')
    package=tmp_path/'services/oracle-brain/oracle_brain';hosting=package/'hosting';hosting.mkdir(parents=True)
    paths=[hosting/'purpose_runtime.py',hosting/'purpose_transport.py',hosting/'custody.py',package/'provider_policy.py']
    for p in paths:p.write_text('owned source = 1\n')
    hidden=hosting/'__pycache__';hidden.mkdir();(hidden/'cache.pyc').write_bytes(b'generated')
    (hosting/'fixture.private').write_text('not a source input')
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    def seal():return hashlib.sha256(json.dumps(verifier.source_input_hashes(),sort_keys=True).encode()).hexdigest()
    baseline=verifier.source_input_hashes()
    assert set(baseline)=={str(p.relative_to(tmp_path)) for p in paths}
    original=seal()
    for p in paths:
        p.write_text('owned source = 2\n');assert seal()!=original
        p.write_text('owned source = 1\n');assert seal()==original
    (hidden/'cache.pyc').write_bytes(b'changed cache');(hosting/'fixture.private').write_text('changed private fixture')
    assert seal()==original
