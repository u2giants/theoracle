"""Static import admission for the clean core; no legacy business reuse."""
from __future__ import annotations

import ast
from importlib.util import resolve_name


def import_violations(text: str, *, package: str, helper_allowlist: frozenset[str]) -> list[str]:
    denied = []
    for node in ast.walk(ast.parse(text)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = resolve_name('.' * node.level + (node.module or ''), package) if node.level else (node.module or '')
            if module == 'oracle_brain':
                names = [module + '.' + alias.name for alias in node.names]
            else:
                names = [module]
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {'__import__', 'exec', 'eval'}:
                denied.append('dynamic-code:' + node.func.id)
            elif isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module':
                denied.append('dynamic-import')
        for name in names:
            if name == 'oracle_brain' or name.startswith('oracle_brain.'):
                if not (name.startswith('oracle_brain.operating_model.') or name == 'oracle_brain.operating_model' or name in helper_allowlist):
                    denied.append(name)
    return denied
