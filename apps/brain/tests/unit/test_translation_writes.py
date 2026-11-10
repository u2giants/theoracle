"""Offline regression tests for translation writes and legacy reconciliation."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from brain.graph.communities import _existing_reports, _store
from brain.translate import cleanup_translations, english_text, upsert_translation


@pytest.mark.parametrize('title,summary,title_en,summary_en,zh_fields', [
    ('采购流程', '采购审批流程。', 'Purchasing', 'Purchasing approval.', {'title', 'summary'}),
    ('Purchasing', '采购审批流程。', '', 'Purchasing approval.', {'summary'}),
    ('采购流程', 'Purchasing approval.', 'Purchasing', '', {'title'}),
    ('Purchasing', 'Purchasing approval.', '', '', set()),
])
def test_community_fields_independent(title, summary, title_en, summary_en, zh_fields):
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = ('community-id',)
    report = dict(title=title, summary=summary, title_en=title_en,
                  summary_en=summary_en, findings=[], open_questions=[])
    _store(conn, 0, None, report, [], 1, set())
    calls = conn.execute.call_args_list
    assert calls[0].args[1][2] == (title_en or title)
    assert (summary_en or summary) in calls[0].args[1][3]
    writes = [call.args[1] for call in calls if 'INSERT INTO cmap.translation' in call.args[0]]
    assert {args[2] for args in writes if args[3] == 'zh-CN'} == zh_fields
    conn.commit.assert_not_called()


def test_missing_english_is_retryable_before_insert():
    conn = Mock()
    with pytest.raises(ValueError):
        _store(conn, 0, None, dict(title='采购流程', summary='Text', findings=[],
                                 open_questions=[]), [], 1, set())
    conn.execute.assert_not_called()
    with pytest.raises(ValueError):
        english_text('采购流程', '采购流程')


def test_empty_translation_deletes_without_committing():
    conn = Mock()
    upsert_translation('entity', 'id', 'description', 'zh-CN', '', conn=conn)
    assert conn.execute.call_args.args[0].startswith('DELETE')
    conn.commit.assert_not_called()


def test_reconcile_legacy_community_preserves_id_and_findings():
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [
        ('id', 0, '采购流程', '# 采购流程\n\n采购审批流程。\n\n## Findings\n- evidence', [], ['member'])
    ]
    conn.execute.return_value.fetchone.return_value = None
    frontier = SimpleNamespace(ask=Mock(side_effect=[{'english': 'Purchasing'},
                                                     {'english': 'Purchasing approval.'}]))
    result = _existing_reports(conn, frontier)
    assert result[(0, frozenset(['member']))]['row_id'] == 'id'
    update = conn.execute.call_args.args[1]
    assert update == ('Purchasing', '# Purchasing\n\nPurchasing approval.\n## Findings\n- evidence', 'id')
    conn.commit.assert_not_called()


def test_cleanup_covers_deleted_artifact_kinds():
    conn = Mock()
    cleanup_translations(conn)
    assert {call.args[1][0] for call in conn.execute.call_args_list} == {'entity', 'community'}
    assert all('NOT EXISTS' in call.args[0] for call in conn.execute.call_args_list)
    conn.commit.assert_not_called()


@pytest.mark.parametrize('description,english,chinese', [
    ('采购审批流程。', 'Purchasing approval.', '采购审批流程。'),
    ('Purchasing approval.', '', ''),
    ('', '', ''),
])
def test_entity_translation_and_description_commit_together(monkeypatch, description, english, chinese):
    from brain.resolve import resolve

    conn = Mock()
    cursor = conn.execute.return_value
    cursor.fetchall.side_effect = [[('id', 'Process', 3)], [('Name', 'Evidence')]]
    cursor.fetchone.return_value = ('Name', english or description)
    frontier = SimpleNamespace(settings=Mock(), usage=Mock(), ask=Mock(return_value={
        'description': description, 'description_en': english, 'description_zh': chinese,
    }))
    monkeypatch.setattr(resolve, 'embed_texts', lambda *args: [[0.1]])
    monkeypatch.setattr(resolve, 'vector_literal', lambda vector: '[0.1]')
    assert resolve._describe(conn, frontier) == 1
    calls = conn.method_calls
    assert calls[-1][0] == 'commit'
    zh_call = calls[-2].args
    assert zh_call[1][3] == 'zh-CN'
    assert ('INSERT' if chinese else 'DELETE') in zh_call[0]
    query = calls[0].args[0]
    assert 'NOT EXISTS' in query and "t.lang = 'en'" in query


def test_failed_entity_sidecar_never_commits(monkeypatch):
    from brain.resolve import resolve

    conn = Mock()
    conn.execute.return_value.fetchall.side_effect = [[('id', 'Process', 3)], [('Name', 'Evidence')]]
    conn.execute.return_value.fetchone.return_value = ('Name', 'English description.')
    frontier = SimpleNamespace(settings=Mock(), usage=Mock(), ask=Mock(return_value={
        'description': 'English description.',
    }))
    monkeypatch.setattr(resolve, 'embed_texts', lambda *args: [[0.1]])
    monkeypatch.setattr(resolve, 'vector_literal', lambda vector: '[0.1]')
    monkeypatch.setattr(resolve, 'upsert_translation', Mock(side_effect=RuntimeError('write failed')))
    with pytest.raises(RuntimeError, match='write failed'):
        resolve._describe(conn, frontier)
    conn.commit.assert_not_called()
