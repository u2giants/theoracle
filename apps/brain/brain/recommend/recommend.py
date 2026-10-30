"""Recommendations with competing explanations (plan step 13).

Runs after ``communities``. Every bottleneck, complaint or contradiction finding
backed by at least two distinct sources in a level-1 report or the company
report gets one frontier call (``prompts/recommend.md``) that returns the
problem, 2-4 competing explanations (one is always "the data is incomplete"),
3-5 options (one is always "no change") and one reversible experiment.
Recommendations whose ``problem`` is a cosine >= 0.9 match of one already
stored (any status, so a rejected card is never re-proposed) are dropped.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import psycopg

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import embed_texts
from brain.graph.communities import _cosine, _fit
from brain.resolve.resolve import FrontierCapReached, _Frontier

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "recommend.md"

FINDING_KINDS = ("bottleneck", "complaint", "contradiction")
MIN_SOURCES = 2
DEDUPE_COSINE = 0.9
MAX_QUOTES = 20
MIN_EXPLANATIONS = 2
MAX_EXPLANATIONS = 4
MIN_OPTIONS = 3
MAX_OPTIONS = 5
EFFORTS = ("low", "med", "high")
DEFAULT_REVIEW_DAYS = 30

INCOMPLETE_DEFAULT = (
    "The data is incomplete: the sources may not show every case, so the "
    "pattern could be smaller or larger than it looks."
)
NO_CHANGE_DEFAULT = (
    "No change: keep the current process and keep watching whether the problem "
    "recurs in new sources."
)
MEASURE_FIRST = "the metric must be measured first"
UNMEASURED = "an unmeasured amount"

_PERCENT = re.compile(
    r"[-+~]?\d+(?:[.,]\d+)?\s*(?:%|percent\b|per\s+cent\b)", re.IGNORECASE
)
_MONEY = re.compile(
    r"[$€£]\s?\d[\d,.]*(?:\s?(?:k|m|bn|million|thousand)\b)?", re.IGNORECASE
)
# A measured quantity: a money amount, or a number followed by a unit, a
# percentage or a time span. Section numbers ("4.2") and node ids ("n1") are
# not measurements.
_QUANTITY = re.compile(
    r"[$€£]\s?\d|\b\d[\d,.]*\s*(?:%|percent\b|per\s+cent\b|"
    r"(?:business\s+|working\s+|calendar\s+)?(?:days?|hours?|hrs?|weeks?|months?|"
    r"years?|minutes?|mins?)\b|units?\b|pieces?\b|pcs\b|orders?\b|times\b|x\b|k\b)",
    re.IGNORECASE,
)


def _has_numbers(texts: list[str]) -> bool:
    """True when any evidence text carries a measured count, time or amount."""
    return any(_QUANTITY.search(text) for text in texts)


def _scrub(text: str) -> str:
    """Remove invented percentages and money amounts from one text."""
    text = _PERCENT.sub(UNMEASURED, text)
    return _MONEY.sub(UNMEASURED, text)


def _source_ids(raw: Any, valid: set[str]) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        value = str(item)
        if value in valid and value not in out:
            out.append(value)
    return out


def _explanations(raw: Any, valid_sources: set[str]) -> list[dict[str, Any]]:
    """2-4 hypotheses; exactly one says the data is incomplete."""
    items: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        hypothesis = str(item.get("hypothesis") or "").strip()
        if not hypothesis:
            continue
        items.append(
            {
                "hypothesis": hypothesis,
                "support": _source_ids(item.get("support"), valid_sources),
                "against": _source_ids(item.get("against"), valid_sources),
            }
        )
    incomplete = [item for item in items if "incomplete" in item["hypothesis"].lower()]
    others = [item for item in items if item not in incomplete]
    keep = incomplete[:1] or [
        {"hypothesis": INCOMPLETE_DEFAULT, "support": [], "against": []}
    ]
    return others[: MAX_EXPLANATIONS - 1] + keep


def _options(raw: Any) -> list[dict[str, Any]]:
    """3-5 options; exactly one is "no change"."""
    items: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("option") or "").strip()
        if not text:
            continue
        effort = str(item.get("effort") or "med").strip().lower()
        no_change = bool(item.get("includes_no_change")) or text.lower().startswith(
            "no change"
        )
        items.append(
            {
                "option": text,
                "effort": effort if effort in EFFORTS else "med",
                "risk": str(item.get("risk") or "").strip(),
                "includes_no_change": no_change,
            }
        )
    keep = [item for item in items if item["includes_no_change"]][:1] or [
        {
            "option": NO_CHANGE_DEFAULT,
            "effort": "low",
            "risk": "",
            "includes_no_change": True,
        }
    ]
    changes = [item for item in items if not item["includes_no_change"]]
    return changes[: MAX_OPTIONS - 1] + keep


def _experiment(raw: Any, numbers_in_data: bool) -> dict[str, Any]:
    experiment = raw if isinstance(raw, dict) else {}
    try:
        review_days = int(experiment.get("review_after_days") or DEFAULT_REVIEW_DAYS)
    except (TypeError, ValueError):
        review_days = DEFAULT_REVIEW_DAYS
    metric = str(experiment.get("metric") or "").strip()
    baseline_needed = bool(experiment.get("baseline_needed", True))
    if not numbers_in_data:
        baseline_needed = True
        if MEASURE_FIRST not in metric.lower():
            metric = f"{metric} ({MEASURE_FIRST})" if metric else MEASURE_FIRST.capitalize()
    return {
        "change": str(experiment.get("change") or "").strip(),
        "metric": metric,
        "baseline_needed": baseline_needed,
        "review_after_days": review_days,
        "owner_role": str(experiment.get("owner_role") or "").strip(),
    }


def _normalise(
    result: dict[str, Any], valid_sources: set[str], numbers_in_data: bool
) -> dict[str, Any] | None:
    """Coerce the model answer into the ``cmap.recommendation`` columns.

    The plan's shape rules are enforced in code, not only in the prompt: one
    explanation is "the data is incomplete", one option is "no change", and
    when the evidence has no numbers no percentage or money figure survives
    and the experiment says the metric must be measured first.
    """
    problem = str(result.get("problem") or "").strip()
    if not problem:
        return None
    explanations = _explanations(result.get("explanations"), valid_sources)
    options = _options(result.get("options"))
    if len(explanations) < MIN_EXPLANATIONS or len(options) < MIN_OPTIONS:
        return None
    experiment = _experiment(result.get("experiment"), numbers_in_data)
    if not numbers_in_data:
        problem = _scrub(problem)
        for item in explanations:
            item["hypothesis"] = _scrub(item["hypothesis"])
        for item in options:
            item["option"] = _scrub(item["option"])
            item["risk"] = _scrub(item["risk"])
        experiment["change"] = _scrub(experiment["change"])
        experiment["metric"] = _scrub(experiment["metric"])
    return {
        "problem": problem,
        "explanations": explanations,
        "options": options,
        "experiment": experiment,
    }


def _candidates(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Qualifying findings from the current level-1 and company reports."""
    version_row = conn.execute("SELECT MAX(graph_version) FROM cmap.community").fetchone()
    if version_row is None or version_row[0] is None:
        return []
    rows = conn.execute(
        "SELECT id, level, title, report_md, findings, entity_ids FROM cmap.community "
        "WHERE level IN (1, 2) AND graph_version = %s ORDER BY level DESC, title",
        (int(version_row[0]),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for community_id, level, title, report_md, findings, entity_ids in rows:
        items = findings if isinstance(findings, list) else json.loads(findings or "[]")
        for finding in items:
            if not isinstance(finding, dict):
                continue
            if str(finding.get("kind") or "").strip().lower() not in FINDING_KINDS:
                continue
            sources = sorted({str(item) for item in finding.get("source_ids") or []})
            if len(sources) < MIN_SOURCES:
                continue
            out.append(
                {
                    "community_id": str(community_id),
                    "level": int(level),
                    "title": str(title or ""),
                    "report_md": str(report_md or ""),
                    "entity_ids": [str(item) for item in entity_ids or []],
                    "finding": finding,
                    "source_ids": sources,
                }
            )
    return out


def _quotes(conn: psycopg.Connection, candidate: dict[str, Any]) -> list[dict[str, str]]:
    """Quotes behind one finding: its sources' mentions of the area's entities."""
    rows = conn.execute(
        "SELECT DISTINCT ON (m.quote) m.quote, ch.source_id::text, s.title "
        "FROM cmap.mention m "
        "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
        "JOIN cmap.source s ON s.id = ch.source_id "
        "WHERE ch.source_id = ANY(%s::uuid[]) AND m.entity_id = ANY(%s::uuid[]) "
        "ORDER BY m.quote",
        (candidate["source_ids"], candidate["entity_ids"]),
    ).fetchall()
    picked: list[dict[str, str]] = []
    seen: set[str] = set()
    for quote, source_id, title in rows:
        if source_id not in seen:
            seen.add(source_id)
            picked.append({"quote": str(quote), "source_id": source_id, "title": str(title)})
    for quote, source_id, title in rows:
        if len(picked) >= MAX_QUOTES:
            break
        item = {"quote": str(quote), "source_id": source_id, "title": str(title)}
        if item not in picked:
            picked.append(item)
    return picked[:MAX_QUOTES]


def _titles(conn: psycopg.Connection, source_ids: list[str]) -> dict[str, str]:
    rows = conn.execute(
        "SELECT id::text, title FROM cmap.source WHERE id = ANY(%s::uuid[])",
        (source_ids,),
    ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def _context(
    candidate: dict[str, Any], quotes: list[dict[str, str]], titles: dict[str, str]
) -> str:
    finding = candidate["finding"]
    lines = [
        "FINDING:",
        f"[{finding.get('kind')}] {finding.get('text')} ({finding.get('stance', '')})",
        "SOURCES (cite these ids):",
    ]
    for source_id in candidate["source_ids"]:
        lines.append(f"- {source_id}: {titles.get(source_id, '(untitled)')}")
    lines.append("QUOTES:")
    for item in quotes:
        lines.append(f'- [{item["source_id"]}] "{item["quote"]}"')
    lines.append(f"AREA REPORT ({candidate['title']}):")
    lines.append(candidate["report_md"])
    return _fit(lines)


def _store(conn: psycopg.Connection, community_id: str, rec: dict[str, Any]) -> str:
    row = conn.execute(
        "INSERT INTO cmap.recommendation (community_id, problem, explanations, options, "
        "experiment) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (
            community_id,
            rec["problem"],
            json.dumps(rec["explanations"], ensure_ascii=False),
            json.dumps(rec["options"], ensure_ascii=False),
            json.dumps(rec["experiment"], ensure_ascii=False),
        ),
    ).fetchone()
    return str(row[0])


def _existing_block(problems: list[str]) -> str:
    """Numbered DATA list of problems already recommended (or ``none``)."""
    if not problems:
        return "none"
    return "\n".join(f"{index}. {text}" for index, text in enumerate(problems, 1))


def _duplicate_index(raw: Any, total: int) -> int | None:
    """The 1-based existing-problem number the model marked, if any is valid."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        index = raw
    elif isinstance(raw, float) and raw.is_integer():
        index = int(raw)
    elif isinstance(raw, str) and raw.strip().isdigit():
        index = int(raw.strip())
    else:
        return None
    return index if 1 <= index <= total else None


def run_recommend(settings: Settings | None = None) -> dict[str, Any]:
    """Write one deduplicated recommendation per qualifying finding."""
    cfg = settings if settings is not None else get_settings()
    frontier = _Frontier(cfg)
    template = PROMPT_PATH.read_text(encoding="utf-8")
    stats: dict[str, Any] = {
        "candidates": 0,
        "recommendations": 0,
        "duplicates": 0,
        "failed": 0,
        "capped": False,
    }
    with get_pool(cfg).connection() as conn:
        candidates = _candidates(conn)
        stats["candidates"] = len(candidates)
        existing_problems = [
            str(row[0])
            for row in conn.execute("SELECT problem FROM cmap.recommendation").fetchall()
        ]
        existing_vectors = embed_texts(existing_problems, cfg) if existing_problems else []
        for candidate in candidates:
            titles = _titles(conn, candidate["source_ids"])
            quotes = _quotes(conn, candidate)
            evidence = [str(candidate["finding"].get("text") or "")]
            evidence.extend(item["quote"] for item in quotes)
            prompt = (
                template.replace("{{context}}", _context(candidate, quotes, titles))
                .replace("{{existing_problems}}", _existing_block(existing_problems))
            )
            try:
                result = frontier.ask(prompt)
            except FrontierCapReached:
                stats["capped"] = True
                break
            except Exception as exc:
                logger.warning("recommendation failed: %s", exc)
                stats["failed"] += 1
                continue
            if _duplicate_index(result.get("duplicate_of"), len(existing_problems)):
                stats["duplicates"] += 1
                continue
            rec = _normalise(result, set(titles), _has_numbers(evidence))
            if rec is None:
                stats["failed"] += 1
                continue
            vector = embed_texts([rec["problem"]], cfg)[0]
            if any(_cosine(vector, other) >= DEDUPE_COSINE for other in existing_vectors):
                stats["duplicates"] += 1
                continue
            _store(conn, candidate["community_id"], rec)
            conn.commit()
            existing_problems.append(rec["problem"])
            existing_vectors.append(vector)
            stats["recommendations"] += 1
    stats.update(frontier.usage)
    return stats


def handle_recommend(job: dict[str, Any]) -> None:
    """Job ``recommend``: recommendations for the current map's problems."""
    stats = run_recommend()
    job_id = job.get("id")
    if job_id is not None:
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) "
                "WHERE id = %s",
                (json.dumps(stats), job_id),
            )
            conn.commit()
    logger.info("recommend stats=%s", stats)
