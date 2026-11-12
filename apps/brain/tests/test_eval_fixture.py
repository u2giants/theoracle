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
from conftest import (
    approve_all_questions,
    fake_relations,
    fake_scaledown,
    fake_vision,
    load_recorded,
)
from test_answer import (
    FLOWCHART_FIXTURE,
    FakeSupport,
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
        if "FUNCTION CLASSIFICATION" in prompt:
            return _wrap({"functions": [{"key": "licensing", "weight": 0.9}]})
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
    monkeypatch.setenv("BRAIN_CHAT_MODEL", "test/chat-model")
    monkeypatch.setenv("BRAIN_EVAL_MODEL", "test/eval-model")
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
    # C2's contract in production: every chunk and entity carries at least one
    # function, so C4's router can scope the answer. The fixture corpus is all
    # Licensing.
    function_row = db.execute(
        "INSERT INTO cmap.function (key, name, description) "
        "VALUES ('licensing', 'Licensing', '') RETURNING id"
    ).fetchone()
    function_id = function_row[0]
    db.execute(
        "INSERT INTO cmap.chunk_function (chunk_id, function_id, weight, origin) "
        "SELECT id, %s, 0.9, 'auto' FROM cmap.chunk",
        (function_id,),
    )
    db.execute(
        "INSERT INTO cmap.entity_function (entity_id, function_id, weight, origin) "
        "SELECT id, %s, 0.9, 'auto' FROM cmap.entity",
        (function_id,),
    )
    db.commit()
    return ids


def _replay(monkeypatch: pytest.MonkeyPatch) -> tuple[EvalAnswers, KeywordGrader]:
    answers = EvalAnswers()
    grader = KeywordGrader()
    monkeypatch.setattr(answer_mod, "_post_chat", answers)
    monkeypatch.setattr(answer_mod, "_post_flat", FakeSupport())
    monkeypatch.setattr(eval_mod, "_post_chat", grader)
    fake_compress(monkeypatch)
    return answers, grader


# --------------------------------------------------------- the named gate


def test_eval_fixture_mean_at_least_08(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """The seed questions (en + zh) score a mean of at least 0.8 on the fixtures."""
    _fixture_corpus(db, monkeypatch)
    assert load_seed() == 15
    assert load_seed() == 0
    approve_all_questions(db)
    answers, grader = _replay(monkeypatch)
    run = run_eval()
    assert len(run["results"]) == 15
    assert len(answers.questions) == 15
    assert len(grader.prompts) == 15
    assert run["mean_score"] >= 0.8
    fixture_titles = {
        "licensing-approval-procedure.pdf",
        "teams-approval-2026-03-14.txt",
        "licensing-approval-flowchart.png",
    }
    for item in run["results"]:
        assert item["error"] is None
        assert item["mode_used"] == "local"
        # The zh China-ops questions cite production sources and are proven by
        # the live eval run; this fixture corpus can only cover the en five.
        if set(item["expected_sources"]) <= fixture_titles:
            assert item["expected_sources_cited"] == item["expected_sources"]
    stored = db.execute(
        "SELECT mean_score, results, prompt_hashes, graph_version, models "
        "FROM cmap.eval_run"
    ).fetchall()
    assert len(stored) == 1
    assert stored[0][0] == pytest.approx(run["mean_score"])
    assert len(stored[0][1]) == 15
    assert set(stored[0][2]) == {
        "answer_local.md",
        "answer_global.md",
        "answer_map.md",
        "grade.md",
        "decline_check.md",
        "support_check.md",
        "support_rewrite.md",
    }
    assert stored[0][3] == run["graph_version"]
    models = stored[0][4]
    assert models == run["models"]
    assert models["answer"] == "test/chat-model"
    assert models["grade"] == "test/eval-model"
    assert models["chat"] == "test/chat-model"
    assert models["eval"] == "test/eval-model"
    assert models["frontier"] == "test/frontier-model"
    assert models["scaledown_enabled"] is True
    assert isinstance(models["extraction_models"], dict)
    assert models["extraction_models"]


def test_eval_detects_broken_citations(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Citation validation that drops valid quotes pulls the score under 0.8."""
    _fixture_corpus(db, monkeypatch)
    load_seed()
    approve_all_questions(db)
    _replay(monkeypatch)
    real_finalize = answer_mod._finalize_local

    def broken_finalize(
        answer_md: str,
        raw_citations: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        evidence: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        # A regression: quotes are checked against the wrong chunk (the first
        # retrieved one), so nearly every valid citation is thrown away.
        wrong = [dict(chunk, id=chunks[0]["id"]) for chunk in chunks[:1]]
        return real_finalize(answer_md, raw_citations, wrong, evidence)

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


def test_errors_fail_run(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """A failed answer is reported as error, shown separately, and fails the run."""
    for question in ("Who signs off licensing?", "Who cancels a package?"):
        db.execute(
            "INSERT INTO cmap.eval_question "
            "(question, expected_points, expected_source_titles, author) "
            "VALUES (%s, %s, %s, %s)",
            (question, ["point one", "point two"], ["doc.pdf"], "test"),
        )
    db.commit()
    approve_all_questions(db)

    def flaky(question: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        if "cancels" in question:
            raise answer_mod.AnswerError("provider down")
        return {
            "answer_md": "Sign-off is by Jessica [1].",
            "citations": [{"title": "doc.pdf", "chunk_id": "c1", "quote": "q"}],
            "mode_used": "local",
        }

    def fake_grade(messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del messages, settings
        return _wrap({"covered": [0, 1], "missing": [], "contradicted": []})

    monkeypatch.setattr(eval_mod, "answer_question", flaky)
    monkeypatch.setattr(eval_mod, "_post_chat", fake_grade)
    with pytest.raises(eval_mod.EvalError):
        run_eval()
    rows = db.execute("SELECT results, mean_score FROM cmap.eval_run").fetchall()
    assert len(rows) == 1
    failed = [item for item in rows[0][0] if item["error"]]
    ok = [item for item in rows[0][0] if not item["error"]]
    assert [item["error"] for item in failed] == ["answer failed: provider down"]
    assert failed[0]["score"] == 0.0
    assert len(ok) == 1
    assert ok[0]["score"] == 1.0
    # shown separately: the failure is kept out of the mean, never averaged
    # into it as a silent 0 (which would give 0.5 here)
    assert rows[0][1] == pytest.approx(1.0)


def test_score_components(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Each component contributes its weight: 0.6 points, 0.2 sources, 0.2 support."""
    assert eval_mod.composite_score(1.0, 1.0, 1.0) == 1.0
    assert eval_mod.composite_score(1.0, 0.5, 1.0) == pytest.approx(0.9)
    assert eval_mod.composite_score(1.0, 1.0, 0.5) == pytest.approx(0.9)
    assert eval_mod.composite_score(1.0, 0.0, 0.0) == pytest.approx(0.6)
    assert eval_mod.composite_score(0.5, 0.5, 0.5) == pytest.approx(0.5)
    db.execute(
        "INSERT INTO cmap.eval_question "
        "(question, expected_points, expected_source_titles, author) "
        "VALUES (%s, %s, %s, %s)",
        (
            "Who signs off licensing?",
            ["Jessica signs", "The Artwork Log records it"],
            ["doc.pdf", "notes.txt"],
            "test",
        ),
    )
    db.commit()
    approve_all_questions(db)

    def fake_answer(question: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del question, args, kwargs
        return {
            "answer_md": (
                "Jessica signs the package [1]. "
                "The other sentence carries no citation."
            ),
            "citations": [{"title": "doc.pdf", "chunk_id": "c1", "quote": "q"}],
            "mode_used": "local",
        }

    def fake_grade(messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del messages, settings
        return _wrap({"covered": [0, 1], "missing": [], "contradicted": []})

    monkeypatch.setattr(eval_mod, "answer_question", fake_answer)
    monkeypatch.setattr(eval_mod, "_post_chat", fake_grade)
    run = run_eval()
    item = run["results"][0]
    # 2/2 points covered (0.6) + 1 of 2 expected sources cited (0.2*0.5)
    # + 1 of 2 sentences supported (0.2*0.5) = 0.8
    assert item["score"] == pytest.approx(0.8)
    assert item["score_legacy"] == pytest.approx(1.0)
    assert item["expected_sources_cited"] == ["doc.pdf"]
    assert item["supported_share"] == pytest.approx(0.5)
    assert run["mean_score"] == pytest.approx(0.8)
    assert run["mean_score_legacy"] == pytest.approx(1.0)


def test_abstention_question(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """An abstention question scores 1 only when the answer declines."""
    for question in (
        "How many sampling rounds per style?",
        "What is the sampling budget?",
    ):
        db.execute(
            "INSERT INTO cmap.eval_question "
            "(question, expected_points, expected_source_titles, author, "
            "abstention) VALUES (%s, %s, %s, %s, true)",
            (
                question,
                ["The answer declines", "No guessed number", "Names who to ask"],
                ["doc.pdf"],
                "test",
            ),
        )
    db.commit()
    approve_all_questions(db)

    def fake_answer(question: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        answer_md = (
            "The documents do not say how many rounds are needed [1]."
            if "rounds" in question
            else "The budget is five dollars [1]."
        )
        return {
            "answer_md": answer_md,
            "citations": [{"title": "doc.pdf", "chunk_id": "c1", "quote": "q"}],
            "mode_used": "local",
        }

    def fake_post(messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        if "EXPECTED POINTS:" in prompt:
            return _wrap({"covered": [0, 1, 2], "missing": [], "contradicted": []})
        answer_region = prompt.split("ANSWER:\n", 1)[-1]
        return _wrap({"declines": "do not say" in answer_region})

    monkeypatch.setattr(eval_mod, "answer_question", fake_answer)
    monkeypatch.setattr(eval_mod, "_post_chat", fake_post)
    run = run_eval()
    by_question = {item["question"]: item for item in run["results"]}
    declining = by_question["How many sampling rounds per style?"]
    pretending = by_question["What is the sampling budget?"]
    assert declining["declined"] is True
    assert declining["score"] == 1.0
    assert pretending["declined"] is False
    # the pretend answer covers every expected point, cites every expected
    # source and supports every sentence — it still must not score 1 here
    assert pretending["score"] == 0.0
    assert pretending["score_legacy"] == pytest.approx(1.0)


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
    approve_all_questions(db)
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
    assert payload["usage"]["grade_calls"] == 15


# ------------------------------------------------------- quality gate (B3)


def test_gate_detects_drop(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """A deliberately broken prompt on a preview run makes the gate exit non-zero."""
    from brain.eval import gate

    _fixture_corpus(db, monkeypatch)
    load_seed()
    approve_all_questions(db)
    _replay(monkeypatch)
    good = run_eval()
    assert good["mean_score"] >= 0.8
    assert gate.run_gate().passed is True

    def broken_answer(question: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del question, args, kwargs
        return {
            "answer_md": "I could not find this in the data.",
            "citations": [],
            "mode_used": "local",
        }

    def broken_grade(messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del messages, settings
        return _wrap({"covered": [], "missing": [0, 1], "contradicted": []})

    monkeypatch.setattr(eval_mod, "answer_question", broken_answer)
    monkeypatch.setattr(eval_mod, "_post_chat", broken_grade)
    broken = run_eval()
    assert broken["mean_score"] < good["mean_score"] - 0.05
    assert gate.run_gate().passed is False
    assert gate.main([]) == 1


def test_gate_accepts_first_run_and_keeps_baseline(db: Any) -> None:
    """The first run is accepted; a 0.05 dip passes, a larger one fails."""
    from brain.eval import gate

    def insert(mean: float) -> None:
        db.execute(
            "INSERT INTO cmap.eval_run "
            "(graph_version, prompt_hashes, results, mean_score, models) "
            "VALUES (1, '{}', %s, %s, '{}')",
            (json.dumps([{"question": "q", "score": mean, "error": None}]), mean),
        )
        db.commit()

    insert(0.90)
    assert gate.run_gate().passed is True
    insert(0.85)  # drop of exactly 0.05 is not "more than 0.05"
    assert gate.run_gate().passed is True
    insert(0.78)  # drop of 0.07 from the accepted 0.85 baseline
    decision = gate.run_gate()
    assert decision.passed is False
    assert decision.previous_mean == pytest.approx(0.85)
    assert decision.drop == pytest.approx(0.07)
    insert(0.84)  # recovered against the last accepted run, not the last run
    assert gate.run_gate().passed is True
    flags = [
        row[0]
        for row in db.execute(
            "SELECT accepted FROM cmap.eval_run ORDER BY created_at, id"
        ).fetchall()
    ]
    assert flags == [True, True, False, True]


def test_gate_fails_on_question_error(db: Any) -> None:
    """Any question error fails the gate even without an accepted baseline."""
    from brain.eval import gate

    db.execute(
        "INSERT INTO cmap.eval_run "
        "(graph_version, prompt_hashes, results, mean_score, models) "
        "VALUES (1, '{}', %s, %s, '{}')",
        (
            json.dumps(
                [{"question": "q", "score": 0.0, "error": "grading failed: boom"}]
            ),
            0.0,
        ),
    )
    db.commit()
    decision = gate.run_gate()
    assert decision.passed is False
    assert decision.error_count == 1
    assert gate.main([]) == 1
    db.execute(
        "INSERT INTO cmap.eval_run "
        "(graph_version, prompt_hashes, results, mean_score, models) "
        "VALUES (1, '{}', %s, %s, '{}')",
        (json.dumps([{"question": "q", "score": 0.5, "error": None}]), 0.5),
    )
    db.commit()
    assert gate.run_gate().passed is True


def test_eval_service_calls_queue_and_read_runs(
    db: Any, client: Any, user_headers: dict[str, str]
) -> None:
    """The shared token alone queues and reads runs for the quality workflow."""
    from conftest import TEST_TOKEN

    service = {"x-brain-token": TEST_TOKEN}
    assert client.post("/eval/run").status_code == 401
    assert (
        client.post("/eval/run", headers={"x-brain-token": "wrong"}).status_code == 401
    )
    queued = client.post("/eval/run", headers=service).json()
    assert queued["queued"] is True
    assert client.post("/eval/run", headers=service).json() == {
        "queued": False,
        "detail": "an eval run is already queued or running",
    }
    run_id = db.execute(
        "INSERT INTO cmap.eval_run "
        "(graph_version, prompt_hashes, results, mean_score, models) "
        "VALUES (1, '{}', %s, %s, '{}') RETURNING id::text",
        (json.dumps([{"question": "q", "score": 0.5, "error": None}]), 0.5),
    ).fetchone()[0]
    db.commit()
    runs = client.get("/eval/runs", headers=service).json()
    assert runs["runs"][0]["mean_score"] == pytest.approx(0.5)
    assert runs["runs"][0]["accepted"] is False
    # The accept round-trip (B3): the service marks the baseline run accepted.
    assert client.post(f"/eval/runs/{run_id}/accept").status_code == 401
    assert (
        client.post(f"/eval/runs/{run_id}/accept", headers=user_headers).status_code
        == 403
    )
    assert (
        client.post("/eval/runs/not-a-uuid/accept", headers=service).status_code == 404
    )
    assert (
        client.post(
            "/eval/runs/11111111-1111-1111-1111-111111111111/accept",
            headers=service,
        ).status_code
        == 404
    )
    accepted = client.post(f"/eval/runs/{run_id}/accept", headers=service).json()
    assert accepted == {"id": run_id, "mean_score": pytest.approx(0.5), "accepted": True}
    assert client.get("/eval/runs", headers=service).json()["runs"][0]["accepted"] is True


class _FakeResponse:
    """Minimal stand-in for an httpx response in the live gate tests."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeBrain:
    """The deployed brain's run store and accept endpoint, as a fake.

    ``POST /eval/run`` lands the next prepared run (the worker); the accept
    endpoint sets ``accepted`` so the next decision sees the baseline — the
    exact production round-trip the gate must make.
    """

    def __init__(self, *runs: dict[str, Any]) -> None:
        self.pending = list(runs)
        self.runs: list[dict[str, Any]] = []
        self.accepted_ids: list[str] = []
        self.accept_error: Exception | None = None

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        del url, kwargs
        return _FakeResponse(
            {
                "runs": [dict(item) for item in self.runs],
                "latest_job": {"state": "done", "error": None},
            }
        )

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        del kwargs
        if url.endswith("/eval/run"):
            if self.pending:
                self.runs.insert(0, dict(self.pending.pop(0)))
            return _FakeResponse({"queued": True, "job_id": "job"})
        run_id = url.rsplit("/", 2)[1]
        if self.accept_error is not None:
            raise self.accept_error
        for item in self.runs:
            if str(item.get("id")) == run_id:
                item["accepted"] = True
        self.accepted_ids.append(run_id)
        return _FakeResponse({"id": run_id, "accepted": True})


def _fake_run(run_id: str, mean: float) -> dict[str, Any]:
    return {
        "id": run_id,
        "mean_score": mean,
        "accepted": False,
        "results": [{"question": "q", "score": mean, "error": None}],
    }


def test_live_gate_marks_accepted_and_catches_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live runs record the accepted baseline and fail the next big drop.

    The second live run dropping 0.10 against the accepted first MUST fail —
    without the accept round-trip no baseline exists and the drop check would
    silently never fire.
    """
    import httpx

    from brain.eval import gate

    brain = _FakeBrain(
        _fake_run("run-good", 0.90), _fake_run("run-bad", 0.80), _fake_run("run-back", 0.88)
    )
    monkeypatch.setattr(httpx, "get", brain.get)
    monkeypatch.setattr(httpx, "post", brain.post)

    first = gate.live_gate("https://brain.example", "token", attempts=2, interval=0)
    assert first.passed is True
    assert brain.accepted_ids == ["run-good"]
    assert brain.runs[0]["accepted"] is True

    second = gate.live_gate("https://brain.example", "token", attempts=2, interval=0)
    assert second.passed is False
    assert second.previous_mean == pytest.approx(0.90)
    assert second.drop == pytest.approx(0.10)
    assert brain.accepted_ids == ["run-good"]

    third = gate.live_gate("https://brain.example", "token", attempts=2, interval=0)
    assert third.passed is True
    assert brain.accepted_ids == ["run-good", "run-back"]


def test_live_gate_surfaces_accept_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A passing run whose accept call fails is never silently swallowed."""
    import httpx

    from brain.eval import gate

    brain = _FakeBrain(_fake_run("run-good", 0.90))
    brain.accept_error = httpx.ConnectError("accept endpoint down")
    monkeypatch.setattr(httpx, "get", brain.get)
    monkeypatch.setattr(httpx, "post", brain.post)
    decision = gate.live_gate("https://brain.example", "token", attempts=2, interval=0)
    assert decision.passed is False
    assert "accept call failed" in decision.reason
    assert brain.accepted_ids == []


def test_live_gate_bails_on_job_error_while_retrying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An eval job that errored fails the gate even while A2 re-queues it.

    The production shape is state=queued with the error text kept (retry with
    backoff); waiting for state=failed only burns the poll timeout first.
    """
    import httpx

    from brain.eval import gate

    class _ErroredJob(_FakeBrain):
        def get(self, url: str, **kwargs: Any) -> _FakeResponse:
            del url, kwargs
            return _FakeResponse(
                {
                    "runs": [],
                    "latest_job": {
                        "state": "queued",
                        "error": "no eval questions: add some on the eval page (or load the seed)",
                    },
                }
            )

    brain = _ErroredJob()
    monkeypatch.setattr(httpx, "get", brain.get)
    monkeypatch.setattr(httpx, "post", brain.post)
    decision = gate.live_gate("https://brain.example", "token", attempts=2, interval=0)
    assert decision.passed is False
    assert "no eval questions" in decision.reason
