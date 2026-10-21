from pathlib import Path
import subprocess
import sys

import pytest

from test_operating_model_sdk import compiler_model
from oracle_brain.operating_model.process_analysis.pm4py_adapter import analyze
from oracle_brain.operating_model.process_analysis.runtime import run_bounded

def test_pm4py_not_bundled_before_qualification():
    root=Path(__file__).resolve().parents[3]
    import tomllib
    declaration=tomllib.loads((root/'services/oracle-brain/pyproject.toml').read_text())
    assert all('pm4py' not in item.lower() for item in declaration['project']['dependencies'])
    assert declaration['project']['optional-dependencies']['process-analysis']==['pm4py==2.7.22']
    assert 'pm4py' not in (root/'apps/workers/oracle2-requirements.txt').read_text().lower()
    assert analyze(compiler_model(),qualification=None)['state']=='unavailable'

def test_resource_runner_denies_without_exact_runtime_fit():
    model=compiler_model()
    result=run_bounded(model,operation='structural',qualification={'version':'2.7.22','deployment_fit':'APPROVE','review_report_hash':'a'*64})
    assert result['state']=='unavailable' and result['model']==model.model_dump(mode='json')

import time
from oracle_brain.operating_model.process_analysis.runtime import _execute_bounded

ORIGINAL={'workflow_id':'synthetic','steps':['preserved'],'state':'ready'}


def _assert_descendant_terminated(pid):
    """Assert that a descendant is gone or in a terminal process state."""
    status = Path(f'/proc/{pid}/stat')
    try:
        stat = status.read_text()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise AssertionError(f'could not read process status for {pid}') from exc

    closing_paren = stat.rfind(')')
    assert closing_paren >= 0, f'malformed process status for {pid}'
    suffix = stat[closing_paren + 1:]
    fields = suffix.split()
    assert suffix[:1].isspace() and len(fields) >= 3, (
        f'malformed process status for {pid}'
    )
    assert fields[0] in {'Z', 'X'}, (
        f'process {pid} is not terminal: {fields[0] if fields else "missing state"}'
    )

def sleeping_worker(*args):
    import time
    time.sleep(3)

def exhausted_worker(*args):
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    bytearray(1024*1024*1024)

def test_bounded_worker_timeout_preserves_original_and_terminates_child():
    started=time.monotonic(); result=_execute_bounded(ORIGINAL,sleeping_worker,(),.1); elapsed=time.monotonic()-started
    assert result['state']=='incomplete' and 'timeout' in result['reason'].lower() and result['model']==ORIGINAL and elapsed<3

def test_bounded_worker_memory_exhaustion_preserves_original_and_returns():
    result=_execute_bounded(ORIGINAL,exhausted_worker,(),1)
    assert result['state']=='incomplete' and 'exhaustion' in result['reason'].lower() and result['model']==ORIGINAL


def native_child_worker(pid_file,output):
    import subprocess,sys,time
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
    Path(pid_file).write_text(str(child.pid))
    time.sleep(60)

def test_timeout_cancels_native_solver_descendant(tmp_path):
    pid_file=tmp_path/'native.pid'
    result=_execute_bounded(ORIGINAL,native_child_worker,(str(pid_file),),1)
    assert result['state']=='incomplete' and result['model']==ORIGINAL
    assert pid_file.exists()
    pid=int(pid_file.read_text())
    _assert_descendant_terminated(pid)


@pytest.mark.parametrize('stat', [
    '42 (worker) Z 1 2 3',
    '42 (worker with (parentheses)) X 1 2 3',
])
def test_descendant_termination_assertion_accepts_terminal_states(monkeypatch, stat):
    monkeypatch.setattr(Path, 'read_text', lambda self: stat)
    _assert_descendant_terminated(42)


def test_descendant_termination_assertion_accepts_disappearance(monkeypatch):
    def gone(self):
        raise FileNotFoundError

    monkeypatch.setattr(Path, 'read_text', gone)
    _assert_descendant_terminated(42)


@pytest.mark.parametrize('state', ['R', 'S', 'D', 'T', 'I', 't', '?'])
def test_descendant_termination_assertion_rejects_live_states(monkeypatch, state):
    monkeypatch.setattr(Path, 'read_text', lambda self: f'42 (worker) {state} 1 2 3')
    with pytest.raises(AssertionError):
        _assert_descendant_terminated(42)


@pytest.mark.parametrize('stat', ['', '42 worker S 1 2 3', '42 (worker)', '42 (worker) Z'])
def test_descendant_termination_assertion_rejects_malformed_status(monkeypatch, stat):
    monkeypatch.setattr(Path, 'read_text', lambda self: stat)
    with pytest.raises(AssertionError):
        _assert_descendant_terminated(42)


def test_descendant_termination_assertion_rejects_unreadable_status(monkeypatch):
    def denied(self):
        raise PermissionError

    monkeypatch.setattr(Path, 'read_text', denied)
    with pytest.raises(AssertionError):
        _assert_descendant_terminated(42)


def test_descendant_termination_assertion_rejects_real_live_subprocess():
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        with pytest.raises(AssertionError):
            _assert_descendant_terminated(process.pid)
    finally:
        process.terminate()
        process.wait(timeout=5)
