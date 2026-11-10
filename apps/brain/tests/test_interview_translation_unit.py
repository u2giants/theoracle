"""Offline regression coverage for interview translation and cache failures."""
from contextlib import contextmanager
from unittest.mock import MagicMock

import httpx
import psycopg
import pytest

from brain import translate
from brain.config import Settings
from brain.interview import tick


@pytest.fixture(scope="session", autouse=True)
def _brain_env():
    """These unit tests use no database or external services."""


@pytest.fixture(autouse=True)
def _clean_cmap():
    """All state is local to each test."""


@pytest.mark.parametrize("error", [RuntimeError("bad payload"), httpx.ConnectError("offline"),
                                    psycopg.errors.CheckViolation("old kind constraint")])
def test_translation_failure_rolls_back_savepoint_and_tick_continues(monkeypatch, error):
    conn = MagicMock()
    rolled_back = []

    @contextmanager
    def transaction():
        try:
            yield
        except Exception:
            rolled_back.append(True)
            raise

    conn.transaction.side_effect = transaction
    conn.execute.return_value.fetchone.return_value = ("zh-CN",)
    conn.execute.return_value.fetchall.return_value = [
        ("q1", "First?", [], None, []), ("q2", "Second?", [], None, []),
    ]
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    monkeypatch.setattr(tick, "get_pool", lambda cfg: pool)
    monkeypatch.setattr(tick, "interviews_enabled", lambda *args: True)
    monkeypatch.setattr(tick, "in_quiet_hours", lambda: False)
    monkeypatch.setattr(tick, "reachable_employees", lambda *args: {})
    monkeypatch.setattr(tick, "select_target", lambda *args: tick.Target("employee", "Name", None))
    monkeypatch.setattr(tick, "translations_for", lambda *args, **kwargs: {})
    translator = MagicMock(side_effect=[error, "第二个？"])
    monkeypatch.setattr(tick, "_translate_question", translator)
    monkeypatch.setattr(tick, "upsert_translation", MagicMock())
    send = MagicMock()
    monkeypatch.setattr(tick, "_post_proactive", send)
    result = tick.run_interview_tick(Settings())
    assert result == {"enabled": True, "asked": 2, "unrouted": 0, "failed": 0}
    assert "First?" in send.call_args_list[0].args[1]
    assert "第二个？" in send.call_args_list[1].args[1]
    assert rolled_back == [True]


def test_cache_write_failure_falls_back(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(tick, "translations_for", lambda *args, **kwargs: {})
    monkeypatch.setattr(tick, "_translate_question", lambda *args: "问题？")
    monkeypatch.setattr(tick, "upsert_translation", MagicMock(side_effect=psycopg.errors.CheckViolation()))
    assert tick._localized_question(conn, "q", "Question?", "zh-CN", Settings()) == "Question?"
    assert conn.transaction.return_value.__exit__.call_args.args[0] is psycopg.errors.CheckViolation


@pytest.mark.parametrize("meta_key,router_key,called", [("meta", None, True), (None, "router", False)])
def test_selected_provider_key(monkeypatch, meta_key, router_key, called):
    monkeypatch.setattr(tick, "stage_model", lambda *args: "meta-model-api/model")
    post = MagicMock(return_value={"choices": [{"message": {"content": "问题？"}}]})
    monkeypatch.setattr(tick, "post_chat_with_rescue", post)
    cfg = Settings(brain_meta_api_key=meta_key, openrouter_api_key=router_key)
    assert tick._translate_question("Question?", cfg) == ("问题？" if called else "")
    assert post.called is called


def test_versioned_cache_reuses_connection_and_invalidates_edits(monkeypatch):
    conn = MagicMock()
    cache = {}

    def lookup(kind, ref_id, **kwargs):
        assert kwargs["conn"] is conn
        return {"zh-CN": cache}

    def store(kind, ref_id, field, lang, text, **kwargs):
        assert kwargs["conn"] is conn
        cache[field] = text

    monkeypatch.setattr(tick, "translations_for", lookup)
    monkeypatch.setattr(tick, "upsert_translation", store)
    translator = MagicMock(side_effect=["问题一", "问题二"])
    monkeypatch.setattr(tick, "_translate_question", translator)
    for source, expected in [("First?", "问题一"), ("First?", "问题一"), ("Edited?", "问题二")]:
        assert tick._localized_question(conn, "q", source, "zh-CN", Settings()) == expected
    assert translator.call_count == 2
    assert len(cache) == 2
    assert "pg_advisory_xact_lock" in conn.execute.call_args.args[0]


@pytest.mark.parametrize("kind,clause", [("question", "DO NOTHING"), ("entity", "DO UPDATE")])
def test_sidecar_existing_connection_and_conflict_policy(monkeypatch, kind, clause):
    monkeypatch.setattr(translate, "get_pool", MagicMock(side_effect=AssertionError("extra checkout")))
    conn = MagicMock()
    translate.upsert_translation(kind, "q", "text", "zh-CN", "问题", conn=conn)
    assert clause in conn.execute.call_args.args[0]
    conn.commit.assert_not_called()
    conn.execute.return_value.fetchall.return_value = [("zh-CN", "text", "问题")]
    assert translate.translations_for(kind, "q", conn=conn) == {"zh-CN": {"text": "问题"}}
