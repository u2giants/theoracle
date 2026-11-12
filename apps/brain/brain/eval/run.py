"""Evaluation harness: the cross-source questions (plan step 11).

``run_eval()`` answers every ``cmap.eval_question`` through the step-9
``answer_question`` (mode ``auto``), grades each answer against its expected
points with the frontier model (``prompts/grade.md``) and writes one
``cmap.eval_run`` row (repair plan B2). Score per question =
0.6 x covered points (the legacy formula: covered / total minus 0.2 per
contradicted point, floored at 0) + 0.2 x expected sources actually cited
+ 0.2 x share of sentences supported. ``score_legacy`` keeps the legacy
formula's number (also as the run's ``mean_score_legacy``) for three runs
of continuity. Abstention questions score 1 only when the answer declines
(``prompts/decline_check.md``, judged on the grade seat). A failed answer is
reported as ``error``, kept out of the mean and fails the run.

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

from brain.answer.answer import AnswerError, answer_question, parse_model_json
from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.eval.gate import run_gate
from brain.llm import post_chat_with_rescue
from brain.seats import seat_report, stage_model
from brain.text_util import split_sentences

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
GRADE_PROMPT_PATH = PROMPTS_DIR / "grade.md"
DECLINE_PROMPT_PATH = PROMPTS_DIR / "decline_check.md"
HASHED_PROMPTS = (
    "answer_local.md",
    "answer_global.md",
    "answer_map.md",
    "grade.md",
    "decline_check.md",
)
SEED_PATH = Path(__file__).resolve().parents[2] / "eval" / "questions.seed.json"
SEED_AUTHOR = "seed"
CONTRADICTION_PENALTY = 0.2
POINTS_WEIGHT = 0.6
SOURCES_WEIGHT = 0.2
SUPPORT_WEIGHT = 0.2
GRADE_ATTEMPTS = 3
MAX_TOKENS = 800
CITE_MARKER = re.compile(r"\[(\d+)\]")


class EvalError(RuntimeError):
    """Raised when an eval run or a grading call cannot complete."""


# ------------------------------------------------------------------ model IO


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one frontier grading request in JSON mode."""
    model = stage_model(settings, "grade")
    if model is None:
        raise EvalError("BRAIN_EVAL_MODEL or BRAIN_FRONTIER_MODEL is not set")
    return post_chat_with_rescue(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
        },
        settings=settings,
        timeout=120.0,
        error_cls=EvalError,
        label="grade",
    )


# ------------------------------------------------------------------- scoring


def prompt_hashes() -> dict[str, str]:
    """sha256 of every prompt that shapes an eval result."""
    return {
        name: hashlib.sha256((PROMPTS_DIR / name).read_bytes()).hexdigest()
        for name in HASHED_PROMPTS
    }


def model_manifest(settings: Settings) -> dict[str, Any]:
    """Which models produce an eval run, kept so bake-off runs compare honestly."""
    return {
        "answer": stage_model(settings, "answer"),
        "grade": stage_model(settings, "grade"),
        "stages": {stage: seat["model"] for stage, seat in seat_report(settings).items()},
        "chat": settings.brain_chat_model,
        "eval": settings.brain_eval_model,
        "frontier": settings.brain_frontier_model,
        "vision": settings.brain_vision_model,
        "embed": settings.brain_embed_model,
        "scaledown_enabled": settings.brain_scaledown_enabled,
    }


def _extraction_models() -> dict[str, int]:
    """Row counts per model behind the stored graph content."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT COALESCE(model, 'unknown'), count(*) "
            "FROM cmap.extraction GROUP BY 1"
        ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def score_grade(total: int, covered: list[int], contradicted: list[int]) -> float:
    """covered / total minus 0.2 per contradicted point, floored at 0."""
    if total <= 0:
        return 0.0
    raw = len(covered) / total - CONTRADICTION_PENALTY * len(contradicted)
    return round(max(0.0, raw), 4)


def composite_score(points: float, sources: float, support: float) -> float:
    """0.6 x covered points + 0.2 x sources cited + 0.2 x sentences supported."""
    return round(
        POINTS_WEIGHT * points + SOURCES_WEIGHT * sources + SUPPORT_WEIGHT * support,
        4,
    )


def sources_share(expected_titles: list[str], cited_hits: list[str]) -> float:
    """Fraction of expected source titles the answer cited (1.0 when none expected)."""
    if not expected_titles:
        return 1.0
    return round(len(cited_hits) / len(expected_titles), 4)


def supported_sentence_share(
    answer_md: str, citations: list[dict[str, Any]]
) -> float:
    """Share of answer sentences backed by a kept citation (H1's seam).

    Until H1's per-sentence support check lands, "supported" is the existing
    citation validity: the sentence carries a ``[n]`` marker whose citation
    survived quote validation (sentences marked ``(uncited)`` or left without
    any marker are not). H1 swaps its own check in here; the scoring formula
    does not change.
    """
    sentences = split_sentences(answer_md)
    if not sentences:
        return 0.0
    kept = len(citations)
    supported = 0
    for sentence in sentences:
        if "(uncited)" in sentence:
            continue
        if any(
            1 <= int(value) <= kept for value in CITE_MARKER.findall(sentence)
        ):
            supported += 1
    return round(supported / len(sentences), 4)


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


def render_decline_prompt(question: str, answer_md: str) -> str:
    """Fill ``prompts/decline_check.md`` for one answer."""
    template = DECLINE_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{question}}", question)
        .replace("{{answer}}", answer_md.strip() or "(empty answer)")
    )


def judge_decline(
    question: str, answer_md: str, settings: Settings, usage: dict[str, int]
) -> bool:
    """Ask the grade seat whether the answer declines to answer at all."""
    prompt = render_decline_prompt(question, answer_md)
    last_error: Exception | None = None
    for _attempt in range(GRADE_ATTEMPTS):
        try:
            body = _post_chat([{"role": "user", "content": prompt}], settings)
            usage["grade_calls"] = usage.get("grade_calls", 0) + 1
            tokens = (body.get("usage") or {}).get("total_tokens")
            if isinstance(tokens, int):
                usage["grade_tokens"] = usage.get("grade_tokens", 0) + tokens
            raw = parse_model_json(_content(body), ())
            declines = raw.get("declines")
            if not isinstance(declines, bool):
                raise AnswerError("decline response has no boolean 'declines'")
            return declines
        except (EvalError, AnswerError, httpx.HTTPError) as exc:
            logger.warning("decline check failed: %s", exc)
            last_error = exc
    raise EvalError("decline check failed after retries") from last_error


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
            "SELECT id::text, question, expected_points, expected_source_titles, "
            "author, abstention "
            "FROM cmap.eval_question ORDER BY question"
        ).fetchall()
    return [
        {
            "id": row[0],
            "question": row[1],
            "expected_points": list(row[2]),
            "expected_source_titles": list(row[3]),
            "author": row[4],
            "abstention": bool(row[5]),
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
    """Answer and grade one question; a failure records ``error`` (the run fails)."""
    points = list(item["expected_points"])
    result: dict[str, Any] = {
        "question_id": item["id"],
        "question": item["question"],
        "expected_points": points,
        "expected_sources": list(item["expected_source_titles"]),
        "abstention": bool(item["abstention"]),
        "score": 0.0,
        "score_legacy": 0.0,
        "covered": [],
        "missing": list(range(len(points))),
        "contradicted": [],
        "cited_sources": [],
        "expected_sources_cited": [],
        "supported_share": 0.0,
        "declined": None,
        "mode_used": None,
        "answer_md": "",
        "error": None,
    }
    try:
        answer = answer_question(item["question"], "auto", [], settings, usage)
    except AnswerError as exc:
        result["error"] = f"answer failed: {exc}"
        return result
    titles = [str(cite.get("title") or "") for cite in answer["citations"]]
    result["answer_md"] = answer["answer_md"]
    result["mode_used"] = answer["mode_used"]
    result["cited_sources"] = [title for title in dict.fromkeys(titles) if title]
    result["expected_sources_cited"] = cited_expected(
        result["expected_sources"], result["cited_sources"]
    )
    result["supported_share"] = supported_sentence_share(
        answer["answer_md"], answer["citations"]
    )
    if result["abstention"]:
        try:
            result["declined"] = judge_decline(
                item["question"], answer["answer_md"], settings, usage
            )
        except EvalError as exc:
            result["error"] = f"decline check failed: {exc}"
            return result
    try:
        grade = grade_answer(
            item["question"], points, answer["answer_md"], settings, usage
        )
    except EvalError as exc:
        result["error"] = f"grading failed: {exc}"
        return result
    result.update(grade)
    result["score_legacy"] = score_grade(
        len(points), grade["covered"], grade["contradicted"]
    )
    if result["abstention"]:
        result["score"] = 1.0 if result["declined"] else 0.0
    else:
        result["score"] = composite_score(
            result["score_legacy"],
            sources_share(
                result["expected_sources"], result["expected_sources_cited"]
            ),
            result["supported_share"],
        )
    return result


def run_eval(settings: Settings | None = None) -> dict[str, Any]:
    """Answer and grade every eval question; store and return the run.

    A question whose answer or grading failed keeps its ``error`` and stays
    out of ``mean_score`` (shown separately, never averaged in as a 0); the
    run is stored with its evidence and then fails.
    """
    cfg = settings if settings is not None else get_settings()
    questions = load_questions()
    if not questions:
        raise EvalError(
            "no eval questions: add some on the eval page (or load the seed)"
        )
    usage: dict[str, int] = {}
    results = [evaluate_question(item, cfg, usage) for item in questions]
    errors = [item for item in results if item["error"] is not None]
    scored = [item for item in results if item["error"] is None]
    mean = (
        round(sum(item["score"] for item in scored) / len(scored), 4) if scored else 0.0
    )
    # The legacy mean keeps the old formula's arithmetic exactly: every
    # question counts, a failure being its forced 0 (three runs of continuity).
    mean_legacy = round(
        sum(item["score_legacy"] for item in results) / len(results), 4
    )
    version = _graph_version()
    models = model_manifest(cfg)
    models["extraction_models"] = _extraction_models()
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.eval_run "
            "(graph_version, prompt_hashes, results, mean_score, models, "
            "mean_score_legacy) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id::text, created_at",
            (
                version,
                json.dumps(prompt_hashes()),
                json.dumps(results),
                mean,
                json.dumps(models),
                mean_legacy,
            ),
        ).fetchone()
        conn.commit()
    if errors:
        raise EvalError(
            f"eval run failed: {len(errors)} of {len(results)} questions errored"
        )
    # The quality gate (B3) marks this run accepted when it passes; a failing
    # run stays unaccepted and the live workflow opens the regression issue.
    decision = run_gate()
    logger.info("eval gate %s: %s", "PASS" if decision.passed else "FAIL", decision.reason)
    return {
        "id": row[0],
        "created_at": row[1].isoformat(),
        "graph_version": version,
        "mean_score": mean,
        "mean_score_legacy": mean_legacy,
        "models": models,
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
            "mean_score_legacy": run["mean_score_legacy"],
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
    try:
        run = run_eval()
    except EvalError as exc:
        print(exc)
        return 1
    for item in run["results"]:
        line = (
            f"{item['score']:.2f} (legacy {item['score_legacy']:.2f})  "
            f"{item['question']}  "
            f"sources cited {len(item['expected_sources_cited'])}/{len(item['expected_sources'])}"
        )
        if item["error"]:
            line += f"  error={item['error']}"
        print(line)
    print(
        f"eval run {run['id']} graph_version={run['graph_version']} "
        f"mean={run['mean_score']} mean_legacy={run['mean_score_legacy']}"
    )
    print(f"models: {run['models']}")
    print(f"usage: {run['usage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
