"""Evaluation harness on the fixture corpus (plan step 11).

The five seed questions run through the real step-9 answer pipeline over the
projected fixture corpus (procedure PDF, Teams transcript, flowchart PNG).
Model calls are replayed: answer prose comes from
``recorded/frontier/eval_answers.json`` and cites the quotes the pipeline put
in the prompt; the grader replays ``recorded/frontier/eval_grade.json`` by
applying the rule in ``prompts/grade.md`` mechanically (a point is covered
only by a cited sentence holding its key words). This guards retrieval and
citation logic, not model quality.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from conftest import fake_relations, fake_scaledown, fake_vision, load_recorded
from test_answer import (
    FLOWCHART_FIXTURE,
    _point_embeddings,
    fake_compress,
    fake_embeds,
)
from test_flat import PDF_FIXTURE, TRANSCRIPT_FIXTURE, _seed_fixture
from test_resolve import _fake as _fake_resolve

from brain.answer import answer as answer_mod
from brain.config import get_settings
from brain.eval import run as eval_mod
from brain.eval.run import (
    cited_expected,
    load_seed,
    normalize_grade,
    run_eval,
    score_grade,
)
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import handle_relations
from brain.graph.project import run_project
from brain.resolve.resolve import run_resolve

QUOTES_MARKER = "QUOTES (verbatim, each with its chunk_id):\n"
MARKER = re.compile(r"\[(\d+)\]")


def _wrap(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": json.dumps(payload)}}],
        "usage": {"total_tokens": 40},
    }


class EvalAnswers:
    """Replay recorded answer prose; cite one prompt quote per source, in order."""

    def __init__(self) -> None:
        self.answers: dict[str, str] = load_recorded("frontier/eval_answers.json")[
            "answers"
        ]
        self.questions: list[str] = []

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        answer_md = "I could not find this in the data."
        for question, text in self.answers.items():
            if question in prompt:
                self.questions.append(question)
                answer_md = text
                break
        citations: list[dict[str, str]] = []
        if QUOTES_MARKER in prompt:
            blob = prompt.split(QUOTES_MARKER, 1)[1].split("\n>>>", 1)[0].strip()
            seen: set[str] = set()
            for item in json.loads(blob):
                source_id = str(item.get("source_id") or "")
                if source_id in seen:
                    continue
                seen.add(source_id)
                citations.append({"chunk_id": item["chunk_id"], "quote": item["quote"]})
        return _wrap({"answer_md": answer_md, "citations": citations, "unknowns": []})


class KeywordGrader:
    """Replay grading: covered = a cited sentence holds every key word."""

    def __init__(self) -> None:
        self.keywords: dict[str, list[str]] = load_recorded("frontier/eval_grade.json")[
            "keywords"
        ]
        self.prompts: list[str] = []

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        self.prompts.append(prompt)
        points_blob = prompt.split("EXPECTED POINTS:\n", 1)[1].split(
            "\n\nANSWER:\n", 1
        )[0]
        answer = prompt.split("\n\nANSWER:\n", 1)[1].rsplit("\n>>>", 1)[0]
        sentences = re.split(r"(?<=[.!?\]\)])\s+(?!\[)", answer)
        cited = [
            s.casefold() for s in sentences if MARKER.search(s) and "(uncited)" not in s
        ]
        covered: list[int] = []
        missing: list[int] = []
        for line in points_blob.splitlines():
            index_text, point = line.split(". ", 1)
            words = self.keywords[point]
            if any(all(word in sentence for word in words) for sentence in cited):
                covered.append(int(index_text))
            else:
                missing.append(int(index_text))
        return _wrap({"covered": covered, "missing": missing, "contradicted": []})


@pytest.fixture()
def eval_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fixture_corpus(db: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Project the three licensing fixtures exactly as the step-9 gate does."""
    fake_embeds(monkeypatch, {})
    fake_scaledown(monkeypatch, "transcript.json", "pdf.json", "flowchart.json")
    fake_relations(monkeypatch)
    fake_vision(monkeypatch, "vision_flowchart.json")
    ids = {
        "transcript": _seed_fixture(db, TRANSCRIPT_FIXTURE, "transcript"),
        "pdf": _seed_fixture(db, PDF_FIXTURE, "pdf"),
        "flowchart": _seed_fixture(db, FLOWCHART_FIXTURE, "image"),
    }
    for source_id in ids.values():
        handle_classify_extract({"payload": {"source_id": source_id}})
        handle_relations({"payload": {"source_id": source_id}})
    _fake_resolve(monkeypatch)
    run_resolve()
    run_project()
    _point_embeddings(db)
    return ids


def _replay(monkeypatch: pytest.MonkeyPatch) -> tuple[EvalAnswers, KeywordGrader]:
    answers = EvalAnswers()
    grader = KeywordGrader()
    monkeypatch.setattr(answer_mod, "_post_chat", answers)
    monkeypatch.setattr(eval_mod, "_post_chat", grader)
    fake_compress(monkeypatch)
    return answers, grader


# --------------------------------------------------------- the named gate


def test_eval_fixture_mean_at_least_08(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """The five seed questions score a mean of at least 0.8 on the fixtures."""
    _fixture_corpus(db, monkeypatch)
    assert load_seed() == 5
    assert load_seed() == 0
    answers, grader = _replay(monkeypatch)
    run = run_eval()
    assert len(run["results"]) == 5
    assert len(answers.questions) == 5
    assert len(grader.prompts) == 5
    assert run["mean_score"] >= 0.8
    for item in run["results"]:
        assert item["error"] is None
        assert item["mode_used"] == "local"
        assert item["expected_sources_cited"] == item["expected_sources"]
    stored = db.execute(
        "SELECT mean_score, results, prompt_hashes, graph_version, models "
        "FROM cmap.eval_run"
    ).fetchall()
    assert len(stored) == 1
    assert stored[0][0] == pytest.approx(run["mean_score"])
    assert len(stored[0][1]) == 5
    assert set(stored[0][2]) == {
        "answer_local.md",
        "answer_global.md",
        "answer_map.md",
        "grade.md",
    }
    assert stored[0][3] == run["graph_version"]
    models = stored[0][4]
    assert models == run["models"]
    assert models["answer"] == "test/frontier-model"
    assert models["grade"] == "test/frontier-model"
    assert models["scaledown_enabled"] is True
    assert isinstance(models["extraction_models"], dict)
    assert models["extraction_models"]


def test_eval_detects_broken_citations(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Citation validation that drops valid quotes pulls the score under 0.8."""
    _fixture_corpus(db, monkeypatch)
    load_seed()
    _replay(monkeypatch)
    real_finalize = answer_mod._finalize_local

    def broken_finalize(
        answer_md: str,
        raw_citations: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        # A regression: quotes are checked against the wrong chunk (the first
        # retrieved one), so nearly every valid citation is thrown away.
        wrong = [dict(chunk, id=chunks[0]["id"]) for chunk in chunks[:1]]
        return real_finalize(answer_md, raw_citations, wrong)

    monkeypatch.setattr(answer_mod, "_finalize_local", broken_finalize)
    run = run_eval()
    assert run["mean_score"] < 0.8
    assert any("(uncited)" in item["answer_md"] for item in run["results"])


# ------------------------------------------------------------- unit rules


def test_score_formula_penalises_contradictions() -> None:
    assert score_grade(3, [0, 1, 2], []) == 1.0
    assert score_grade(4, [0, 1], []) == 0.5
    assert score_grade(3, [0, 1], [2]) == pytest.approx(2 / 3 - 0.2, abs=1e-4)
    assert score_grade(3, [], [0, 1]) == 0.0
    assert score_grade(0, [], []) == 0.0


def test_normalize_grade_keeps_each_point_once() -> None:
    grade = normalize_grade({"covered": [0, 1, 1, 9, "x"], "contradicted": [1]}, 3)
    assert grade == {"covered": [0], "missing": [2], "contradicted": [1]}


def test_cited_expected_matches_titles_loosely() -> None:
    hits = cited_expected(
        [
            "licensing-approval-procedure.pdf",
            "teams-approval-2026-03-14.txt",
            "missing.docx",
        ],
        [
            "flat-test licensing-approval-procedure.pdf",
            "Flat-Test TEAMS-approval-2026-03-14.txt",
        ],
    )
    assert hits == ["licensing-approval-procedure.pdf", "teams-approval-2026-03-14.txt"]


def test_answer_failure_scores_zero_and_run_continues(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """A question whose answer fails scores 0 with the error kept."""
    load_seed()
    del db

    def failing(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise answer_mod.AnswerError("provider down")

    monkeypatch.setattr(eval_mod, "answer_question", failing)
    run = run_eval()
    assert run["mean_score"] == 0.0
    assert all(
        item["error"] == "answer failed: provider down" for item in run["results"]
    )


# -------------------------------------------------------------- endpoints


def test_eval_endpoints(
    eval_env: None,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
    client: Any,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
) -> None:
    """Questions (admin writes), run queue (admin, de-duplicated), runs with diff."""
    body = {
        "question": "Who signs off licensing?",
        "expected_points": ["Jessica", "Artwork Log", "Licensor"],
        "expected_source_titles": ["licensing-approval-procedure.pdf"],
    }
    assert (
        client.post("/eval/questions", json=body, headers=user_headers).status_code
        == 403
    )
    short = dict(body, expected_points=["only one"])
    assert (
        client.post("/eval/questions", json=short, headers=admin_headers).status_code
        == 400
    )
    added = client.post("/eval/questions", json=body, headers=admin_headers)
    assert added.status_code == 200
    listed = client.get("/eval/questions", headers=user_headers).json()["questions"]
    assert [item["question"] for item in listed] == ["Who signs off licensing?"]
    assert client.post("/eval/run", headers=user_headers).status_code == 403
    first = client.post("/eval/run", headers=admin_headers).json()
    second = client.post("/eval/run", headers=admin_headers).json()
    assert first["queued"] is True
    assert second["queued"] is False
    for score in (0.5, 0.75):
        db.execute(
            "INSERT INTO cmap.eval_run "
            "(graph_version, prompt_hashes, results, mean_score, models) "
            "VALUES (1, '{}', %s, %s, %s)",
            (
                json.dumps([{"question": "Who signs off licensing?", "score": score}]),
                score,
                json.dumps({"answer": "test/a", "grade": "test/b"}),
            ),
        )
        db.commit()
    runs = client.get("/eval/runs", headers=user_headers).json()
    assert [run["mean_score"] for run in runs["runs"]] == [0.75, 0.5]
    assert runs["runs"][0]["mean_delta"] == 0.25
    assert runs["runs"][0]["diff"][0]["previous"] == 0.5
    assert runs["runs"][0]["models"] == {"answer": "test/a", "grade": "test/b"}
    assert runs["runs"][1]["previous_mean"] is None
    assert runs["latest_job"]["state"] == "queued"
    question_id = listed[0]["id"]
    assert (
        client.delete(
            f"/eval/questions/{question_id}", headers=admin_headers
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/eval/questions/{question_id}", headers=admin_headers
        ).status_code
        == 404
    )


def test_evaluate_job_records_usage(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """The worker's ``evaluate`` job runs the eval and stores its summary."""
    _fixture_corpus(db, monkeypatch)
    load_seed()
    _replay(monkeypatch)
    from brain.worker import run_handler

    job_id = db.execute(
        "INSERT INTO cmap.job (kind, payload) VALUES ('evaluate', '{}') RETURNING id"
    ).fetchone()[0]
    db.commit()
    run_handler({"id": job_id, "kind": "evaluate", "payload": {}})
    payload = db.execute(
        "SELECT payload FROM cmap.job WHERE id = %s", (job_id,)
    ).fetchone()[0]
    assert payload["usage"]["mean_score"] >= 0.8
    assert payload["usage"]["grade_calls"] == 5
