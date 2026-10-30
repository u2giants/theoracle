"""Evaluation harness: the cross-source questions (plan step 11).

``run_eval()`` answers every ``cmap.eval_question`` through the step-9
``answer_question`` (mode ``auto``), grades each answer against its expected
points with the frontier model (``prompts/grade.md``) and writes one
``cmap.eval_run`` row. Score per question = covered / total points, minus
0.2 per contradicted point, floored at 0. The run also records which
expected source titles the answer actually cited.

Job ``evaluate`` runs it in the worker; ``python -m brain.eval.run`` runs it
from a shell (``--seed`` first loads ``eval/questions.seed.json``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import httpx

from brain.answer import answer as answer_mod
from brain.answer.answer import AnswerError, answer_question, parse_model_json
from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import EmbedError

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
GRADE_PROMPT_PATH = PROMPTS_DIR / "grade.md"
HASHED_PROMPTS = ("answer_local.md", "answer_global.md", "answer_map.md", "grade.md")
SEED_PATH = Path(__file__).resolve().parents[2] / "eval" / "questions.seed.json"
SEED_AUTHOR = "seed"
CONTRADICTION_PENALTY = 0.2
GRADE_ATTEMPTS = 3
MAX_TOKENS = 800


class EvalError(RuntimeError):
    """Raised when an eval run or a grading call cannot complete."""


# ------------------------------------------------------------------ model IO


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one frontier grading request in JSON mode."""
    if settings.openrouter_api_key is None:
        raise EvalError("OPENROUTER_API_KEY is not set")
    if settings.brain_frontier_model is None:
        raise EvalError("BRAIN_FRONTIER_MODEL is not set")
    response = httpx.post(
        f"{answer_mod.OPENROUTER_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={
            "model": settings.brain_frontier_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
        },
        timeout=120.0,
    )
    if response.status_code != 200:
        raise EvalError(
            f"grade call failed: {response.status_code} {response.text[:200]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise EvalError("grade response is not JSON") from exc


# ------------------------------------------------------------------- scoring


def prompt_hashes() -> dict[str, str]:
    """sha256 of every prompt that shapes an eval result."""
    return {
        name: hashlib.sha256((PROMPTS_DIR / name).read_bytes()).hexdigest()
        for name in HASHED_PROMPTS
    }


def score_grade(total: int, covered: list[int], contradicted: list[int]) -> float:
    """covered / total minus 0.2 per contradicted point, floored at 0."""
    if total <= 0:
        return 0.0
    raw = len(covered) / total - CONTRADICTION_PENALTY * len(contradicted)
    return round(max(0.0, raw), 4)


def _indexes(value: Any, total: int) -> list[int]:
    out: list[int] = []
    if not isinstance(value, list):
        return out
    for item in value:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= index < total and index not in out:
            out.append(index)
    return out


def normalize_grade(raw: dict[str, Any], total: int) -> dict[str, list[int]]:
    """Clean a grader reply: valid indexes only, each point in one list.

    Contradicted wins over covered; every point the grader skipped is missing.
    """
    if not any(key in raw for key in ("covered", "missing", "contradicted")):
        raise EvalError("grade response has no grading fields")
    if any(not isinstance(value, list) for key, value in raw.items()
           if key in ("covered", "missing", "contradicted")):
        raise EvalError("grade fields must be lists")
    contradicted = _indexes(raw.get("contradicted"), total)
    covered = [i for i in _indexes(raw.get("covered"), total) if i not in contradicted]
    missing = [i for i in range(total) if i not in covered and i not in contradicted]
    return {"covered": covered, "missing": missing, "contradicted": contradicted}


def render_grade_prompt(question: str, points: list[str], answer_md: str) -> str:
    """Fill ``prompts/grade.md`` for one answer."""
    template = GRADE_PROMPT_PATH.read_text(encoding="utf-8")
    rendered_points = "\n".join(
        f"{index}. {point}" for index, point in enumerate(points)
    )
    return (
        template.replace("{{question}}", question)
        .replace("{{points}}", rendered_points)
        .replace("{{answer}}", answer_md.strip() or "(empty answer)")
    )


def _content(body: dict[str, Any]) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise EvalError("grade response has no message content") from exc
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str):
        raise EvalError("grade response has no message content")
    return content


def grade_answer(
    question: str,
    points: list[str],
    answer_md: str,
    settings: Settings,
    usage: dict[str, int],
) -> dict[str, list[int]]:
    """Ask the frontier model which expected points the answer covers."""
    prompt = render_grade_prompt(question, points, answer_md)
    last_error: Exception | None = None
    for _attempt in range(GRADE_ATTEMPTS):
        try:
            body = _post_chat([{"role": "user", "content": prompt}], settings)
            usage["grade_calls"] = usage.get("grade_calls", 0) + 1
            tokens = (body.get("usage") or {}).get("total_tokens")
            if isinstance(tokens, int):
                usage["grade_tokens"] = usage.get("grade_tokens", 0) + tokens
            raw = parse_model_json(
                _content(body), ("covered", "missing", "contradicted")
            )
            return normalize_grade(raw, len(points))
        except (EvalError, AnswerError, httpx.HTTPError) as exc:
            logger.warning("grade call failed: %s", exc)
            last_error = exc
    raise EvalError("grading failed after retries") from last_error


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def cited_expected(expected_titles: list[str], cited_titles: list[str]) -> list[str]:
    """Expected source titles the answer cited (case-insensitive containment)."""
    folded = [_fold(title) for title in cited_titles if title.strip()]
    hits: list[str] = []
    for expected in expected_titles:
        needle = _fold(expected)
        if needle and any(needle in title or title in needle for title in folded):
            hits.append(expected)
    return hits


# ---------------------------------------------------------------------- run


def load_questions() -> list[dict[str, Any]]:
    """Every eval question, in a stable order."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text, question, expected_points, expected_source_titles, author "
            "FROM cmap.eval_question ORDER BY question"
        ).fetchall()
    return [
        {
            "id": row[0],
            "question": row[1],
            "expected_points": list(row[2]),
            "expected_source_titles": list(row[3]),
            "author": row[4],
        }
        for row in rows
    ]


def load_seed(path: Path = SEED_PATH) -> int:
    """Insert the seed questions not already present; return how many."""
    data = json.loads(path.read_text(encoding="utf-8"))
    added = 0
    with get_pool().connection() as conn:
        for item in data["questions"]:
            row = conn.execute(
                "INSERT INTO cmap.eval_question "
                "(question, expected_points, expected_source_titles, author) "
                "SELECT %s, %s, %s, %s WHERE NOT EXISTS "
                "(SELECT 1 FROM cmap.eval_question WHERE question = %s) RETURNING id",
                (
                    item["question"],
                    item["expected_points"],
                    item["expected_source_titles"],
                    SEED_AUTHOR,
                    item["question"],
                ),
            ).fetchone()
            if row is not None:
                added += 1
        conn.commit()
    return added


def _graph_version() -> int:
    with get_pool().connection() as conn:
        row = conn.execute("SELECT max(version) FROM cmap.graph_version").fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def evaluate_question(
    item: dict[str, Any], settings: Settings, usage: dict[str, int]
) -> dict[str, Any]:
    """Answer and grade one question; a failure scores 0 with the error kept."""
    points = list(item["expected_points"])
    result: dict[str, Any] = {
        "question_id": item["id"],
        "question": item["question"],
        "expected_points": points,
        "expected_sources": list(item["expected_source_titles"]),
        "score": 0.0,
        "covered": [],
        "missing": list(range(len(points))),
        "contradicted": [],
        "cited_sources": [],
        "expected_sources_cited": [],
        "mode_used": None,
        "answer_md": "",
        "error": None,
    }
    try:
        answer = answer_question(item["question"], "auto", [], settings, usage)
    except (AnswerError, EmbedError) as exc:
        result["error"] = f"answer failed: {exc}"
        return result
    markers = {int(value) for value in re.findall(r"\[(\d+)\]", answer["answer_md"])}
    titles = [
        str(cite.get("title") or "")
        for index, cite in enumerate(answer["citations"], start=1)
        if index in markers
    ]
    result["answer_md"] = answer["answer_md"]
    result["mode_used"] = answer["mode_used"]
    result["cited_sources"] = [title for title in dict.fromkeys(titles) if title]
    result["expected_sources_cited"] = cited_expected(
        result["expected_sources"], result["cited_sources"]
    )
    try:
        grade = grade_answer(
            item["question"], points, answer["answer_md"], settings, usage
        )
    except EvalError as exc:
        result["error"] = f"grading failed: {exc}"
        return result
    result.update(grade)
    result["score"] = score_grade(len(points), grade["covered"], grade["contradicted"])
    return result


def run_eval(settings: Settings | None = None) -> dict[str, Any]:
    """Answer and grade every eval question; store and return the run."""
    cfg = settings if settings is not None else get_settings()
    questions = load_questions()
    if not questions:
        raise EvalError(
            "no eval questions: add some on the eval page (or load the seed)"
        )
    usage: dict[str, int] = {}
    results = [evaluate_question(item, cfg, usage) for item in questions]
    mean = round(sum(item["score"] for item in results) / len(results), 4)
    version = _graph_version()
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.eval_run (graph_version, prompt_hashes, results, mean_score) "
            "VALUES (%s, %s, %s, %s) RETURNING id::text, created_at",
            (version, json.dumps(prompt_hashes()), json.dumps(results), mean),
        ).fetchone()
        conn.commit()
    return {
        "id": row[0],
        "created_at": row[1].isoformat(),
        "graph_version": version,
        "mean_score": mean,
        "results": results,
        "usage": usage,
    }


def handle_evaluate(job: dict[str, Any]) -> None:
    """Job ``evaluate``: one eval run; its usage lands in the job payload."""
    run = run_eval()
    job_id = job.get("id")
    if job_id is not None:
        summary = {
            "eval_run_id": run["id"],
            "mean_score": run["mean_score"],
            **run["usage"],
        }
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) "
                "WHERE id = %s",
                (json.dumps(summary), job_id),
            )
            conn.commit()
    logger.info("evaluate run=%s mean=%s", run["id"], run["mean_score"])


def main(argv: list[str] | None = None) -> int:
    """Shell entry point: ``python -m brain.eval.run [--seed]``."""
    parser = argparse.ArgumentParser(description="Run the Company Map eval.")
    parser.add_argument(
        "--seed", action="store_true", help="load the seed questions first"
    )
    args = parser.parse_args(argv)
    if args.seed:
        print(f"seed questions added: {load_seed()}")
    run = run_eval()
    for item in run["results"]:
        line = (
            f"{item['score']:.2f}  {item['question']}  "
            f"sources cited {len(item['expected_sources_cited'])}/{len(item['expected_sources'])}"
        )
        if item["error"]:
            line += f"  error={item['error']}"
        print(line)
    print(
        f"eval run {run['id']} graph_version={run['graph_version']} mean={run['mean_score']}"
    )
    print(f"usage: {run['usage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
