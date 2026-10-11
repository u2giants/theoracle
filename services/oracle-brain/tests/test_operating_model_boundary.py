"""W01: enforce exact infrastructure allowlist, no legacy business imports."""
import json
from pathlib import Path
from oracle_brain.operating_model.boundary import import_violations

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'services/oracle-brain/oracle_brain/operating_model'
REGISTRY = ROOT / 'docs/verification/oracle2/workflow/boundary-register.json'


def test_new_core_import_boundary():
    helpers = frozenset(json.loads(REGISTRY.read_text())['helper_allowlist'])
    paths = list(CORE.rglob('*.py'))
    assert CORE.is_dir() and paths, 'missing replacement core boundary'
    for path in paths:
        relative = path.relative_to(ROOT / 'services/oracle-brain')
        package = '.'.join(relative.parts[:-1])
        assert not import_violations(path.read_text(), package=package, helper_allowlist=helpers), path
    for text in ('from oracle_brain.graph.graphrag import HolisticGraphPilot',
                 'from ..graph import graphrag', 'from .. import holistic_runtime',
                 'from oracle_brain import graph', 'import oracle_brain.graph',
                 'import oracle_brain.consultant.pilot',
                 '__import__("oracle_brain.graph.graphrag")',
                 'exec("import oracle_brain.graph")',
                 'builtins.exec("import oracle_brain.graph")',
                 'builtins.eval("1")',
                 'from importlib import import_module; import_module("oracle_brain.graph")',
                 'from builtins import exec as run; run("import oracle_brain.graph")',
                 'from ... import x', 'invalid python syntax :',
                 'import importlib.machinery', 'import importlib.util',
                 'from importlib.util import spec_from_file_location',
                 'from importlib.machinery import SourceFileLoader',
                 'import runpy', 'import pkgutil', 'import sys',
                 '__loader__.exec_module(__spec__)',
                 'importlib.import_module("oracle_brain.retrieval.pilot")'):
        assert import_violations(text, package='oracle_brain.operating_model', helper_allowlist=helpers), text
    assert not import_violations('from ..provider_policy import authorize',package='oracle_brain.operating_model',helper_allowlist=helpers)
    assert import_violations('from ..config import Settings',package='oracle_brain.operating_model',helper_allowlist=helpers)


def test_retention_contracts_cover_all_live_callers():
    register = json.loads(REGISTRY.read_text())
    assert register['legacy_default'] is False and register['production_activation'] is False
    assert register['new_graph_prefix'] != register['legacy_graph_prefix']
    for record in register['retained']:
        assert record['invariants'] and record['required_tests']
        for path in record['paths']: assert (ROOT / path).is_file(), path
        for test in record['required_tests']:
            assert any((ROOT / base / test).is_file() for base in ('services/oracle-brain/tests','scripts/oracle2')), test
    discovered = set()
    for base in ('apps/web/app/api/consultant', 'apps/workers/src/trigger', 'services/oracle-brain/oracle_brain'):
        for path in (ROOT / base).rglob('*'):
            if path.suffix in ('.py', '.ts') and any(t in path.read_text(errors='strict') for t in ('HolisticGraphPilot', 'oracle2-holistic-answer', 'oracle_brain/holistic_runtime.py')):
                discovered.add(str(path.relative_to(ROOT)))
    assert discovered == set(register['callers'])


def test_retained_helpers_do_not_transitively_import_legacy_business_core():
    register = json.loads(REGISTRY.read_text())
    allowed = frozenset(register['helper_allowlist'] + register['transitive_infrastructure'])
    for module in allowed:
        path = ROOT / 'services/oracle-brain' / (module.replace('.', '/') + '.py')
        assert path.is_file(), module
        denied = import_violations(path.read_text(), package=module.rsplit('.',1)[0], helper_allowlist=allowed)
        # Helpers may use sys for their established parser/runtime identity; this
        # check restricts Oracle dependencies, not their reviewed standard library.
        assert not [name for name in denied if name.startswith('oracle_brain')], (module, denied)
