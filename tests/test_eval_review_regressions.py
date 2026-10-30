"""Offline regressions for eval review findings."""
from contextlib import nullcontext

import pytest

import __future__
import ast
import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class EmbedError(RuntimeError):
    pass


class AnswerError(RuntimeError):
    pass


ROOT = Path(__file__).resolve().parents[1]


def load_functions(relative, names, **namespace):
    """Execute actual pure functions without importing unavailable service dependencies."""
    tree = ast.parse((ROOT / relative).read_text())
    tree.body = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    namespace.update(Any=Any)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
    exec(compile(tree, relative, "exec", flags=__future__.annotations.compiler_flag), namespace)
    return SimpleNamespace(**namespace)


ev = load_functions(
    "apps/brain/brain/eval/run.py",
    {"EvalError", "_indexes", "normalize_grade", "grade_answer", "evaluate_question",
     "score_grade", "_fold", "cited_expected", "render_grade_prompt", "_content"},
    re=re, logger=logging.getLogger(__name__), AnswerError=AnswerError,
    EmbedError=EmbedError, GRADE_ATTEMPTS=3, CONTRADICTION_PENALTY=.2,
    GRADE_PROMPT_PATH=ROOT / "apps/brain/brain/prompts/grade.md",
    parse_model_json=lambda content, fields: json.loads(content),
    httpx=SimpleNamespace(HTTPError=OSError),
    answer_question=None, grade_answer=None, _post_chat=None,
)
api = load_functions("apps/brain/brain/api/eval.py",
                     {"_question_key", "diff_runs", "queue_eval"}, get_pool=None)


@pytest.fixture(autouse=True)
def patch_function_globals(monkeypatch):
    # SimpleNamespace patches must reach the actual source functions' globals.
    original = monkeypatch.setattr
    def patch(target, name, value):
        original(target, name, value)
        if target in (ev, api):
            for function in vars(target).values():
                if callable(function) and hasattr(function, "__globals__"):
                    monkeypatch.setitem(function.__globals__, name, value)
    monkeypatch.setattr = patch


def question(key="one"):
    return {"id": key, "question": "Same text", "expected_points": ["point"],
            "expected_source_titles": ["Used", "Other document"]}


def test_embedding_failure_is_isolated(monkeypatch):
    def answer(*args):
        if args[0] == "Same text":
            raise EmbedError("unavailable")
        return {"answer_md": "Answer [1]", "mode_used": "local",
                "citations": [{"title": "Used"}]}
    monkeypatch.setattr(ev, "answer_question", answer)
    monkeypatch.setattr(ev, "grade_answer", lambda *a: ev.normalize_grade({"covered": [0]}, 1))
    failed = ev.evaluate_question(question(), None, {})
    assert failed["score"] == 0
    assert failed["error"] == "answer failed: unavailable"
    assert ev.evaluate_question(dict(question(), question="Next"), None, {})["score"] == 1


def test_only_marked_citations_count(monkeypatch):
    monkeypatch.setattr(ev, "answer_question", lambda *a: {
        "answer_md": "Answer [1] and invalid [9]", "mode_used": "local",
        "citations": [{"title": "Used"}, {"title": "Other document"}]})
    monkeypatch.setattr(ev, "grade_answer", lambda *a: ev.normalize_grade({"covered": [0]}, 1))
    result = ev.evaluate_question(question(), None, {})
    assert result["cited_sources"] == result["expected_sources_cited"] == ["Used"]


@pytest.mark.parametrize("raw", [{}, {"other": []}, {"covered": None}])
def test_malformed_grades_retry_and_fail(monkeypatch, raw):
    calls = []
    def post(*args):
        import json
        calls.append(1)
        return {"choices": [{"message": {"content": json.dumps(raw)}}]}
    monkeypatch.setattr(ev, "_post_chat", post)
    with pytest.raises(ev.EvalError, match="after retries"):
        ev.grade_answer("Question", ["point"], "Answer", None, {})
    assert len(calls) == ev.GRADE_ATTEMPTS


def test_duplicate_text_and_renamed_questions_match_by_id():
    previous = [{"question_id": "a", "question": "Same", "score": .2},
                {"question_id": "b", "question": "Same", "score": .8}]
    current = [{"question_id": "a", "question": "Renamed", "score": .3},
               {"question_id": "b", "question": "Same", "score": .5},
               {"question_id": "c", "question": "Same", "score": .1}]
    assert [d["delta"] for d in api.diff_runs(current, previous)] == [.1, -.3, None]
    assert api.diff_runs([{"question": "Old", "score": .5}],
                         [{"question": "Old", "score": .2}])[0]["delta"] == .3


def test_queue_holds_transaction_lock_through_commit(monkeypatch):
    calls = []
    class Conn:
        def execute(self, sql):
            calls.append(sql)
            return self
        def fetchone(self):
            return ("job",)
        def commit(self):
            calls.append("commit")
    class Pool:
        def connection(self):
            return nullcontext(Conn())
    monkeypatch.setattr(api, "get_pool", Pool)
    assert api.queue_eval(None)["queued"] is True
    assert "pg_advisory_xact_lock" in calls[0]
    assert "INSERT" in calls[1]
    assert calls[2] == "commit"


def test_explicit_all_missing_grade_is_valid():
    assert ev.normalize_grade({"covered": [], "missing": [0], "contradicted": []}, 1) == {
        "covered": [], "missing": [0], "contradicted": []}
