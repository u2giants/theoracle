from pathlib import Path
from test_operating_model_sdk import compiler_model
from oracle_brain.operating_model.process_analysis.pm4py_adapter import analyze
from oracle_brain.operating_model.process_analysis.runtime import run_bounded

def test_pm4py_not_bundled_before_qualification():
    root=Path(__file__).resolve().parents[3]
    for file in ('services/oracle-brain/pyproject.toml','apps/workers/oracle2-requirements.txt'):
        assert 'pm4py' not in (root/file).read_text().lower()
    assert analyze(compiler_model(),qualification=None)['state']=='unavailable'

def test_resource_runner_denies_without_exact_runtime_fit():
    model=compiler_model()
    result=run_bounded(model,operation='structural',qualification={'version':'2.7.22','deployment_fit':'APPROVE','review_report_hash':'a'*64})
    assert result['state']=='unavailable' and result['model']==model.model_dump(mode='json')
