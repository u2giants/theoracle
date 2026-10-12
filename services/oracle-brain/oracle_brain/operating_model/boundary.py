"""Static import admission for the clean core; no legacy business reuse."""
from __future__ import annotations

import ast


def import_violations(text: str, *, package: str, helper_allowlist: frozenset[str]) -> list[str]:
    denied = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ['invalid-syntax']
    # Admit the framework's public graph builder, not Python code compilation.
    graph_types = {alias.asname or alias.name for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module == 'langgraph.graph'
                   for alias in node.names if alias.name == 'StateGraph'}
    assigned = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
    graph_builders = {name for name, values in assigned.items() if len(values) == 1
                      and isinstance(values[0], ast.Call)
                      and isinstance(values[0].func, ast.Name)
                      and values[0].func.id in graph_types}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            try:
                parts = package.split('.')
                if node.level > len(parts): raise ImportError('relative import exceeds package')
                module = '.'.join(parts[:len(parts)-node.level+1]+([node.module] if node.module else [])) if node.level else (node.module or '')
            except ImportError:
                denied.append('invalid-relative-import')
                continue
            if module in {'oracle_brain','oracle_brain.ingest','oracle_brain.knowledge'}:
                names = [module + '.' + alias.name for alias in node.names]
            else:
                names = [module]
        elif isinstance(node, ast.Name) and node.id in {'__import__','exec','eval','compile','__builtins__','import_module','__loader__','__spec__'}:
            denied.append('dynamic-code:' + node.id)
        elif isinstance(node, ast.Attribute) and node.attr in {'__import__','exec','eval','compile','import_module','exec_module','load_module','spec_from_file_location','SourceFileLoader'}:
            if not (node.attr == 'compile' and isinstance(node.value, ast.Name) and node.value.id in graph_builders):
                denied.append('dynamic-code:' + node.attr)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {'__import__', 'exec', 'eval'}:
                denied.append('dynamic-code:' + node.func.id)
            elif isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module':
                denied.append('dynamic-import')
        for name in names:
            if name.split('.')[0] in {'builtins','runpy','pkgutil','sys'} or (name.split('.')[0]=='importlib' and name!='importlib.metadata'):
                denied.append('dynamic-module:' + name)
            if name == 'oracle_brain' or name.startswith('oracle_brain.'):
                if not (name.startswith('oracle_brain.operating_model.') or name == 'oracle_brain.operating_model' or name in helper_allowlist):
                    denied.append(name)
    return denied
