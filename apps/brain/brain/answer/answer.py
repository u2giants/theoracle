"""Question answering over the company map: local and global modes (plan step 9).

``POST /answer`` asks one question in one of three modes:

- ``local`` — embed the question, take the nearest entities and their depth-2
  graph neighbourhood (60 nodes / 150 edges, edges ranked by weight), retrieve
  chunks by cosine from the edge sources plus the open corpus, compress the
  passages with ScaleDown ``/compress/raw/`` when they exceed the token
  threshold (the quotes list stays uncompressed for citation), and answer from
  ``prompts/answer_local.md``.
- ``global`` — map-reduce over the level-1 community reports and the company
  report (``prompts/answer_map.md`` per batch of 10 when they exceed the
  one-call budget, then ``prompts/answer_global.md``), citing finding
  source_ids resolved to titles and the chunk nearest each answer paragraph.
- ``auto`` — ScaleDown classifies the question ``specific``/``broad``; a top
  score under 0.6 runs both modes and merges.

Citations are validated: a local quote must be a substring of its chunk or the
citation is dropped, and a sentence left without any citation is marked
``(uncited)`` rather than deleted. History is the request's last turns only —
there is no server-side session store.

H1 — every sentence supported or marked. After drafting, each sentence's
cited quotes are checked on the flat seat (``prompts/support_check.md``) for
support: ``supported`` / ``partly`` / ``not``. A sentence that is not fully
supported is rewritten once with that evidence (``prompts/support_rewrite.md``;
the rewrite is adopted only when a re-check finds it supported) and otherwise
shown with ``(unsupported — my inference)``; a sentence whose check did not run
is shown with ``(verifying)``. The supported share is returned with the answer
as ``supported_share`` and scored by B2 (``supported_share_of``). Company-wide
citations may name only sources present in the prompt and show the supporting
evidence text from that prompt, never the nearest chunk.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from brain.config import Settings, get_settings
from brain.contradictions import disagreement_lines
from brain.corrections import (
    apply_edge_edit,
    entity_key,
    entity_key_sets,
    load_corrections,
)
from brain.db import get_pool
from brain.embed import embed_texts, vector_literal
from brain.extract import flat as flat_mod
from brain.extract.relations import DEFAULT_MAX_FRONTIER_CALLS, _complete_items
from brain.graph.communities import _tokens
from brain.graph.project import connect as connect_graph
from brain.graph.version import current_graph_version
from brain.llm import post_chat_with_rescue
from brain.seats import stage_model
from brain.text_util import fold_key, sentence_slices
from brain.versions import superseded_source_ids

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
LOCAL_PROMPT_PATH = PROMPTS_DIR / "answer_local.md"
GLOBAL_PROMPT_PATH = PROMPTS_DIR / "answer_global.md"
MAP_PROMPT_PATH = PROMPTS_DIR / "answer_map.md"
SUPPORT_CHECK_PROMPT_PATH = PROMPTS_DIR / "support_check.md"
SUPPORT_REWRITE_PROMPT_PATH = PROMPTS_DIR / "support_rewrite.md"

TOP_ENTITIES = 8
GRAPH_NODE_CAP = 60
GRAPH_EDGE_CAP = 150
CHUNKS_RESTRICTED = 20
CHUNKS_UNRESTRICTED = 10
COMPRESS_MIN_TOKENS = 6000
GLOBAL_ONE_SHOT_TOKENS = 60000
MAP_BATCH = 10
HISTORY_TURNS = 6
ROUTE_MIN_SCORE = 0.6
MAX_TOKENS = 8000
ASK_ATTEMPTS = 3

# H1 sentence support checks (plan Phase H): one flat-seat call per sentence,
# run in parallel. Above SUPPORT_PARALLEL_MAX checked sentences the staged
# path checks sentences carrying numbers, names or negations first and marks
# the rest ``(verifying)`` when the p95 budget (plan §13) is spent.
SUPPORT_ATTEMPTS = 3
SUPPORT_MAX_TOKENS = 400
SUPPORT_PARALLEL = 8
SUPPORT_PARALLEL_MAX = 24
SUPPORT_BUDGET_S = 12.0
SUPPORT_VERDICTS = ("supported", "partly", "not")
UNCITED_TAG = "(uncited)"
UNSUPPORTED_TAG = "(unsupported — my inference)"
VERIFYING_TAG = "(verifying)"
SUPPORT_TAGS = (UNSUPPORTED_TAG, UNCITED_TAG, VERIFYING_TAG)
_NEGATION = re.compile(
    r"\b(no|not|never|without|nobody|nothing|none|neither|nor|cannot|"
    r"can't|don't|doesn't|isn't|aren't|wasn't|weren't|won't|shouldn't|"
    r"wouldn't|couldn't)\b",
    re.IGNORECASE,
)
_CJK_NEGATION = re.compile(r"[未不无没非勿]")
_NAME = re.compile(r"\b[A-Z][a-z]{2,}\b")

ROUTE_LABELS: list[dict[str, str]] = [
    {
        "name": "specific",
        "rubric": (
            "asks about a particular person, process, system, document or step. "
            "具体问题/事实查询"
        ),
    },
    {
        "name": "broad",
        "rubric": (
            "asks about patterns, biggest problems, overview, 'across the "
            "company', comparisons between departments. 全局/跨部门梳理"
        ),
    },
]

_MARKER = re.compile(r"\[(\d+)\]")
# A trailing [n] or support-mark run belongs to the sentence before it:
# _renumber writes "text. [1]" and the marks land the same way.
_RUN_PIECE = (
    r"(?:\[\d+\]|"
    + re.escape(UNSUPPORTED_TAG)
    + "|"
    + re.escape(UNCITED_TAG)
    + "|"
    + re.escape(VERIFYING_TAG)
    + r")"
)
_LEADING_MARKER_RUN = re.compile(rf"^(?:\s*{_RUN_PIECE})+")

# D2 history-reach seam: a question explicitly about the past may surface
# superseded facts (labelled as history); anything else is current-only.
_HISTORY_MARKERS = (
    "until",
    "before ",
    "back when",
    "back then",
    "used to",
    "formerly",
    "previously",
    "old version",
    "older version",
    "previous version",
    "old rule",
    "earlier rule",
    "earlier version",
    "history",
    "historical",
    "no longer",
    "in those days",
    "at the time",
    "prior to",
    "as it was",
    "what changed",
    "how did it work",
)
_HISTORY_PREFIX = "[SUPERSEDED VERSION — shown because this question is about the past]\n"


def is_history_question(question: str) -> bool:
    """True when the question explicitly asks about how things used to be."""
    folded = " " + question.casefold()
    return any(marker in folded for marker in _HISTORY_MARKERS)


class AnswerError(RuntimeError):
    """Raised when a question cannot be answered."""


class AnswerCapReached(AnswerError):
    """Raised when ``BRAIN_MAX_FRONTIER_CALLS_PER_JOB`` is used up."""


# ------------------------------------------------------------------ model IO


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one frontier chat-completions request in JSON mode."""
    model = stage_model(settings, "answer")
    if model is None:
        raise AnswerError("BRAIN_CHAT_MODEL or BRAIN_FRONTIER_MODEL is not set")
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
        error_cls=AnswerError,
        label="frontier answer",
    )


def _post_scaledown(
    path: str, body: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    """POST one ScaleDown call (classify or compress) and return its JSON body."""
    if settings.scaledown_api_key is None:
        raise AnswerError("SCALEDOWN_API_KEY is not set")
    response = httpx.post(
        f"{flat_mod.SCALEDOWN_BASE_URL}{path}",
        headers={"x-api-key": settings.scaledown_api_key},
        json=body,
        timeout=120.0,
    )
    if response.status_code != 200:
        raise AnswerError(
            f"scaledown {path} failed: {response.status_code} {response.text[:200]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise AnswerError(f"scaledown {path} response is not JSON") from exc
    if not isinstance(payload, dict):
        raise AnswerError(f"scaledown {path} response is not a JSON object")
    return payload


def parse_model_json(content: str, list_fields: tuple[str, ...]) -> dict[str, Any]:
    """Parse one model JSON object, salvaging fields out of cut-off output.

    Same robustness chain as steps 5-8: tolerate a code fence, trailing
    commas and content returned as text blocks; salvage the known fields when
    the closing brace never arrived.
    """
    text = content.strip()
    fenced = re.fullmatch(r"```[a-zA-Z]*\n(.*?)\n?```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        body = re.sub(r",(\s*[}\]])", r"\1", text[start : end + 1])
        try:
            value = json.loads(body, strict=False)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
    salvaged: dict[str, Any] = {}
    match = re.search(r'"answer_md"\s*:\s*("(?:[^"\\]|\\.)*")', text)
    if match is not None:
        try:
            salvaged["answer_md"] = json.loads(match.group(1))
        except json.JSONDecodeError:
            salvaged["answer_md"] = match.group(1).strip('"')
    for name in list_fields:
        items = _complete_items(text, name)
        if items:
            salvaged[name] = items
    if salvaged:
        salvaged["truncated"] = True
        return salvaged
    raise AnswerError(f"answer response is not JSON: {content[:300]!r}")


def _ask(prompt: str, settings: Settings, usage: dict[str, int]) -> dict[str, Any]:
    """One JSON answer from the frontier model, retrying transient failures."""
    last_error: Exception | None = None
    for _attempt in range(ASK_ATTEMPTS):
        try:
            return _ask_once(prompt, settings, usage)
        except AnswerCapReached:
            raise
        except (AnswerError, httpx.HTTPError) as exc:
            logger.warning("answer call failed: %s", exc)
            last_error = exc
    raise AnswerError("frontier answer failed after retries") from last_error


def _ask_once(prompt: str, settings: Settings, usage: dict[str, int]) -> dict[str, Any]:
    cap = settings.brain_max_frontier_calls_per_job
    if cap is None:
        cap = DEFAULT_MAX_FRONTIER_CALLS
    used = usage.get("frontier_calls", 0)
    if used >= cap:
        raise AnswerCapReached(
            f"BRAIN_MAX_FRONTIER_CALLS_PER_JOB cap of {cap} reached while answering"
        )
    usage["frontier_calls"] = used + 1
    body = _post_chat([{"role": "user", "content": prompt}], settings)
    tokens = (body.get("usage") or {}).get("total_tokens")
    if isinstance(tokens, int):
        usage["frontier_tokens"] = usage.get("frontier_tokens", 0) + tokens
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AnswerError("frontier answer response has no message content") from exc
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    if content is None:
        raise AnswerError("frontier answer response has no message content")
    if not isinstance(content, str):
        raise AnswerError("frontier answer response has no message content")
    return parse_model_json(content, ("citations", "unknowns", "points"))


# ------------------------------------------------------- flat support checks


def _post_flat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one flat-seat JSON request (H1's sentence checks and rewrites)."""
    model = stage_model(settings, "flat")
    if model is None:
        raise AnswerError("BRAIN_FLAT_MODEL or BRAIN_FRONTIER_MODEL is not set")
    return post_chat_with_rescue(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": SUPPORT_MAX_TOKENS,
            "response_format": {"type": "json_object"},
        },
        settings=settings,
        timeout=60.0,
        error_cls=AnswerError,
        label="flat support",
    )


def _flat_json_field(content: str, field: str) -> str | None:
    """One string field out of a flat-seat JSON reply, salvaging like step 9."""
    text = content.strip()
    fenced = re.fullmatch(r"```[a-zA-Z]*\n(.*?)\n?```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        body = re.sub(r",(\s*[}\]])", r"\1", text[start : end + 1])
        try:
            value = json.loads(body, strict=False)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict) and isinstance(value.get(field), str):
            return str(value[field])
    match = re.search(rf'"{field}"\s*:\s*"([^"]*)"', text)
    if match is not None:
        return match.group(1)
    return None


def _flat_ask(
    prompt: str, settings: Settings, field: str
) -> tuple[str | None, int]:
    """One flat-seat JSON reply after retries; ``(value, tokens)``, value None on failure."""
    total = 0
    for _attempt in range(SUPPORT_ATTEMPTS):
        try:
            body = _post_flat([{"role": "user", "content": prompt}], settings)
        except (AnswerError, httpx.HTTPError) as exc:
            logger.warning("flat support call failed: %s", exc)
            continue
        tokens = (body.get("usage") or {}).get("total_tokens")
        if isinstance(tokens, int):
            total += tokens
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            continue
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str):
            continue
        value = _flat_json_field(content, field)
        if value is not None:
            return value, total
    return None, total


def _render_support(template: str, sentence: str, quotes: list[str]) -> str:
    """Fill a support prompt's sentence and evidence slots."""
    return (
        template.replace("{{sentence}}", sentence).replace(
            "{{evidence}}", "\n\n".join(quote for quote in quotes if quote)
        )
    )


def _support_verdict(
    sentence: str, quotes: list[str], settings: Settings
) -> tuple[str | None, int]:
    """``supported`` / ``partly`` / ``not`` for one sentence; None when unverifiable."""
    prompt = _render_support(
        SUPPORT_CHECK_PROMPT_PATH.read_text(encoding="utf-8"), sentence, quotes
    )
    raw, tokens = _flat_ask(prompt, settings, "support")
    verdict = (raw or "").strip().casefold()
    if verdict in SUPPORT_VERDICTS:
        return verdict, tokens
    return None, tokens


def _rewrite_sentence(
    sentence: str, quotes: list[str], settings: Settings
) -> tuple[str | None, int]:
    """One rewrite attempt of a sentence against its evidence; None on failure."""
    prompt = _render_support(
        SUPPORT_REWRITE_PROMPT_PATH.read_text(encoding="utf-8"), sentence, quotes
    )
    return _flat_ask(prompt, settings, "sentence")


def _has_words(text: str) -> bool:
    """True when the text holds letters or CJK — a real sentence, not a marker run."""
    return any(ch.isalpha() for ch in text)


def _needs_priority(sentence: str) -> bool:
    """Numbers, names or negations: the sentences checked first on the staged path."""
    bare = _MARKER.sub("", sentence)
    if re.search(r"\d", bare):
        return True
    if _NEGATION.search(bare) or _CJK_NEGATION.search(bare):
        return True
    words = _NAME.findall(bare)
    return any(words[1:])


def supported_share_of(answer_md: str, citations: list[dict[str, Any]]) -> float:
    """Share of sentences H1 found supported — the number returned and scored.

    A sentence counts as supported when it carries a kept ``[n]`` marker and
    none of H1's marks (``(unsupported — my inference)`` after the rewrite
    attempt, ``(uncited)`` when it has no citation, ``(verifying)`` when the
    check did not run). Fragment runs without letters (list numbering) are
    not sentences and stay out of the count. This is what B2's
    ``supported_sentence_share`` seam reads.
    """
    sentences = [s for s, _sep in _support_slices(answer_md) if _has_words(s)]
    if not sentences:
        return 0.0
    kept = len(citations)
    supported = 0
    for sentence in sentences:
        if any(tag in sentence for tag in SUPPORT_TAGS):
            continue
        if any(
            1 <= int(value) <= kept for value in _MARKER.findall(sentence)
        ):
            supported += 1
    return round(supported / len(sentences), 4)


def _check_wave(
    items: list[tuple[int, str, list[str]]], settings: Settings
) -> tuple[dict[int, str | None], int]:
    """Run the support checks of one wave in parallel on the flat seat."""
    verdicts: dict[int, str | None] = {}
    tokens = 0
    if not items:
        return verdicts, tokens
    workers = min(SUPPORT_PARALLEL, len(items))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_support_verdict, sentence, quotes, settings): index
            for index, sentence, quotes in items
        }
        for future in as_completed(futures):
            verdict, used = future.result()
            verdicts[futures[future]] = verdict
            tokens += used
    return verdicts, tokens


def _run_checks(
    items: list[tuple[int, str, list[str]]], settings: Settings
) -> tuple[dict[int, str | None], int]:
    """Parallel checks; staged priority-first above the cap (plan §13 latency).

    The simple parallel path ships for up to ``SUPPORT_PARALLEL_MAX`` checked
    sentences. Above that, sentences carrying numbers, names or negations are
    checked first and the rest only while the p95 budget holds; anything
    unchecked is marked ``(verifying)`` (the visible fallback — no background
    job fills it in later).
    """
    if len(items) <= SUPPORT_PARALLEL_MAX:
        return _check_wave(items, settings)
    priority = [item for item in items if _needs_priority(item[1])]
    rest = [item for item in items if not _needs_priority(item[1])]
    started = time.monotonic()
    verdicts, tokens = _check_wave(priority, settings)
    if time.monotonic() - started < SUPPORT_BUDGET_S:
        more, more_tokens = _check_wave(rest, settings)
        verdicts.update(more)
        return verdicts, tokens + more_tokens
    for index, _sentence, _quotes in rest:
        verdicts[index] = None
    return verdicts, tokens


def _verify_support(
    result: dict[str, Any], settings: Settings, usage: dict[str, int]
) -> dict[str, Any]:
    """H1: check every cited sentence, rewrite once, mark what stays unsupported.

    Policy: a sentence the cited quotes do not fully support (``partly`` or
    ``not``) is rewritten once with that evidence; the rewrite is adopted only
    when a re-check finds it ``supported``, otherwise the original sentence is
    shown with ``(unsupported — my inference)`` (never deleted — the marks are
    the contract the docstring promises). Sentences without citations were
    already marked ``(uncited)`` by ``_renumber``; a sentence whose check did
    not complete is marked ``(verifying)`` and never counted supported.
    """
    answer_md = str(result.get("answer_md") or "")
    citations = [
        item for item in (result.get("citations") or []) if isinstance(item, dict)
    ]
    slices = _support_slices(answer_md)
    planned: list[tuple[int, str, list[str]]] = []
    for index, (sentence, _separator) in enumerate(slices):
        if not _has_words(sentence):
            continue
        found = [int(value) for value in _MARKER.findall(sentence)]
        quotes = [
            str(citations[value - 1].get("quote") or "")
            for value in found
            if 1 <= value <= len(citations)
        ]
        if not quotes:
            continue
        planned.append((index, sentence, quotes))
    verdicts: dict[int, str | None] = {}
    tokens = 0
    rewrite_calls = 0
    if planned:
        verdicts, tokens = _run_checks(planned, settings)
    quotes_by_index = {index: quotes for index, _sentence, quotes in planned}
    sentence_by_index = {index: sentence for index, sentence, _quotes in planned}
    failed = [
        index
        for index, _sentence, _quotes in planned
        if verdicts.get(index) in ("partly", "not")
    ]
    adopted: dict[int, str] = {}
    rechecks: list[tuple[int, str, list[str]]] = []
    if failed:
        rewrites: dict[int, str | None] = {}
        rewrite_tokens = 0
        with ThreadPoolExecutor(
            max_workers=min(SUPPORT_PARALLEL, len(failed))
        ) as pool:
            futures = {
                pool.submit(
                    _rewrite_sentence,
                    sentence_by_index[index],
                    quotes_by_index[index],
                    settings,
                ): index
                for index in failed
            }
            for future in as_completed(futures):
                value, used = future.result()
                rewrites[futures[future]] = value
                rewrite_tokens += used
        tokens += rewrite_tokens
        rewrite_calls = len(failed)
        for index in failed:
            rewritten = rewrites.get(index)
            original = sentence_by_index[index]
            if rewritten is None:
                continue
            if sorted(_MARKER.findall(rewritten)) != sorted(
                _MARKER.findall(original)
            ):
                continue
            rechecks.append((index, rewritten, quotes_by_index[index]))
        if rechecks:
            recheck_verdicts, recheck_tokens = _check_wave(rechecks, settings)
            tokens += recheck_tokens
            for index, rewritten, _quotes in rechecks:
                if recheck_verdicts.get(index) == "supported":
                    adopted[index] = rewritten
    pieces: list[str] = []
    for index, (sentence, separator) in enumerate(slices):
        if index in adopted:
            pieces.append(adopted[index] + separator)
        elif index in failed and index not in adopted:
            pieces.append(sentence + " " + UNSUPPORTED_TAG + separator)
        elif planned and index in sentence_by_index and verdicts.get(index) is None:
            pieces.append(sentence + " " + VERIFYING_TAG + separator)
        else:
            pieces.append(sentence + separator)
    result["answer_md"] = "".join(pieces)
    result["supported_share"] = supported_share_of(result["answer_md"], citations)
    usage["support_calls"] = (
        usage.get("support_calls", 0) + len(planned) + len(rechecks)
    )
    usage["rewrite_calls"] = usage.get("rewrite_calls", 0) + rewrite_calls
    usage["support_tokens"] = usage.get("support_tokens", 0) + tokens
    return result


# ------------------------------------------------------------------- routing


def _route_mode(question: str, settings: Settings, usage: dict[str, int]) -> str:
    """ScaleDown ``specific``/``broad`` classify; low confidence runs both."""
    if not settings.brain_scaledown_enabled or settings.scaledown_api_key is None:
        return "both"
    usage["scaledown_classify_calls"] = usage.get("scaledown_classify_calls", 0) + 1
    try:
        payload = _post_scaledown(
            "/classify",
            {"text": question, "labels": ROUTE_LABELS},
            settings,
        )
    except AnswerError as exc:
        logger.warning("route classify failed (%s); running both modes", exc)
        return "both"
    top = payload.get("top_label")
    scores_raw = payload.get("scores")
    scores: dict[str, float] = {}
    if isinstance(scores_raw, dict):
        for key, value in scores_raw.items():
            try:
                scores[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    score = scores.get(str(top), 0.0)
    if score < ROUTE_MIN_SCORE:
        return "both"
    if top == "specific":
        return "local"
    if top == "broad":
        return "global"
    return "both"


# ---------------------------------------------------------------- citations


def _sentence_slices(text: str) -> list[tuple[str, str]]:
    """Split into ``(sentence, separator)`` pairs, keeping the whitespace."""
    return sentence_slices(text)


def _support_slices(text: str) -> list[tuple[str, str]]:
    """Sentence slices with trailing ``[n]`` runs folded onto their sentence.

    ``_renumber`` writes kept markers after the sentence's final stop
    ("text. [1]"), which a plain split strands as the next fragment's head
    (and splits the CJK "…。[1]" form outright). This folds each leading
    marker run back onto the sentence it belongs to so checks, marks and the
    supported share see "text. [1]" as one unit. Round-trips exactly.
    """
    out: list[list[str]] = []
    for sentence, separator in _sentence_slices(text):
        match = _LEADING_MARKER_RUN.match(sentence) if out else None
        if match is None:
            out.append([sentence, separator])
            continue
        run = match.group(0)
        rest = sentence[match.end() :]
        previous, previous_separator = out[-1]
        out[-1] = [previous + previous_separator + run, ""]
        if rest.strip():
            out.append([rest, separator])
        elif rest or separator:
            out[-1][1] = rest + separator
    return [(sentence, separator) for sentence, separator in out]


def _renumber(answer_md: str, old_to_new: dict[int, int]) -> str:
    """Rewrite [n] markers to the filtered citation numbers.

    A marker whose citation was dropped disappears; a sentence left without
    any citation at all is marked ``(uncited)`` rather than deleted (plan
    step 9.6, H1). Fragment runs without letters (list numbering) are not
    sentences and pass through untouched.
    """
    pieces: list[str] = []
    for sentence, separator in _support_slices(answer_md):
        found = [int(value) for value in _MARKER.findall(sentence)]
        if not found:
            if _has_words(sentence):
                pieces.append(sentence + " " + UNCITED_TAG + separator)
            else:
                pieces.append(sentence + separator)
            continue
        kept = [value for value in found if value in old_to_new]
        stripped = re.sub(r"\s*\[\d+\]", "", sentence)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip()
        if kept:
            markers = "".join(f" [{old_to_new[value]}]" for value in kept)
            pieces.append(stripped + markers + separator)
        else:
            pieces.append(stripped + " " + UNCITED_TAG + separator)
    return "".join(pieces)


def _finalize_local(
    answer_md: str,
    raw_citations: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Validate quotes against their chunks; drop invalid; renumber markers."""
    by_id = {chunk["id"]: chunk for chunk in chunks}
    kept: list[dict[str, Any]] = []
    old_to_new: dict[int, int] = {}
    for index, cite in enumerate(raw_citations, start=1):
        chunk_id = str(cite.get("chunk_id") or "")
        quote = str(cite.get("quote") or "")
        chunk = by_id.get(chunk_id)
        if chunk is None or not quote or quote not in chunk["text"]:
            continue
        kept.append(
            {
                "source_id": chunk["source_id"],
                "title": chunk["title"],
                "chunk_id": chunk_id,
                "quote": quote,
                "locator": chunk["locator"],
            }
        )
        old_to_new[index] = len(kept)
    return _renumber(answer_md, old_to_new), kept


def _supporting_text(paragraph: str, candidates: list[str]) -> str:
    """The candidate evidence text that shares the most words with the paragraph."""
    if len(candidates) == 1:
        return candidates[0]
    paragraph_words = set(fold_key(paragraph).split())
    best = candidates[0]
    best_score = -1
    for candidate in candidates:
        score = len(paragraph_words & set(fold_key(candidate).split()))
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _finalize_global(
    answer_md: str,
    raw_citations: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Keep only citations to sources the prompt showed; quote the evidence.

    H1: a company-wide citation may name only a source present in the prompt
    (the ``source_ids`` of the rendered findings or mapped points) and its
    quote is that prompt's supporting evidence text — never the nearest
    chunk of the source, which was never shown to the model.
    """
    allowed: set[str] = set()
    texts_by_source: dict[str, list[str]] = {}
    for item in evidence:
        text = str(item.get("text") or "")
        for raw_id in item.get("source_ids") or []:
            source_id = str(raw_id)
            if not source_id:
                continue
            allowed.add(source_id)
            texts_by_source.setdefault(source_id, []).append(text)
    kept: list[dict[str, Any]] = []
    old_to_new: dict[int, int] = {}
    with get_pool().connection() as conn:
        for index, cite in enumerate(raw_citations, start=1):
            source_id = str(cite.get("source_id") or "")
            if source_id not in allowed:
                continue
            try:
                uuid.UUID(source_id)
            except ValueError:
                # Models sometimes cite a word ("REPORTS") instead of a real id;
                # those citations are dropped like any other invalid one.
                continue
            row = conn.execute(
                "SELECT title FROM cmap.source WHERE id = %s",
                (source_id,),
            ).fetchone()
            if row is None:
                continue
            marker = f"[{index}]"
            paragraph = answer_md
            for sentence, _separator in _sentence_slices(answer_md):
                if marker in sentence:
                    paragraph = sentence
                    break
            kept.append(
                {
                    "source_id": source_id,
                    "title": str(row[0]),
                    "chunk_id": None,
                    "quote": _supporting_text(
                        paragraph, texts_by_source[source_id]
                    ),
                    "locator": None,
                }
            )
            old_to_new[index] = len(kept)
    return _renumber(answer_md, old_to_new), kept


# -------------------------------------------------------------------- local


def _fold_question(question: str) -> str:
    """Casefold and strip punctuation so alias names can appear-match."""
    return fold_key(question)


def _select_entities(
    question: str, vector: list[float], include_history: bool = False
) -> list[dict[str, Any]]:
    """Top-8 entities by embedding cosine, plus any entity whose alias appears.

    D2: an entity whose only mentions sit in superseded sources is history and
    is left out unless the question is about the past.
    """
    folded = _fold_question(question)
    live = (
        ""
        if include_history
        else " AND EXISTS (SELECT 1 FROM cmap.mention m "
        "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
        "WHERE m.entity_id = e.id AND ch.source_id NOT IN "
        "(SELECT supersedes_source_id FROM cmap.source_version "
        "WHERE decided_at IS NOT NULL))"
    )
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT e.id::text, e.entity_type, e.canonical_name, e.description, "
            "e.mention_count, e.source_count "
            "FROM cmap.entity e WHERE e.embedding IS NOT NULL" + live + " "
            "ORDER BY e.embedding <=> %s::vector LIMIT %s",
            (vector_literal(vector), TOP_ENTITIES),
        ).fetchall()
        alias_rows = conn.execute(
            "SELECT DISTINCT e.id::text, e.entity_type, e.canonical_name, "
            "e.description, e.mention_count, e.source_count "
            "FROM cmap.entity e "
            "JOIN cmap.entity_alias a ON a.entity_id = e.id "
            "WHERE a.normalized_name <> '' AND position(a.normalized_name IN %s) > 0"
            + live,
            (folded,),
        ).fetchall()
    seen: dict[str, dict[str, Any]] = {}
    for row in list(rows) + list(alias_rows):
        entity_id = str(row[0])
        if entity_id in seen:
            continue
        seen[entity_id] = {
            "id": entity_id,
            "type": str(row[1]),
            "name": str(row[2]),
            "description": str(row[3] or ""),
            "mention_count": int(row[4]),
            "source_count": int(row[5]),
        }
    return list(seen.values())


def _apply_fact_corrections(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """G1: human corrections win in the answer context (plan Phase G).

    A rejected entity or relation never reaches the answer; an ``edit``
    correction replaces the fact's fields; a ``confirm``ed fact ranks first.
    """
    with get_pool().connection() as conn:
        corrections = load_corrections(conn)
        key_sets = entity_key_sets(conn, sorted({str(node["id"]) for node in nodes}))
    keys_by_id: dict[str, set[str]] = {}
    confirmed_nodes: list[dict[str, Any]] = []
    kept_nodes: list[dict[str, Any]] = []
    dropped: set[str] = set()
    for node in nodes:
        node_id = str(node["id"])
        keys = set(key_sets.get(node_id, set()))
        keys.add(entity_key(str(node["name"]), str(node["type"])))
        keys_by_id[node_id] = keys
        verdict = corrections.verdict_for(keys)
        if verdict is not None and verdict.action == "reject":
            dropped.add(node_id)
            continue
        rename = corrections.rename_for(keys)
        if rename is not None:
            node["name"] = str(rename.payload.get("name") or node["name"])
        edit = corrections.edit_for(keys)
        if edit is not None:
            if "name" in edit.payload:
                node["name"] = str(edit.payload["name"])
            if "description" in edit.payload:
                node["description"] = str(edit.payload["description"])
        if verdict is not None and verdict.action == "confirm":
            confirmed_nodes.append(node)
        else:
            kept_nodes.append(node)
    confirmed_edges: list[dict[str, Any]] = []
    kept_edges: list[dict[str, Any]] = []
    for edge in edges:
        if str(edge["from"]) in dropped or str(edge["to"]) in dropped:
            continue
        from_keys = keys_by_id.get(str(edge["from"]), set())
        to_keys = keys_by_id.get(str(edge["to"]), set())
        rel_type = str(edge["rel_type"])
        verdict = corrections.relation_verdict_for(from_keys, to_keys, rel_type)
        if verdict is not None and verdict.action == "reject":
            continue
        edit = corrections.relation_edit_for(from_keys, to_keys, rel_type)
        if edit is not None:
            apply_edge_edit(edge, edit.payload)
        if verdict is not None and verdict.action == "confirm":
            confirmed_edges.append(edge)
        else:
            kept_edges.append(edge)
    return confirmed_nodes + kept_nodes, confirmed_edges + kept_edges


def _graph_context(
    entities: list[dict[str, Any]], settings: Settings
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Depth-2 neighbourhood of the seeds: capped nodes and weight-ranked edges."""
    ids = [entity["id"] for entity in entities]
    graph = connect_graph(settings)
    result = graph.query(
        "MATCH (a:Entity)-[*1..2]-(x:Entity) WHERE a.id IN $ids "
        "RETURN DISTINCT x "
        "ORDER BY x.source_count DESC, x.mention_count DESC LIMIT $limit",
        {"ids": ids, "limit": GRAPH_NODE_CAP},
    )
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entity in entities:
        seen.add(entity["id"])
        nodes.append(
            {
                "id": entity["id"],
                "type": entity["type"],
                "name": entity["name"],
                "description": entity["description"],
            }
        )
    for row in result.result_set:
        node = row[0]
        node_id = str(node.properties.get("id"))
        if node_id in seen:
            continue
        seen.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "type": str(node.properties.get("type")),
                "name": str(node.properties.get("name")),
                "description": str(node.properties.get("description") or ""),
            }
        )
    nodes = nodes[:GRAPH_NODE_CAP]
    node_ids = [node["id"] for node in nodes]
    edge_rows = graph.query(
        "MATCH (a:Entity)-[r]->(b:Entity) "
        "WHERE a.id IN $ids AND b.id IN $ids "
        "RETURN a.id, b.id, type(r), r.weight, r.descriptions, r.stances, r.source_refs",
        {"ids": node_ids},
    ).result_set
    edges: list[dict[str, Any]] = []
    for from_id, to_id, rel_type, weight, descriptions, stances, source_refs in edge_rows:
        refs = source_refs
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except json.JSONDecodeError:
                refs = []
        if not isinstance(refs, list):
            refs = []
        edges.append(
            {
                "from": str(from_id),
                "to": str(to_id),
                "rel_type": str(rel_type),
                "weight": int(weight or 0),
                "descriptions": [str(item) for item in (descriptions or [])],
                "stances": str(stances or "{}"),
                "source_refs": [
                    {
                        "source_id": str(ref.get("source_id") or ""),
                        "chunk_id": str(ref.get("chunk_id") or ""),
                        "quote": str(ref.get("quote") or ""),
                    }
                    for ref in refs
                    if isinstance(ref, dict)
                ],
            }
        )
    edges.sort(key=lambda edge: edge["weight"], reverse=True)
    edges = edges[:GRAPH_EDGE_CAP]
    return _apply_fact_corrections(nodes[:GRAPH_NODE_CAP], edges)


def _select_chunks(
    vector: list[float], source_ids: list[str], include_history: bool = False
) -> list[dict[str, Any]]:
    """Top chunks from the edge sources, plus the open-corpus top.

    D2: chunks of superseded sources are excluded unless ``include_history``;
    every returned chunk is flagged ``superseded`` so the caller can label it.
    """
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    superseded_sql = (
        "c.source_id IN (SELECT supersedes_source_id FROM cmap.source_version "
        "WHERE decided_at IS NOT NULL)"
    )
    history_filter = "" if include_history else f" AND NOT ({superseded_sql})"
    with get_pool().connection() as conn:
        queries: list[tuple[str, list[Any]]] = []
        if source_ids:
            queries.append(
                (
                    "SELECT c.id::text, c.source_id::text, s.title, c.locator, c.text, "
                    f"{superseded_sql} AS is_superseded "
                    "FROM cmap.chunk c JOIN cmap.source s ON s.id = c.source_id "
                    "WHERE c.embedding IS NOT NULL AND c.source_id = ANY(%s::uuid[])"
                    + history_filter
                    + " ORDER BY c.embedding <=> %s::vector LIMIT %s",
                    [source_ids, vector_literal(vector), CHUNKS_RESTRICTED],
                )
            )
        queries.append(
            (
                "SELECT c.id::text, c.source_id::text, s.title, c.locator, c.text, "
                f"{superseded_sql} AS is_superseded "
                "FROM cmap.chunk c JOIN cmap.source s ON s.id = c.source_id "
                "WHERE c.embedding IS NOT NULL"
                + history_filter
                + " ORDER BY c.embedding <=> %s::vector LIMIT %s",
                [vector_literal(vector), CHUNKS_UNRESTRICTED],
            )
        )
        for sql, params in queries:
            for row in conn.execute(sql, params).fetchall():
                chunk_id = str(row[0])
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                selected.append(
                    {
                        "id": chunk_id,
                        "source_id": str(row[1]),
                        "title": str(row[2]),
                        "locator": row[3],
                        "text": str(row[4]),
                        "superseded": bool(row[5]),
                    }
                )
    return selected


def _quotes_for(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Sentence-level quotes of the selected chunks, one entry per quote."""
    chunk_ids = [chunk["id"] for chunk in chunks]
    if not chunk_ids:
        return []
    by_chunk = {chunk["id"]: chunk for chunk in chunks}
    quotes: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with get_pool().connection() as conn:
        mention_rows = conn.execute(
            "SELECT chunk_id::text, quote FROM cmap.mention "
            "WHERE chunk_id = ANY(%s::uuid[]) ORDER BY quote, id",
            (chunk_ids,),
        ).fetchall()
        relation_rows = conn.execute(
            "SELECT chunk_id::text, quote FROM cmap.relation "
            "WHERE chunk_id = ANY(%s::uuid[]) ORDER BY quote, id",
            (chunk_ids,),
        ).fetchall()
    per_chunk: dict[str, list[str]] = {}
    for chunk_id, quote in list(mention_rows) + list(relation_rows):
        key = (str(chunk_id), str(quote))
        if key in seen:
            continue
        if str(chunk_id) not in by_chunk:
            continue
        seen.add(key)
        per_chunk.setdefault(str(chunk_id), []).append(str(quote))
    for chunk in chunks:
        for quote in per_chunk.get(chunk["id"], []):
            quotes.append(
                {
                    "chunk_id": chunk["id"],
                    "quote": quote,
                    "source_id": chunk["source_id"],
                    "title": chunk["title"],
                }
            )
    return quotes


def _compress_passages(
    texts: list[str], question: str, settings: Settings, usage: dict[str, int]
) -> str:
    """Join the chunk texts, compressing through ScaleDown past the threshold."""
    raw = "\n\n".join(texts)
    if _tokens(raw) <= COMPRESS_MIN_TOKENS:
        return raw
    if not settings.brain_scaledown_enabled or settings.scaledown_api_key is None:
        return raw
    usage["scaledown_compress_calls"] = usage.get("scaledown_compress_calls", 0) + 1
    try:
        payload = _post_scaledown(
            "/compress/raw/",
            {"context": raw, "prompt": question, "rate": "auto"},
            settings,
        )
    except AnswerError as exc:
        logger.warning("compress failed (%s); sending uncompressed passages", exc)
        return raw
    inner = payload.get("results")
    if not isinstance(inner, dict):
        inner = payload
    compressed = inner.get("compressed_prompt")
    if not isinstance(compressed, str) or not compressed.strip():
        return raw
    return compressed


def _render_history(history: list[dict[str, str]]) -> str:
    """Render the conversation turns kept for this request."""
    turns = history[-HISTORY_TURNS:] if history else []
    if not turns:
        return "CONVERSATION SO FAR: (none)"
    lines = ["CONVERSATION SO FAR:"]
    for turn in turns:
        lines.append(f"{str(turn.get('role') or 'user')}: {str(turn.get('content') or '')}")
    return "\n".join(lines)


def _render_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Render the entity/edge list with stances for the prompt."""
    names = {node["id"]: node["name"] for node in nodes}
    lines = ["ENTITIES:"]
    for node in nodes:
        lines.append(
            f"- [{node['type']}] {node['name']}: "
            f"{node['description'] or '(no description)'}"
        )
    lines.append("EDGES:")
    for edge in edges:
        descriptions = "; ".join(edge["descriptions"])
        lines.append(
            f"- {names.get(edge['from'], edge['from'])} -[{edge['rel_type']}]-> "
            f"{names.get(edge['to'], edge['to'])} weight={edge['weight']} "
            f"stances={edge['stances']} {descriptions}"
        )
    return "\n".join(lines)


def _local_answer(
    question: str,
    history: list[dict[str, str]],
    settings: Settings,
    usage: dict[str, int],
) -> dict[str, Any]:
    """Local mode: graph neighbourhood + chunk retrieval + quote citations.

    D2: ``is_history_question`` is the history-reach seam — only a question
    explicitly about the past retrieves (labelled) superseded passages; every
    other question is current-only.
    """
    include_history = is_history_question(question)
    vector = embed_texts([question], settings, usage)[0]
    entities = _select_entities(question, vector, include_history)
    nodes, edges = _graph_context(entities, settings)
    edge_sources = sorted(
        {
            ref["source_id"]
            for edge in edges
            for ref in edge["source_refs"]
            if ref["source_id"]
        }
    )
    chunks = _select_chunks(vector, edge_sources, include_history)
    quotes = _quotes_for(chunks)
    texts = [
        _HISTORY_PREFIX + chunk["text"] if chunk.get("superseded") else chunk["text"]
        for chunk in chunks
    ]
    passages = _compress_passages(texts, question, settings, usage)
    graph_block = _render_graph(nodes, edges)
    with get_pool().connection() as conn:
        disagreements = disagreement_lines(conn, [node["id"] for node in nodes])
    if disagreements:
        graph_block += "\n\nSOURCES DISAGREE:\n" + "\n".join(
            f"- {line}" for line in disagreements
        )
    template = LOCAL_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{history}}", _render_history(history))
        .replace("{{question}}", question)
        .replace("{{graph}}", graph_block)
        .replace("{{passages}}", passages)
        .replace("{{quotes}}", json.dumps(quotes, ensure_ascii=False))
    )
    raw = _ask(prompt, settings, usage)
    answer_md = str(raw.get("answer_md") or "")
    raw_citations = [
        item for item in (raw.get("citations") or []) if isinstance(item, dict)
    ]
    unknowns = [
        str(item) for item in (raw.get("unknowns") or []) if str(item).strip()
    ]
    final_md, citations = _finalize_local(answer_md, raw_citations, chunks)
    return {
        "answer_md": final_md,
        "citations": citations,
        "mode_used": "local",
        "entities": entities,
        "communities": [],
        "unknowns": unknowns,
    }


# -------------------------------------------------------------------- global


def _report_summary(report_md: str) -> str:
    """The prose under the report title, before its Findings section."""
    text = (report_md or "").strip()
    if text.startswith("# "):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text.split("\n## Findings", 1)[0].strip()


def _apply_report_corrections(
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """G1: corrections win in report assembly (plan Phase G).

    A finding that touches a rejected entity never reaches the answer; a
    finding on a confirmed entity ranks first inside its report.
    """
    entity_ids: set[str] = set()
    for report in reports:
        for finding in report["findings"]:
            for item in finding.get("entity_ids") or []:
                try:
                    entity_ids.add(str(uuid.UUID(str(item))))
                except (ValueError, AttributeError, TypeError):
                    continue
    if not entity_ids:
        return reports
    with get_pool().connection() as conn:
        corrections = load_corrections(conn)
        key_sets = entity_key_sets(conn, sorted(entity_ids))
    for report in reports:
        confirmed: list[dict[str, Any]] = []
        kept: list[dict[str, Any]] = []
        for finding in report["findings"]:
            rejected = False
            is_confirmed = False
            for item in finding.get("entity_ids") or []:
                try:
                    keys = key_sets.get(str(uuid.UUID(str(item))), set())
                except (ValueError, AttributeError, TypeError):
                    continue
                verdict = corrections.verdict_for(keys) if keys else None
                if verdict is not None and verdict.action == "reject":
                    rejected = True
                if verdict is not None and verdict.action == "confirm":
                    is_confirmed = True
            if rejected:
                continue
            if is_confirmed:
                confirmed.append(finding)
            else:
                kept.append(finding)
        report["findings"] = confirmed + kept
    return reports


def _drop_superseded_findings(
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """D2: a finding whose only sources are superseded is history, not report.

    Kept when the question is about the past (the caller skips this filter).
    """
    with get_pool().connection() as conn:
        superseded = superseded_source_ids(conn)
    if not superseded:
        return reports
    for report in reports:
        kept: list[dict[str, Any]] = []
        for finding in report["findings"]:
            ids = {str(item) for item in (finding.get("source_ids") or [])}
            if ids and ids <= superseded:
                continue
            kept.append(finding)
        report["findings"] = kept
    return reports


def _load_reports(include_history: bool = False) -> list[dict[str, Any]]:
    """The current map's level-1 community reports plus its company report.

    Only rows stamped with the current graph version are read: older builds'
    reports stay in the table for a while and must never reach an answer.
    D2: findings whose only sources are superseded are dropped unless the
    question is about the past.
    """
    with get_pool().connection() as conn:
        version = current_graph_version(conn)
        if version is None:
            return []
        rows = conn.execute(
            "SELECT id::text, level, title, report_md, findings "
            "FROM cmap.community WHERE level IN (1, 2) AND graph_version = %s "
            "ORDER BY level, title",
            (version,),
        ).fetchall()
    reports: list[dict[str, Any]] = []
    for report_id, level, title, report_md, findings in rows:
        if not isinstance(findings, list):
            findings = []
        reports.append(
            {
                "id": report_id,
                "level": int(level),
                "title": str(title or ""),
                "summary": _report_summary(str(report_md or "")),
                "findings": [item for item in findings if isinstance(item, dict)],
            }
        )
    if not include_history:
        reports = _drop_superseded_findings(reports)
    return _apply_report_corrections(reports)


def _reports_context(reports: list[dict[str, Any]]) -> str:
    """Render the reports with their findings' source ids for citing."""
    lines = ["REPORTS:"]
    for report in reports:
        lines.append(f"## {report['title']}")
        lines.append(report["summary"])
        for finding in report["findings"]:
            source_ids = [
                str(source_id) for source_id in (finding.get("source_ids") or [])
            ]
            lines.append(
                f"- [{finding.get('kind', '')}] {finding.get('text', '')} "
                f"(sources: {', '.join(source_ids)})"
            )
    return "\n".join(lines)


def _points_context(points: list[dict[str, Any]]) -> str:
    """Render mapped points (the map-reduce middle step) as the report context."""
    lines = ["MAPPED POINTS:"]
    for point in points:
        source_ids = [str(source_id) for source_id in (point.get("source_ids") or [])]
        lines.append(
            f"- [{point.get('relevance', '')}] {point.get('text', '')} "
            f"(sources: {', '.join(source_ids)})"
        )
    return "\n".join(lines)


def _map_points(
    question: str,
    reports: list[dict[str, Any]],
    settings: Settings,
    usage: dict[str, int],
) -> list[dict[str, Any]]:
    """Map step: one frontier call per 10 reports, keeping relevant points."""
    template = MAP_PROMPT_PATH.read_text(encoding="utf-8")
    points: list[dict[str, Any]] = []
    for start in range(0, len(reports), MAP_BATCH):
        batch = reports[start : start + MAP_BATCH]
        prompt = (
            template.replace("{{question}}", question)
            .replace("{{reports}}", _reports_context(batch))
        )
        raw = _ask(prompt, settings, usage)
        for item in raw.get("points") or []:
            if not isinstance(item, dict):
                continue
            try:
                relevance = float(item.get("relevance") or 0)
            except (TypeError, ValueError):
                relevance = 0.0
            points.append(
                {
                    "text": str(item.get("text") or ""),
                    "source_ids": [
                        str(source_id)
                        for source_id in (item.get("source_ids") or [])
                        if str(source_id).strip()
                    ],
                    "relevance": relevance,
                }
            )
    points.sort(key=lambda point: point["relevance"], reverse=True)
    return points


def _global_answer(
    question: str,
    history: list[dict[str, str]],
    settings: Settings,
    usage: dict[str, int],
) -> dict[str, Any]:
    """Global mode: synthesise the community reports, citing finding sources.

    D2: the same history-reach seam as local mode — superseded findings are
    reachable only for questions explicitly about the past.
    """
    reports = _load_reports(is_history_question(question))
    context = _reports_context(reports)
    evidence: list[dict[str, Any]] = [
        {
            "text": str(finding.get("text") or ""),
            "source_ids": [
                str(source_id) for source_id in (finding.get("source_ids") or [])
            ],
        }
        for report in reports
        for finding in report["findings"]
    ]
    if _tokens(context) > GLOBAL_ONE_SHOT_TOKENS:
        points = _map_points(question, reports, settings, usage)
        context = _points_context(points)
        evidence = [
            {
                "text": str(point.get("text") or ""),
                "source_ids": list(point["source_ids"]),
            }
            for point in points
        ]
    report_entity_ids = [
        str(entity_id)
        for report in reports
        for finding in report["findings"]
        for entity_id in (finding.get("entity_ids") or [])
        if str(entity_id).strip()
    ]
    with get_pool().connection() as conn:
        disagreements = disagreement_lines(conn, report_entity_ids)
    if disagreements:
        context += "\n\nSOURCES DISAGREE:\n" + "\n".join(
            f"- {line}" for line in disagreements
        )
    template = GLOBAL_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{history}}", _render_history(history))
        .replace("{{question}}", question)
        .replace("{{reports}}", context)
    )
    raw = _ask(prompt, settings, usage)
    answer_md = str(raw.get("answer_md") or "")
    raw_citations = [
        item for item in (raw.get("citations") or []) if isinstance(item, dict)
    ]
    unknowns = [
        str(item) for item in (raw.get("unknowns") or []) if str(item).strip()
    ]
    final_md, citations = _finalize_global(answer_md, raw_citations, evidence)
    return {
        "answer_md": final_md,
        "citations": citations,
        "mode_used": "global",
        "entities": [],
        "communities": [
            {"id": report["id"], "level": report["level"], "title": report["title"]}
            for report in reports
        ],
        "unknowns": unknowns,
    }


def _shift_markers(answer_md: str, offset: int) -> str:
    """Renumber [n] markers by ``offset`` for a merged answer."""
    return _MARKER.sub(lambda match: f"[{int(match.group(1)) + offset}]", answer_md)


def _merge_answers(local: dict[str, Any], global_: dict[str, Any]) -> dict[str, Any]:
    """Merge both modes: local prose first, then the company-wide view."""
    offset = len(local["citations"])
    return {
        "answer_md": local["answer_md"] + "\n\n" + _shift_markers(global_["answer_md"], offset),
        "citations": list(local["citations"]) + list(global_["citations"]),
        "mode_used": "both",
        "entities": local["entities"],
        "communities": global_["communities"],
        "unknowns": list(local["unknowns"]) + list(global_["unknowns"]),
    }


def answer_question(
    question: str,
    mode: str = "auto",
    history: list[dict[str, str]] | None = None,
    settings: Settings | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Answer one question; return the step-9 response shape.

    ``mode`` is ``auto``, ``local`` or ``global``. The caller owns any
    session state: only ``history``'s last turns are used, never stored.
    H1 adds ``supported_share`` — the share of sentences the cited quotes
    support, after every other sentence was rewritten or marked.
    """
    cfg = settings if settings is not None else get_settings()
    counters = usage if usage is not None else {}
    turns = list(history or [])
    text = question.strip()
    if not text:
        raise AnswerError("question is required")
    if mode not in {"auto", "local", "global"}:
        raise AnswerError("mode must be auto, local or global")
    if mode == "auto":
        mode = _route_mode(text, cfg, counters)
    if mode == "local":
        result = _local_answer(text, turns, cfg, counters)
    elif mode == "global":
        result = _global_answer(text, turns, cfg, counters)
    else:
        result = _merge_answers(
            _local_answer(text, turns, cfg, counters),
            _global_answer(text, turns, cfg, counters),
        )
    return _verify_support(result, cfg, counters)
