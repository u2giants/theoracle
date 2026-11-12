"""Step 4.1 gate: the eval harness grades Chinese questions and answers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import approve_all_questions
from test_eval_fixture import _fixture_corpus, _replay

from brain.answer import answer as answer_mod
from brain.config import get_settings
from brain.eval.run import (
    load_questions,
    load_seed,
    normalize_grade,
    render_grade_prompt,
    run_eval,
)

SEED_PATH = Path(__file__).resolve().parents[1] / "eval" / "questions.seed.json"
ZH_QUESTION = "样品从工厂提交到样品间走查的流程是怎样的？"
ZH_POINTS = ["样品要先过内部审批（Samples Internal Approval）", "样品意见记录之后才进样品间排期"]
ZH_ANSWER = "样品要先过内部审批（Samples Internal Approval） [1]。样品意见记录之后才进样品间排期 [2]。"


@pytest.fixture()
def eval_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    monkeypatch.setenv("BRAIN_CHAT_MODEL", "test/chat-model")
    monkeypatch.setenv("BRAIN_EVAL_MODEL", "test/eval-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _cjk_questions() -> list[dict[str, Any]]:
    return [
        row
        for row in json.loads(SEED_PATH.read_text(encoding="utf-8"))["questions"]
        if any("一" <= ch <= "鿿" for ch in row["question"])
    ]


def test_seed_loads_zh_questions(eval_env: None, db: Any) -> None:
    seed = _cjk_questions()
    assert len(seed) == 10  # O4: 5 process, 3 cross-source, 2 negative
    added = load_seed()
    assert added >= len(seed)
    again = load_seed()
    assert again == 0  # seeding only inserts when absent
    approve_all_questions(db)
    questions = [item["question"] for item in load_questions()]
    for item in seed:
        assert item["question"] in questions
        assert all(
            any("一" <= ch <= "鿿" for ch in point) for point in item["expected_points"]
        )


def test_grader_handles_zh_expected_points() -> None:
    prompt = render_grade_prompt(ZH_QUESTION, ZH_POINTS, ZH_ANSWER)
    assert ZH_QUESTION in prompt
    assert ZH_POINTS[0] in prompt
    assert "in whatever language" in prompt  # the language-neutral rubric (step 2.2)
    graded = normalize_grade({"covered": [0], "missing": [1], "contradicted": []}, 2)
    assert graded == {"covered": [0], "missing": [1], "contradicted": []}


def test_eval_detects_broken_citations_zh(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    _fixture_corpus(db, monkeypatch)
    load_seed()
    approve_all_questions(db)
    answers, grader = _replay(monkeypatch)
    answers.answers[ZH_QUESTION] = ZH_ANSWER
    grader.keywords[ZH_POINTS[0]] = ["内部审批"]
    grader.keywords[ZH_POINTS[1]] = ["样品间排期"]

    real_finalize = answer_mod._finalize_local

    def broken_finalize(
        answer_md: str,
        raw_citations: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        wrong = [dict(chunk, id=chunks[0]["id"]) for chunk in chunks[:1]]
        return real_finalize(answer_md, raw_citations, wrong)

    monkeypatch.setattr(answer_mod, "_finalize_local", broken_finalize)
    run = run_eval()
    assert run["mean_score"] < 0.8
    zh_results = [item for item in run["results"] if ZH_QUESTION in str(item.get("question"))]
    assert zh_results
    assert any("(uncited)" in str(item["answer_md"]) for item in zh_results)
