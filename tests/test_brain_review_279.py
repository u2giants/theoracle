"""Offline regressions for #279; execute real functions without service imports.

The brain integration suite requires Postgres and third-party dependencies.
Extracting functions keeps these checks runnable in the network-free fixer.
"""
import ast
import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1] / 'apps/brain/brain'


def load(file, names, **env):
    tree = ast.parse((ROOT / file).read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    namespace = dict(json=json, re=re, UUID=UUID, logger=logging.getLogger(__name__), **env)
    exec(compile(ast.fix_missing_locations(module), str(ROOT / file), 'exec'), namespace)
    return SimpleNamespace(**namespace)


def connection():
    conn = MagicMock()
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    return conn, lambda: pool


def answer(**env):
    return load('answer/answer.py', ['AnswerError', '_post_scaledown', '_route_mode', '_compress_passages', '_finalize_global', '_closest_chunk', '_renumber', '_sentence_slices', '_load_reports'],
                _MARKER=re.compile(r'\[(\d+)\]'), _SENTENCE_SPLIT=re.compile(r'(?<=[.!?])\s+'), **env)


def test_invalid_global_citation_and_closest_chunk():
    conn, pool = connection()
    embed = MagicMock()
    mod = answer(get_pool=pool, embed_texts=embed, _paragraphs=lambda text: [text])
    text, citations = mod._finalize_global('A claim [1].', [{'source_id': 'bad-uuid'}], None, {})
    assert '(uncited)' in text and citations == []
    assert mod._closest_chunk(conn, 'bad-uuid', []) is None
    conn.execute.assert_not_called()
    embed.assert_not_called()


def test_ten_citations_select_exact_paragraph():
    conn, pool = connection()
    conn.execute.return_value.fetchone.return_value = ('Source',)
    embed = MagicMock(return_value=[[1]] * 10)
    chunk = lambda *args: dict(chunk_id='chunk', text='quote', locator={})
    mod = answer(get_pool=pool, embed_texts=embed, _paragraphs=lambda text: text.split('\n\n'))
    mod._finalize_global.__globals__['_closest_chunk'] = chunk
    paragraphs = ['Tenth [10].'] + [f'Claim {i} [{i}].' for i in range(1, 10)]
    mod._finalize_global('\n\n'.join(paragraphs), [{'source_id': str(UUID(int=i))} for i in range(1, 11)], None, {})
    assert embed.call_args.args[0] == paragraphs[1:] + paragraphs[:1]


def test_scaledown_transport_falls_back():
    class HTTPError(Exception):
        pass
    post = MagicMock(side_effect=HTTPError('timeout'))
    mod = answer(httpx=SimpleNamespace(post=post, HTTPError=HTTPError), flat_mod=SimpleNamespace(SCALEDOWN_BASE_URL='unused'), ROUTE_LABELS=[], _tokens=lambda text: 100, COMPRESS_MIN_TOKENS=1)
    cfg = SimpleNamespace(brain_scaledown_enabled=True, scaledown_api_key='fake')
    assert mod._route_mode('question', cfg, {}) == 'both'
    assert mod._compress_passages(['one', 'two'], 'question', cfg, {}) == 'one\n\ntwo'
    assert post.call_count == 2


def test_embedding_bad_json_is_retried():
    response = MagicMock(status_code=200)
    response.json.side_effect = [ValueError('invalid JSON'), {'data': [{'embedding': [1.0]}]}]
    post = MagicMock(return_value=response)
    mod = load('embed.py', ['EmbedError', '_post_embeddings', '_post_embeddings_once'], httpx=SimpleNamespace(post=post, HTTPError=OSError), EMBED_ATTEMPTS=3, OPENROUTER_BASE_URL='unused')
    cfg = SimpleNamespace(openrouter_api_key='fake', brain_embed_model='fake', brain_embed_dims=1)
    assert mod._post_embeddings(['text'], cfg) == ([[1.0]], {})
    assert post.call_count == 2


def test_report_queries_scope_current_version():
    conn, pool = connection()
    conn.execute.return_value.fetchall.return_value = []
    mod = load('graph/communities.py', ['_existing_reports'])
    assert mod._existing_reports(conn, 42) == {}
    sql, params = conn.execute.call_args.args
    assert 'WHERE graph_version = %s' in sql and params == (42,)
    assert answer(get_pool=pool)._load_reports() == []
    sql = conn.execute.call_args.args[0]
    assert 'graph_version = (SELECT COALESCE(MAX(version), 0) FROM cmap.graph_version)' in sql


def test_describe_transport_failure_is_skipped(tmp_path):
    class HTTPError(Exception):
        pass
    conn = MagicMock()
    conn.execute.return_value.fetchall.side_effect = [[('entity', 'Person', 3)], [('Name', 'Quote')]]
    frontier = SimpleNamespace(ask=MagicMock(side_effect=HTTPError('timeout')))
    prompt = tmp_path / 'prompt.md'
    prompt.write_text('{{entity_type}} {{names_json}} {{quotes}}')
    mod = load('resolve/resolve.py', ['ResolveError', 'FrontierCapReached', '_describe'], httpx=SimpleNamespace(HTTPError=HTTPError), DESCRIBE_MIN_MENTIONS=3, DESCRIBE_MAX_QUOTES=10, DESCRIBE_PROMPT_PATH=prompt)
    assert mod._describe(conn, frontier) == 0
    assert conn.execute.call_count == 2
    conn.commit.assert_not_called()


def test_company_uses_level_one_reports():
    # Run both newly generated and reused level-1 branches through the real orchestrator.
    for reuse in (False, True):
        conn, pool = connection()
        conn.execute.return_value.fetchall.return_value = []
        conn.execute.return_value.fetchone.return_value = (42,)
        l0 = dict(title='Local', summary='Local detail', findings=[])
        l1 = dict(title='Division', summary='Division synthesis', findings=[], row_id='level-one')
        company_ask = MagicMock(return_value=l1)
        mod = load('graph/communities.py', ['run_communities', '_group_summaries', '_member_ids'],
                   get_pool=pool, _Frontier=lambda cfg: SimpleNamespace(usage={}),
                   _load_entities=lambda conn: [{'id': 'entity'}], _load_edges=lambda conn: [],
                   _level0_membership=lambda *args: {'entity': 0}, _level1_membership=lambda *args: {0: 0},
                   _existing_reports=lambda conn, version: {(1, frozenset(['entity'])): l1} if reuse else {},
                   _context_l0=lambda *args: 'original', _context_reports=lambda reports: [r['summary'] for r in reports],
                   _ask_many=lambda frontier, tasks: [l0 if task[0] == 'L0' else l1 for task in tasks],
                   _store=lambda *args: ('stored', 0), _store_open_questions=lambda *args: 0,
                   _child_rows=lambda *args: [], _ask_with_retry=company_ask,
                   SCOPE_L0='L0', SCOPE_L1='L1', SCOPE_L2='L2', COMPANY_EXTRA='')
        mod.run_communities(SimpleNamespace())
        assert company_ask.call_args.args[3] == ['Division synthesis']


def test_level_one_context_preserves_finding_source_ids():
    mod = load('graph/communities.py', ['_context_reports'], _fit=lambda lines: '\n'.join(lines))
    context = mod._context_reports([dict(title='Division', summary='Synthesis', findings=[dict(kind='fact', text='Claim', source_ids=['source-a'])])])
    assert 'sources: source-a' in context
