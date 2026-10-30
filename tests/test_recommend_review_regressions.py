"""Offline regression checks for recommendation review findings."""
import ast
import json
import logging
import re
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'apps/brain/brain'


def load(relative, names, **bindings):
    """Execute the actual functions without loading unavailable service SDKs."""
    tree = ast.parse((ROOT / relative).read_text())
    nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in names for target in node.targets
        ):
            nodes.append(node)
    scope = dict(re=re, json=json, logger=logging.getLogger(__name__), **bindings)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(ROOT / relative), 'exec'), scope)
    return SimpleNamespace(**scope)


@pytest.mark.parametrize('text', ['5 days', '3x faster', '5000 units', '40%', '$5,000', '2 working hours'])
def test_scrubs_measurements(text):
    mod = load('recommend/recommend.py', {'_scrub', '_QUANTITY', '_PERCENT', '_MONEY', 'UNMEASURED'})
    assert not re.search(r'\d', mod._scrub(text))


@pytest.mark.parametrize('days', [0, -5, 1000000, 'bad', float('inf'), None, 1, 365])
def test_review_days(days):
    mod = load('recommend/recommend.py', {'_experiment', 'DEFAULT_REVIEW_DAYS'})
    result = mod._experiment({'review_after_days': days}, True)
    assert result['review_after_days'] == (days if days in (1, 365) else 30)


@pytest.mark.parametrize('failure', ['existing', 'new', 'dimensions', 'cap'])
def test_embedding_failure_preserves_usage(failure):
    class Cap(Exception):
        pass

    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [('old',)]
    pool = SimpleNamespace(connection=lambda: nullcontext(conn))
    frontier = SimpleNamespace(ask=Mock(return_value={}), usage={'tokens': 42})
    embed = Mock(side_effect={
        'existing': [RuntimeError('offline')],
        'new': [[[1.0]], RuntimeError('offline')],
        'dimensions': [[[1.0]], [[1.0, 2.0]]],
        'cap': [[[1.0]], Cap()],
    }[failure])
    store = Mock()
    candidate = {'source_ids': ['a'], 'finding': {}, 'community_id': 'c'}
    mod = load('recommend/recommend.py', {'run_recommend'},
               _Frontier=lambda cfg: frontier, PROMPT_PATH=SimpleNamespace(read_text=lambda **kw: '{{context}}'),
               get_pool=lambda cfg: pool, _candidates=lambda conn: [candidate],
               _titles=lambda *args: {}, _quotes=lambda *args: [], _context=lambda *args: '',
               _has_numbers=lambda evidence: False, _normalise=lambda *args: {'problem': 'new'},
               embed_texts=embed, FrontierCapReached=Cap, DEDUPE_COSINE=.9, _store=store,
               _cosine=lambda a, b: sum(x * y for x, y in zip(a, b, strict=True)))
    stats = mod.run_recommend(object())
    assert stats['tokens'] == 42
    assert stats['capped'] == (failure == 'cap')
    assert stats['failed'] == (0 if failure == 'cap' else 1)
    store.assert_not_called()
    conn.commit.assert_not_called()


def test_graph_connection_retains_only_its_own_client():
    factory = Mock(side_effect=[Mock(), Mock()])
    mod = load('graph/project.py', {'connect', '_client'},
               FalkorDB=SimpleNamespace(from_url=factory), GRAPH_NAME='company')
    cfg = SimpleNamespace(falkordb_url='redis://test')
    first = mod.connect(cfg)
    second = mod.connect(cfg)
    assert factory.call_count == 2
    assert first._oracle_client is not second._oracle_client


def test_recommend_enqueue_serializes_and_checks_waiting_job():
    conn = Mock()
    mod = load('graph/communities.py', {'handle_communities'},
               run_communities=lambda: {},
               get_pool=lambda: SimpleNamespace(connection=lambda: nullcontext(conn)))
    mod.handle_communities({})
    statements = [call.args[0] for call in conn.execute.call_args_list]
    assert 'pg_advisory_xact_lock' in statements[0]
    assert "WHERE NOT EXISTS" in statements[1]
    assert "kind = 'recommend' AND state = 'queued'" in statements[1]
    conn.commit.assert_called_once()
