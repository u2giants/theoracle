"""Offline checks for bilingual canonical writes and retained model answers."""
import json
from contextlib import nullcontext

import pytest

from brain.graph import communities
from brain.extract import relations
from brain.lang import english_canonical
from brain.resolve import resolve


@pytest.fixture(scope="session", autouse=True)
def _brain_env():
    """These tests use no database or service."""


@pytest.fixture(autouse=True)
def _clean_cmap():
    """All writes below are captured in memory."""


class Connection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return ("id", "English description")

    def fetchall(self):
        if "SELECT id, entity_type" in self.calls[-1][0]:
            return [("id", "Process", 3)]
        return [("采购", "采购审批流程")]

    def commit(self):
        pass


def test_entity_retains_companions_and_embeds_english(monkeypatch):
    conn = Connection()
    answer = {"description": "采购审批流程", "description_en": "English description", "description_zh": "中文"}
    class Frontier:
        settings = usage = None
        def ask(self, prompt):
            assert "IN THE LANGUAGE OF THE QUOTES" in prompt
            assert "采购审批流程" in prompt
            return answer
    texts = []
    monkeypatch.setattr(resolve, "embed_texts", lambda values, *_: texts.extend(values) or [[0.0]])
    assert resolve._describe(conn, Frontier()) == 1
    params = next(p for sql, p in conn.calls if "describe_payload" in sql)
    assert params[1] == "English description"
    assert json.loads(params[2]) == answer
    assert texts == ["id — English description"]


def test_community_retains_response_and_english_report():
    answer = {"title": "采购审批", "title_en": "Purchasing", "summary": "采购流程", "summary_en": "Approval flow", "findings": [], "open_questions": ["Who approves?"]}
    class Frontier:
        def ask(self, prompt):
            assert "phrased in English" in prompt
            assert "one finding in English" in prompt
            return answer
    report = communities._ask_report(Frontier(), "scope", "", "data")
    conn = Connection()
    communities._store(conn, 0, None, report, [], 1, set())
    params = conn.calls[-1][1]
    assert params[2] == "Purchasing"
    assert "Approval flow" in params[3]
    assert "采购" not in params[3]
    assert json.loads(params[-1]) == answer


def test_relation_companion_is_validated_and_written(monkeypatch):
    known = {key: relations.KnownMention(key, key, "Process", key) for key in ("m1", "m2")}
    payload = {"relations": [{"from": "m1", "to": "m2", "type": "USES", "description": "采购使用系统", "description_en": "Purchasing uses the system", "quote": "采购使用系统", "stance": "practice", "confidence": 0.9}]}
    accepted, mentions = relations.validate_response("采购使用系统", known, payload)
    assert accepted[0].description_en == "Purchasing uses the system"
    conn = Connection()
    class Pool:
        def connection(self):
            return nullcontext(conn)
    monkeypatch.setattr(relations, "get_pool", lambda: Pool())
    result = relations.ChunkResult("chunk", known, payload, accepted, mentions)
    relations._write_result(result, "hash", "model")
    assert conn.calls[0][1][4] == "Purchasing uses the system"
    assert conn.calls[1][1][-1].obj == payload


def test_missing_companion_does_not_overwrite_english():
    with pytest.raises(ValueError, match="English companion"):
        english_canonical("采购审批流程", "")
    assert english_canonical("English", "") == "English"


def test_english_report_without_companions_stays_unchanged():
    report = {
        "title": "Purchasing",
        "summary": "Approval flow",
        "findings": [],
        "open_questions": [],
    }
    conn = Connection()
    communities._store(conn, 0, None, report, [], 1, set())
    params = conn.calls[-1][1]
    assert params[2] == "Purchasing"
    assert "Approval flow" in params[3]
    assert json.loads(params[-1]) == report


def test_open_questions_use_english_context(monkeypatch):
    report = {
        "title": "采购审批",
        "title_en": "Purchasing",
        "open_questions": ["Who approves?"],
    }
    conn = Connection()
    monkeypatch.setattr(conn, "fetchall", lambda: [])
    monkeypatch.setattr(communities, "embed_texts", lambda texts, *_: [[1.0] for _ in texts])
    assert communities._store_open_questions(conn, report, [], None) == 1
    assert conn.calls[-1][1] == ("Who approves?", "Purchasing", [])
