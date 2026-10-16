"""Closed test orchestration only; no synthetic object is runtime authority."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json,time
from threading import Barrier,Lock
import pytest
from purpose_journey_fixture_delivery import _assert_readonly_delivery_resources,_observe_fixture_tasks,run_readonly_delivery_fixture_tasks


def resources():
    base=dict(principal='executor-human',runtime='executor-runtime',login='executor-login',profile='documentary-executor',observer_path=None,
        config_sha256='a'*64,appointment_sha256='b'*64,config_path='/same/config',appointment_path='/same/appointment')
    direct=base|{k:i+1 for i,k in enumerate(('settings_object','resolver_object','ledger_object','guard_object','semantic_object','blobs_object'))}
    result=base|{k:i+20 for i,k in enumerate(('settings_object','resolver_object','ledger_object','guard_object','semantic_object','blobs_object'))}
    return dict(compiler_restart=dict(principal='compiler',runtime='compiler-runtime',login='compiler-login',profile='candidate-compiler',observer_path='/compiler/state'),executor_answer=direct,result_rpc=result)


def test_closed_readonly_identity_map_allows_same_actor_only_separate_objects():
    _assert_readonly_delivery_resources(resources())

@pytest.mark.parametrize('change',['key','compiler-login','executor-login','config','appointment','observer','settings_object','resolver_object','ledger_object','guard_object','semantic_object','blobs_object'])
def test_readonly_delivery_collisions_are_refused(change):
    r=resources()
    if change=='key':r['unknown']=r.pop('result_rpc')
    elif change=='compiler-login':r['compiler_restart']['login']=r['executor_answer']['login']
    elif change=='executor-login':r['result_rpc']['login']='different-unadmitted-login'
    elif change=='config':r['result_rpc']['config_sha256']='different'
    elif change=='appointment':r['result_rpc']['appointment_path']='/different'
    elif change=='observer':r['result_rpc']['observer_path']='/compiler/state'
    else:r['result_rpc'][change]=r['executor_answer'][change]
    with pytest.raises(AssertionError):_assert_readonly_delivery_resources(r)


def test_three_real_tasks_overlap_and_negative_barrier_waits_for_all(tmp_path):
    barrier=Barrier(3);done=[];lock=Lock()
    def task(name):
        barrier.wait(timeout=1);time.sleep(.015)
        with lock:done.append(name)
        return name
    names=('compiler_restart','executor_answer','result_rpc');path=tmp_path/'intervals.json'
    result=_observe_fixture_tasks({n:lambda n=n:task(n) for n in names},deadline=datetime.now(timezone.utc)+timedelta(seconds=2),identities=resources(),record=path)
    assert set(done)==set(names) and set(result)==set(names)
    done.append('negative-after-join');assert done[-1]=='negative-after-join'
    record=json.loads(path.read_text());assert record['all_tasks_observed'] and not record['errors']
    assert max(v['started'] for v in record['intervals'].values())<min(v['finished'] for v in record['intervals'].values())


def test_one_failure_still_observes_all_three_actual_tasks(tmp_path):
    done=[]
    def fail():done.append('failed');raise RuntimeError('invented fixture failure')
    def finish():time.sleep(.02);done.append('finished')
    with pytest.raises(RuntimeError):_observe_fixture_tasks(dict(compiler_restart=fail,executor_answer=finish,result_rpc=finish),deadline=datetime.now(timezone.utc)+timedelta(seconds=2),identities=resources(),record=tmp_path/'failure.json')
    assert done.count('finished')==2
    assert json.loads((tmp_path/'failure.json').read_text())['all_tasks_observed']


def test_elapsed_original_deadline_observes_tasks_but_refuses_successor(tmp_path):
    completed=[]
    def late():time.sleep(.025);completed.append(True)
    with pytest.raises(TimeoutError):_observe_fixture_tasks({k:late for k in resources()},deadline=datetime.now(timezone.utc)+timedelta(milliseconds=5),identities=resources(),record=tmp_path/'late.json')
    assert len(completed)==3 and json.loads((tmp_path/'late.json').read_text())['all_tasks_observed']


def test_closed_public_wrapper_rejects_fake_settings_before_tasks(tmp_path):
    with pytest.raises(AssertionError,match='exact actual'):
        run_readonly_delivery_fixture_tasks({},deadline=datetime.now(timezone.utc)+timedelta(seconds=1),compiler=object(),direct=object(),result=object(),record=tmp_path/'none')
