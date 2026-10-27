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
        '012_processing_compiler_capabilities.sql','013_processing_purpose_permissions.sql',
        '014_replacement_source_custody.sql','017_processing_model_history.sql','018_original_review_reading_input.sql','019_employee_conversations.sql','020_meeting_capture.sql','021_meeting_participation.sql','022_consolidated_answer_delivery.sql','023_maintained_research.sql','024_question_effects.sql','025_recommendation_actions.sql','026_operational_recovery.sql','027_legacy_migration.sql')



def test_parallel_population_is_exact_bounded_and_heavy_native_suites_are_isolated():
    for stage in ('W10','W12','all','documentary','W04'):
        groups=verifier.test_groups(stage)
        assert tuple(s for _,values in groups for s in values)==verifier.required_suites(stage)
        assert len({s for _,values in groups for s in values})==len(verifier.required_suites(stage))
        assert len(groups)==(10 if stage in ('W10','W12','all') else 8 if stage=='documentary' else 2 if stage in ('event','W04') else 1)
        assert all(values for _,values in groups)
        if stage!='W04':
            # R7 registration: purpose_coherent_native_journey / native_trigger_v1
            # no longer own singleton groups; original/raw families replaced them.
            for heavy in ('purpose_worker_startup',):
                matching=[values for _,values in groups if heavy in values]
                if matching:assert len(matching)==1
            for start in ('original_corpus_import','raw_endpoint_inventory_v1'):
                assert any(values and values[0]==start for _,values in groups)


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
    expected|={p.stem.removeprefix('test_') for p in Path(__file__).parent.glob('test_paid_*.py')}
    expected|={'parent_observer_v2','semantic_registry_v3','processing_extraction_runtime_v2','extraction_connection_authority'}
    assert expected==set(verifier.PURPOSE_V2_SUITES)
    assert all(Counter(suites)[name]==1 for name in expected)
    assert set(verifier.PURPOSE_V2_SUITES)-{'purpose_worker_startup'}<=set(verifier.required_suites('documentary'))
    assert verifier.SYNTHETIC_MIGRATIONS[-12:]==('014_replacement_source_custody.sql','017_processing_model_history.sql','018_original_review_reading_input.sql','019_employee_conversations.sql','020_meeting_capture.sql','021_meeting_participation.sql','022_consolidated_answer_delivery.sql','023_maintained_research.sql','024_question_effects.sql','025_recommendation_actions.sql','026_operational_recovery.sql','027_legacy_migration.sql')



@pytest.mark.parametrize('damage',['foreign-project','foreign-service','foreign-network','public-port','no-label'])
def test_worker_cluster_rejects_foreign_target_before_tls_and_cleans_only_owned_project(tmp_path,monkeypatch,damage):
    import json
    from dev.oracle2 import test_worker_postgres_fixture as helper
    calls=[];chosen={}
    def run(*args,env=None):
        calls.append(args)
        if args[:3]==('docker','ps','-aq'):return ''
        if 'up' in args:chosen['project']=env['COMPOSE_PROJECT_NAME'];return ''
        if 'ps' in args:return 'a'*64
        if args[:2]==('docker','inspect'):
            project=chosen['project']
            labels={'com.docker.compose.project':project,'com.docker.compose.service':'postgres','oracle.operating.synthetic':'true'}
            networks={project+'_default':{}}
            if damage=='foreign-project':labels['com.docker.compose.project']='foreign'
            if damage=='foreign-service':labels['com.docker.compose.service']='foreign'
            if damage=='foreign-network':networks={'foreign':{}}
            if damage=='no-label':labels.pop('oracle.operating.synthetic')
            return json.dumps([{'Config':{'Labels':labels},'NetworkSettings':{'Ports':{'5432/tcp':[{'HostIp':'0.0.0.0' if damage=='public-port' else '127.0.0.1','HostPort':'61234'}]},'Networks':networks}}])
        return ''
    monkeypatch.setattr(helper,'run',run)
    monkeypatch.setattr(helper,'bootstrap',lambda *args:pytest.fail('foreign target reached TLS/write'))
    with pytest.raises(PermissionError):
        with helper.worker_postgres({'COMPOSE_PROJECT_NAME':'oracle2-synthetic-unit'},tmp_path/'cluster','documentary-01'):pass
    cleanup=calls[-1]
    assert cleanup[-2:]==('down','--volumes')
    assert cleanup[cleanup.index('-p')+1]==chosen['project']
    assert chosen['project']!='oracle2-synthetic-unit'


def test_worker_cluster_existing_project_refuses_before_any_mutation(tmp_path,monkeypatch):
    from dev.oracle2 import test_worker_postgres_fixture as helper
    calls=[]
    def run(*args,**kwargs):calls.append(args);return 'existing'
    monkeypatch.setattr(helper,'run',run)
    with pytest.raises(PermissionError,match='fresh empty'):
        with helper.worker_postgres({'COMPOSE_PROJECT_NAME':'oracle2-synthetic-unit'},tmp_path/'cluster','event'):pass
    assert len(calls)==1 and calls[0][:3]==('docker','ps','-aq')
    assert not (tmp_path/'cluster').exists()


def test_protected_raw_factory_and_actual_reviewer_input_are_mandatory_once():
    from collections import Counter
    import ast
    names={'protected_raw_original_factory_v1','protected_raw_original_factory_sql','original_review_reading_input_sql'}
    for stage in ('W10','W12','documentary'):
        counts=Counter(verifier.required_suites(stage))
        assert all(counts[name]==1 for name in names)
    phase=ast.parse((Path(__file__).parents[3]/'scripts/oracle2/verify_phase.py').read_text())
    suites=next(ast.literal_eval(n.value) for n in phase.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='S03_TESTS' for t in n.targets))
    assert all(suites.count('test_'+name+'.py')==1 for name in names)


@pytest.mark.parametrize(('body', 'exit_code', 'skipped', 'failures'), [
    ('def test_actual(): assert True\n', 0, 0, 0),
    ('import pytest\ndef test_actual(): pytest.skip("missing capability")\n', 1, 1, 0),
    ('def test_actual(): assert False\n', 1, 0, 1),
    ('import pytest\n@pytest.fixture\ndef broken(): raise RuntimeError("setup failed")\ndef test_actual(broken): pass\n', 1, 0, 1),
])
def test_phase_gate_checks_actual_case_evidence_not_only_pytest_exit(tmp_path, body, exit_code, skipped, failures):
    import sys
    from scripts.oracle2.verify_phase import run_phase_tests
    test = tmp_path / 'test_actual_phase.py'
    test.write_text(body)
    code, evidence, _ = run_phase_tests(Path(sys.executable), [str(test)])
    assert bool(code) == bool(exit_code)
    assert evidence['tests'] == 1
    assert evidence['skipped'] == skipped
    assert evidence['failures'] == failures
    assert bool(evidence['evidence_errors']) == bool(exit_code)
    assert evidence['worker_results'][0]['junit_present']
    assert evidence['worker_results'][0]['junit_sha256']
    if skipped:
        assert evidence['worker_results'][0]['exit_code'] == 0


def test_actual_python_web_peer_conformance_is_mandatory_not_a_skipped_browser_placeholder():
    from scripts.oracle2.verify_phase import S03_TESTS
    assert verifier.required_suites('W10').count('protected_web_python_conformance_v1') == 1
    assert S03_TESTS.count('test_protected_web_python_conformance_v1.py') == 1


def test_canonical_consolidation_is_required_once_with_017_before_018():
    from scripts.oracle2.verify_phase import S03_TESTS, S05_TESTS
    for name in ('consolidation_contracts_v1', 'consolidation_sql_v1','consolidation_review_v1','consolidation_review_browser_v1'):
        assert verifier.required_suites('W10').count(name) == 1
        assert S03_TESTS.count('test_' + name + '.py') == 1
        assert S05_TESTS.count('test_' + name + '.py') == 1
    assert verifier.SYNTHETIC_MIGRATIONS.count('017_processing_model_history.sql') == 1
    assert verifier.SYNTHETIC_MIGRATIONS.count('018_original_review_reading_input.sql') == 1
    assert verifier.SYNTHETIC_MIGRATIONS.count('019_employee_conversations.sql') == 1
    start=verifier.SYNTHETIC_MIGRATIONS.index('017_processing_model_history.sql')
    assert verifier.SYNTHETIC_MIGRATIONS[start:start+3] == ('017_processing_model_history.sql', '018_original_review_reading_input.sql', '019_employee_conversations.sql')


def test_phase_frontdoor_needs_no_worker_database_or_process_dependencies(tmp_path):
    import subprocess
    import sys
    case = tmp_path / 'test_locked_runtime.py'
    case.write_text('def test_actual(): assert True\n')
    wrapper = """import builtins,runpy,sys
from pathlib import Path
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.split('.')[0] in ('psutil','psycopg'):
        raise AssertionError('phase frontdoor imported worker-only dependencies')
    return original(name,*args,**kwargs)
builtins.__import__=guarded
phase=runpy.run_path(sys.argv[1])
code,evidence,_=phase['run_phase_tests'](Path(sys.argv[2]),[sys.argv[3]])
assert code==0 and evidence['tests']==1 and evidence['failures']==evidence['skipped']==0
"""
    result = subprocess.run([sys.executable, '-I', '-c', wrapper,
        str(Path(__file__).parents[3] / 'scripts/oracle2/verify_phase.py'),
        sys.executable, str(case)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_original_browser_upload_is_required_with_browser_install_before_w10():
    from scripts.oracle2.verify_phase import S03_TESTS, S04_TESTS
    for name in ('original_upload_chunks_v1','original_upload_browser_v1'):
        assert verifier.required_suites('W10').count(name)==1
        assert S03_TESTS.count('test_'+name+'.py')==1
        assert S04_TESTS.count('test_'+name+'.py')==1
    workflow=(Path(__file__).parents[3]/'.github/workflows/oracle2-contracts.yml').read_text()
    assert workflow.count('run: pnpm --filter @oracle/web exec playwright install chromium')==1
    assert workflow.index('name: Install browser for synthetic connected-document proof') < workflow.index('name: New operating-model documentary and event contracts')


def test_s08_participation_suites_are_registered_once_in_w10_and_phase():
    from scripts.oracle2.verify_phase import S08_TESTS
    from scripts.oracle2.verify_workflow_integrity import (
        MEETING_PARTICIPATION_CORE_SUITES,
        MEETING_PARTICIPATION_EVENT_SUITES,
    )
    for name in MEETING_PARTICIPATION_CORE_SUITES:
        assert verifier.required_suites('W10').count(name) == 1
        assert name in verifier.DOCUMENTARY or name in verifier.EVENT
        assert S08_TESTS.count('test_' + name + '.py') == 1
    for name in MEETING_PARTICIPATION_EVENT_SUITES:
        assert verifier.required_suites('W10').count(name) == 1
        assert name in verifier.DOCUMENTARY or name in verifier.EVENT
        assert S08_TESTS.count('test_' + name + '.py') == 1
    assert len(S08_TESTS) == 6
    assert S08_TESTS.count('test_meeting_participation.py') == 1



def test_recorded_source_inventory_binds_shared_evidence_and_phase_frontdoor_bytes(tmp_path,monkeypatch):
    import subprocess
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    names=('scripts/oracle2/contract_test_evidence.py','scripts/oracle2/verify_phase.py','dev/oracle2/test_canonical_schema.py')
    for name in names:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('invented initial source\n')
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    first=verifier.source_input_hashes()
    assert set(first)==set(names)
    for index,name in enumerate(names):
        before=verifier.source_input_hashes()
        (tmp_path/name).write_text('invented changed source '+str(index)+'\n')
        after=verifier.source_input_hashes()
        assert before[name]!=after[name]
        assert all(before[other]==after[other] for other in names if other!=name)


def test_actual_web_identity_and_framework_source_are_in_recorded_execution_inventory(tmp_path,monkeypatch):
    import subprocess
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    names=('apps/web/app/api/consultant/replacement/v1/protected/model-review/route.ts',
        'apps/web/lib/replacement-protected-client.ts','apps/web/proxy.ts',
        'apps/web/tests/oracle2/model-review-next-auth-proof.ts',
        'packages/db/src/schema.ts','packages/auth/src/index.ts',
        'packages/shared/src/protected-node-https.ts','pnpm-lock.yaml')
    for name in names:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'invented executed source')
    private=tmp_path/'apps/web/lib/.env.local';private.write_bytes(b'invented excluded private fixture')
    cache=tmp_path/'apps/web/.next/cache';cache.parent.mkdir(parents=True);cache.write_bytes(b'invented cache')
    monkeypatch.setattr(verifier,'ROOT',tmp_path)
    before=verifier.source_input_hashes()
    assert set(before)==set(names)
    (tmp_path/'apps/web/lib/replacement-protected-client.ts').write_bytes(b'changed actual executed peer')
    assert before!=verifier.source_input_hashes()


def test_new_database_browser_and_native_families_use_distinct_existing_worker_capacity():
    groups=dict(verifier.test_groups('W10'))
    assert set(verifier.CONSOLIDATION_SUITES)-{'consolidation_next_auth_browser_v1'}<=set(groups['documentary-01'])
    assert 'consolidation_next_auth_browser_v1' in groups['documentary-07']
    assert sum(suites.count('consolidation_next_auth_browser_v1') for suites in groups.values())==1
    assert {'protected_raw_original_factory_sql','original_review_reading_input_sql'}<=set(groups['documentary-04'])
    assert 'protected_raw_original_factory_v1' in groups['documentary-06']
    assert 'qualified_workspace_sdk_sql_v1' in groups['documentary-03']
    assert 'question_effect_native_sql_v1' in groups['documentary-04']
    assert 'question_effects_sql_v1' in groups['documentary-07']
    assert 'consolidation_sql_v1' in groups['documentary-01']
    assert 'purpose_coherent_native_journey' in groups['documentary-06']
    assert 'conversation_native_sql' in groups['documentary-03']
    assert 'conversation_native_sql' not in groups['documentary-08']
    assert 'purpose_coherent_native_journey' not in groups['documentary-08']
    for population,selected,anchor in ((('a','a','b'),('a',),'b'),
        (('a','b'),('missing',),'b'),(('a','b'),('a',),'a')):
        with pytest.raises(RuntimeError):
            verifier._place_suites(population,selected,anchor)


def test_current_capture_migration_source_and_actual_SQL_are_mandatory_once():
    expected=('legacy_snapshot_v1','legacy_export_contract_v1','legacy_storage_capture_v1',
        'legacy_s3_signing_v1','legacy_migration_factory_v1','legacy_migration_sql','legacy_migration_citation_sql')
    assert verifier.MIGRATION_CURRENT_CAPTURE_SUITES==expected
    suites=verifier.required_suites('W10')
    assert all(suites.count(name)==1 for name in expected)
    assert all((Path(__file__).parent/f'test_{name}.py').is_file() for name in expected)
    assert verifier.SYNTHETIC_MIGRATIONS.count('027_legacy_migration.sql')==1
    assert verifier.SYNTHETIC_MIGRATIONS[-1]=='027_legacy_migration.sql'
    assert (verifier.ROOT/'services/oracle-brain/sql/027_legacy_migration.sql').is_file()
    assert len(verifier.test_groups('W10'))==10


def test_current_capture_migration_uses_existing_workers_and_actual_S14_admission():
    import runpy
    phase=runpy.run_path(str(verifier.ROOT/'scripts/oracle2/verify_phase.py'))
    assert phase['FIXTURE_ONLY_PHASES']=={'S12','S16'}
    assert {f'test_{name}.py' for name in verifier.MIGRATION_CURRENT_CAPTURE_SUITES}<=set(phase['S14_TESTS'])
    assert len(phase['S14_TESTS'])==11
    groups=dict(verifier.test_groups('W10'))
    assert set(verifier.MIGRATION_CURRENT_CAPTURE_SUITES)-{'legacy_migration_sql','legacy_migration_citation_sql'}<=set(groups['documentary-01'])
    assert 'legacy_migration_sql' in groups['documentary-03']
    assert 'legacy_migration_citation_sql' in groups['documentary-08']


def test_actual_S14_gate_refuses_absent_store_before_any_success_receipt(tmp_path):
    import os,subprocess,sys
    environment={key:value for key,value in os.environ.items() if key not in ('ORACLE2_TEST_ADMIN_URL','ORACLE2_TEST_CONFIRMED_URL')}
    result=tmp_path/'result.json'
    completed=subprocess.run([sys.executable,str(verifier.ROOT/'scripts/oracle2/verify_phase.py'),'S14','--mode','offline','--result',str(result)],
        env=environment,capture_output=True,text=True,timeout=10,check=False)
    assert completed.returncode==2
    assert 'real isolated Postgres and FalkorDB test URLs required' in completed.stderr
    assert not result.exists()
