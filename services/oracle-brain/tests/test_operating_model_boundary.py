"""W01 enforcement: legacy business logic cannot enter the replacement."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'services/oracle-brain/oracle_brain/operating_model'
REGISTRY = ROOT / 'docs/verification/oracle2/workflow/boundary-register.json'
FORBIDDEN = ('graph.graphrag', 'graph.retrieval', 'holistic_runtime', 'consultant.pilot',
             'retrieval.pilot', 'workflows.pilot')


def violations(text):
    found = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import): names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or '']
            names += [(node.module or '') + '.' + a.name for a in node.names]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module':
            names = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        else: continue
        for name in names:
            if any(name == f or name.endswith('.' + f) or name.startswith('oracle_brain.' + f) for f in FORBIDDEN):
                found.append(name)
    return found


def test_new_core_import_boundary():
    for path in CORE.rglob('*.py'):
        assert not violations(path.read_text()), path
    for text in ('from oracle_brain.graph.graphrag import HolisticGraphPilot',
                 'from ..graph import graphrag', 'from .. import holistic_runtime',
                 'import oracle_brain.consultant.pilot',
                 'importlib.import_module("oracle_brain.retrieval.pilot")'):
        assert violations(text), text


def test_retention_contracts_cover_all_live_callers():
    register = json.loads(REGISTRY.read_text())
    assert register['legacy_default'] is False
    assert register['production_activation'] is False
    assert register['new_graph_prefix'] != register['legacy_graph_prefix']
    for record in register['retained']:
        assert record['invariants'] and record['required_tests']
        for path in record['paths']: assert (ROOT / path).is_file(), path
    callers = set(register['callers'])
    discovered = set()
    for base in ('apps/web/app/api/consultant', 'apps/workers/src/trigger', 'services/oracle-brain/oracle_brain'):
        for path in (ROOT / base).rglob('*'):
            if path.suffix in ('.py', '.ts') and any(t in path.read_text() for t in ('HolisticGraphPilot', 'oracle2-holistic-answer', 'oracle_brain/holistic_runtime.py')):
                discovered.add(str(path.relative_to(ROOT)))
    assert discovered <= callers, discovered - callers
