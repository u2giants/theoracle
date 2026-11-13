"""Stored interview questions are English-only canon (owner 2026-11-13).

The communities pipeline may generate a question in the language of its
source quotes; the guard in ``brain.translate.ensure_english_question`` rewrites
it to English before it reaches ``cmap.open_question``. zh-CN recipients still
get their translation at send time (``test_interview_zh`` covers that path).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import fake_embeddings

from brain.config import get_settings
from brain.graph.communities import _store_open_questions
from brain.lang import contains_non_latin_letters, looks_english
from brain.resolve.resolve import _Frontier
from brain.translate import ensure_english_question

RU_QUESTION = (
    "\u041a\u0442\u043e \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u044f\u0435\u0442 "
    "\u0437\u0430\u043f\u0440\u043e\u0441 \u043d\u0430 \u0438\u0441\u043a\u043b\u044e\u0447\u0435"
    "\u043d\u0438\u0435 \u0412\u041f?"
)
RU_ENGLISH = "Who submits the VP exception request?"
ZH_QUESTION = "\u8c01\u7b7e\u7f72\u6388\u6743\u65b9\u5ba1\u6279\u8868\uff1f"
ZH_ENGLISH = "Who signs the licensor approval form?"


def _ask_returning(text: str) -> Any:
    def _ask(prompt: str) -> dict[str, str]:
        assert prompt.startswith("ENGLISH QUESTION REWRITE")
        return {"question_en": text}

    return _ask


def test_looks_english_classifies_questions() -> None:
    assert looks_english("Who owns the sign-off?") is True
    assert looks_english("Is Mar\u00eda the buyer who gives approval?") is True
    assert looks_english(RU_QUESTION) is False
    assert looks_english(ZH_QUESTION) is False
    assert looks_english("Qui d\u00e9cide de l'ordre des approbations ?") is False
    # Short question without common function words: unsure, not non-English.
    assert looks_english("PPS audit pass criteria?") is None


def test_cyrillic_question_comes_out_english() -> None:
    calls: list[str] = []

    def _ask(prompt: str) -> dict[str, str]:
        calls.append(prompt)
        return {"question_en": RU_ENGLISH}

    out = ensure_english_question(RU_QUESTION, _ask)
    assert out == RU_ENGLISH
    assert len(calls) == 1
    assert RU_QUESTION in calls[0]


def test_clear_english_question_is_not_rewritten() -> None:
    def _boom(prompt: str) -> dict[str, str]:
        raise AssertionError(f"model must not be called: {prompt[:40]}")

    assert (
        ensure_english_question("Who owns the sign-off?", _boom)
        == "Who owns the sign-off?"
    )


def test_failed_rewrite_drops_the_question() -> None:
    def _boom(prompt: str) -> dict[str, Any]:
        raise RuntimeError("model down")

    assert ensure_english_question(RU_QUESTION, _boom) is None
    assert ensure_english_question(RU_QUESTION, _ask_returning("")) is None
    assert ensure_english_question(RU_QUESTION, _ask_returning(RU_QUESTION)) is None
    assert ensure_english_question("", _boom) is None


def test_stored_question_is_always_english(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """A non-English generated question lands in the table as English."""
    from brain.resolve import resolve as resolve_mod

    fake_embeddings(monkeypatch)

    def _fake_post_chat(
        messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del settings, max_tokens
        prompt = str(messages[-1]["content"])
        if prompt.startswith("ENGLISH QUESTION REWRITE"):
            body = {"question_en": ZH_ENGLISH if ZH_QUESTION in prompt else RU_ENGLISH}
        elif prompt.startswith("QUESTION VETTING"):
            candidates = prompt.split("CANDIDATES:\n<<<", 1)[1].rsplit(">>>", 1)[0]
            count = len([b for b in candidates.strip().split("\n\n") if b.strip()])
            body = {
                "results": [
                    {
                        "n": n,
                        "answered": False,
                        "importance": 5,
                        "person": "",
                        "department": "",
                    }
                    for n in range(1, count + 1)
                ]
            }
        else:
            raise AssertionError(f"unexpected prompt: {prompt[:60]}")
        return {
            "choices": [{"message": {"content": json.dumps(body)}}],
            "usage": {"total_tokens": 5},
        }

    monkeypatch.setattr(resolve_mod, "_post_chat", _fake_post_chat)
    report = {"title": "r", "open_questions": [RU_QUESTION, ZH_QUESTION]}
    written = _store_open_questions(
        db, report, [], _Frontier(get_settings(), "reports"), get_settings(), set()
    )
    db.commit()
    rows = [
        r[0] for r in db.execute("SELECT question FROM cmap.open_question").fetchall()
    ]
    assert written == 2
    assert sorted(rows) == sorted([RU_ENGLISH, ZH_ENGLISH])
    assert all(not contains_non_latin_letters(text) for text in rows)


def test_untranslatable_question_is_never_stored(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    from brain.resolve import resolve as resolve_mod

    fake_embeddings(monkeypatch)

    def _fake_post_chat(
        messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del settings, max_tokens
        prompt = str(messages[-1]["content"])
        if prompt.startswith("ENGLISH QUESTION REWRITE"):
            raise RuntimeError("model down")
        raise AssertionError(f"unexpected prompt: {prompt[:60]}")

    monkeypatch.setattr(resolve_mod, "_post_chat", _fake_post_chat)
    report = {"title": "r", "open_questions": [RU_QUESTION]}
    written = _store_open_questions(
        db, report, [], _Frontier(get_settings(), "reports"), get_settings(), set()
    )
    db.commit()
    rows = db.execute("SELECT question FROM cmap.open_question").fetchall()
    assert written == 0
    assert rows == []
