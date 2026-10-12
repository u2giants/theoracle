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
