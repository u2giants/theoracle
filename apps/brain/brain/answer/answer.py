"""Question answering over the company map (plan step 9; C4 scoped answering).

``POST /answer`` asks one question in one of three modes:

- ``auto`` — route first (C4): the question and its conversation history are
  classified to 0–3 functions with the C2 classifier (``prompts/function_assign.md``).
  No function ⇒ company-wide mode. A confident top function (weight ≥ 0.5) ⇒
  scoped mode on the routed functions. Low confidence ⇒ one hybrid prompt with
  the top function's scope plus the company report (never two answers
  concatenated).
- ``local`` — scoped mode forced: the same classifier routes the question and
  retrieval is restricted to the routed functions' material; with no routed
  function the scope is the whole map (the forced-mode contract). Candidates
  are entities and chunks assigned to the routed functions
  (``cmap.*_function.weight`` ≥ 0.2) plus entities one hand-off/sequence hop
  across the function boundary. A similarity floor (0.25 cosine) drops
  "nearest of nothing" hits; when nothing survives and no report or flow is in
  scope the answer is an honest don't-know. Expansion around the seeds is
  ranked by similarity to the question × relation-kind weight (never global
  popularity). Alias seeding matches on word boundaries and ignores aliases
  under 3 characters.
- ``global`` — company-wide mode: the company report plus the function
  reports, the function reports always selected by relevance through the map
  step (``prompts/answer_map.md``), citing finding source_ids resolved to
  titles and the prompt's own evidence text.

Both modes assemble their context under a hard token ceiling
(``BRAIN_ANSWER_CONTEXT_TOKENS``, default 12,000) in priority order — function
report → ordered process flow (E2) → relations → quotes → passages — and never
exceed it; ScaleDown compression is an optimisation only. Every answer
returns ``functions_consulted`` and ``context_tokens``.

Citations are validated: a quote must be a substring of its chunk or the
citation is dropped (a report citation may name only sources present in the
prompt, quoting that prompt's evidence text), and a sentence left without any
citation is marked ``(uncited)`` rather than deleted. History is the request's
last turns only — there is no server-side session store.

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
from brain.function_assign import (
    build_prompt as build_function_prompt,
)
from brain.function_assign import (
    load_functions,
)
from brain.function_assign import (
    validate_response as validate_function_response,
)
from brain.graph.communities import EDGE_KIND_WEIGHTS, _tokens, edge_rank
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
MAP_BATCH = 10
HISTORY_TURNS = 6
MAX_TOKENS = 8000
ASK_ATTEMPTS = 3

# C4 function scoping (tune on the approved set; plan §9 C4).
# A chunk/entity assignment below this weight does not put its function's
# material in scope.
FUNCTION_WEIGHT_FLOOR = 0.2
# Cosine floor on retrieval: "nearest of nothing" is not evidence.
SIMILARITY_FLOOR = 0.25
# Below this top function weight, routing confidence is low and the answer
# runs the top function's scope plus the company report in ONE prompt.
ROUTE_MIN_WEIGHT = 0.5
# Relations that carry work across a function boundary (one hop only).
HANDOFF_REL_TYPES = frozenset({"HANDS_OFF_TO", "PRECEDES"})
# Alias seeding: word-boundary matches only, and never for short aliases.
ALIAS_MIN_CHARS = 3
_ALIAS_EDGE = r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])"

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


def _route_functions(
    question: str,
    history: list[dict[str, str]],
    settings: Settings,
    usage: dict[str, int],
) -> list[dict[str, Any]]:
    """Classify the question (with its history) to 0–3 functions (C2's classifier).

    Reuses the C2 classifier verbatim: the ``function_assign`` prompt and the
    same 0–3 keyed picks with clamped weights. The conversation history is part
    of the passage so a follow-up inherits the scope of what preceded it.
    With no active function vocabulary there is nothing to route to, and no
    model call is made.
    """
    with get_pool().connection() as conn:
        functions = load_functions(conn)
    if not functions:
        return []
    passage = f"QUESTION:\n{question}\n\n{_render_history(history)}"
    prompt = build_function_prompt(passage, functions)
    usage["route_calls"] = usage.get("route_calls", 0) + 1
    payload = _ask(prompt, settings, usage)
    known = {item["key"]: item["id"] for item in functions}
    weights = validate_function_response(payload, known)
    names = {item["key"]: item["name"] for item in functions}
    routed = [
        {
            "id": known[key],
            "key": key,
            "name": names[key],
            "weight": weight,
        }
        for key, weight in weights.items()
    ]
    routed.sort(key=lambda item: item["weight"], reverse=True)
    return routed[:3]


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


def _finalize_citations(
    answer_md: str,
    raw_citations: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    evidence: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Validate citations against what the prompt showed; renumber markers.

    A citation with a ``chunk_id`` must quote its chunk verbatim (the locked
    rule). A citation with only a ``source_id`` follows the company-wide rule:
    the source must be present in the prompt's evidence and its quote is that
    evidence text. Anything else is dropped.
    """
    by_id = {chunk["id"]: chunk for chunk in chunks}
    allowed: set[str] = set()
    texts_by_source: dict[str, list[str]] = {}
    for item in evidence or []:
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
            chunk_id = str(cite.get("chunk_id") or "")
            quote = str(cite.get("quote") or "")
            if chunk_id:
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
                continue
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


def _finalize_local(
    answer_md: str,
    raw_citations: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    evidence: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Scoped/hybrid finalize: verbatim chunk quotes plus prompt-backed reports."""
    return _finalize_citations(answer_md, raw_citations, chunks, evidence)


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
    return _finalize_citations(answer_md, raw_citations, [], evidence)


# -------------------------------------------------------------------- local


def _fold_question(question: str) -> str:
    """Casefold and strip punctuation so alias names can appear-match."""
    return fold_key(question)


def _alias_matches(question: str, aliases: list[str]) -> bool:
    """Word-boundary alias seeding: short aliases never substring-match.

    An alias under ``ALIAS_MIN_CHARS`` characters is ignored outright, and a
    longer one matches only at ASCII word edges so "cat" never seeds from
    "concatenate". CJK neighbours are not word edges (Chinese has no spaces).
    """
    folded = _fold_question(question)
    for alias in aliases:
        if len(alias) < ALIAS_MIN_CHARS:
            continue
        if re.search(_ALIAS_EDGE % re.escape(alias), folded):
            return True
    return False


def _function_entity_ids(conn: Any, function_ids: list[str]) -> list[str]:
    """Entities assigned to the routed functions at weight ≥ the floor."""
    rows = conn.execute(
        "SELECT DISTINCT entity_id::text FROM cmap.entity_function "
        "WHERE function_id = ANY(%s::uuid[]) AND weight >= %s",
        (function_ids, FUNCTION_WEIGHT_FLOOR),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _select_entities(
    question: str,
    vector: list[float],
    include_history: bool = False,
    universe_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Top-8 entities by embedding cosine above the floor, plus alias matches.

    C4: candidates are limited to ``universe_ids`` (the routed functions'
    entities plus their one-hop hand-off neighbours) when given; a candidate
    below ``SIMILARITY_FLOOR`` is never retrieved ("nearest of nothing").
    D2: an entity whose only mentions sit in superseded sources is history and
    is left out unless the question is about the past.
    """
    live = (
        ""
        if include_history
        else " AND EXISTS (SELECT 1 FROM cmap.mention m "
        "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
        "WHERE m.entity_id = e.id AND ch.source_id NOT IN "
        "(SELECT supersedes_source_id FROM cmap.source_version "
        "WHERE decided_at IS NOT NULL))"
    )
    scope = ""
    params: list[Any] = [vector_literal(vector), SIMILARITY_FLOOR]
    if universe_ids is not None:
        if not universe_ids:
            return []
        scope = " AND e.id = ANY(%s::uuid[])"
        params.append(universe_ids)
    params.extend([vector_literal(vector), TOP_ENTITIES])
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT e.id::text, e.entity_type, e.canonical_name, e.description, "
            "e.mention_count, e.source_count "
            "FROM cmap.entity e WHERE e.embedding IS NOT NULL" + live + " "
            "AND 1 - (e.embedding <=> %s::vector) >= %s" + scope + " "
            "ORDER BY e.embedding <=> %s::vector LIMIT %s",
            params,
        ).fetchall()
        alias_sql = (
            "SELECT DISTINCT e.id::text, e.entity_type, e.canonical_name, "
            "e.description, e.mention_count, e.source_count, a.normalized_name "
            "FROM cmap.entity e "
            "JOIN cmap.entity_alias a ON a.entity_id = e.id "
            "WHERE a.normalized_name <> '' AND length(a.normalized_name) >= %s"
            + live
            + scope
        )
        alias_params: list[Any] = [ALIAS_MIN_CHARS]
        if universe_ids is not None:
            alias_params.append(universe_ids)
        alias_rows = conn.execute(alias_sql, alias_params).fetchall()
    seen: dict[str, dict[str, Any]] = {}
    for row in list(rows):
        entity_id = str(row[0])
        seen[entity_id] = {
            "id": entity_id,
            "type": str(row[1]),
            "name": str(row[2]),
            "description": str(row[3] or ""),
            "mention_count": int(row[4]),
            "source_count": int(row[5]),
        }
    aliases_by_id: dict[str, list[str]] = {}
    for row in alias_rows:
        aliases_by_id.setdefault(str(row[0]), []).append(str(row[6]))
    for entity_id, aliases in aliases_by_id.items():
        if entity_id in seen:
            continue
        if not _alias_matches(question, aliases):
            continue
        row = next(r for r in alias_rows if str(r[0]) == entity_id)
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
    entities: list[dict[str, Any]],
    settings: Settings,
    vector: list[float],
    universe_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Neighbourhood of the seeds, ranked by similarity × relation-kind weight.

    C4: the old depth-2-by-global-popularity expansion is gone. Candidates
    reachable in ≤ 2 hops are scored ``cosine(candidate, question) ×
    relation-kind weight`` (hand-off and sequence kinds weigh double — the C3
    cluster weights) and the top nodes are kept. When ``universe_ids`` is set
    (scoped mode) only that universe may enter: the routed functions'
    entities plus the one-hop hand-off/sequence neighbours across the
    boundary — never anything else.
    """
    ids = [entity["id"] for entity in entities]
    graph = connect_graph(settings)
    allowed: set[str] | None = None
    if universe_ids is not None:
        allowed = set(universe_ids)
        rows = graph.query(
            "MATCH (a:Entity)-[r]-(x:Entity) WHERE a.id IN $ids "
            "AND type(r) IN ['HANDS_OFF_TO', 'PRECEDES'] RETURN DISTINCT x.id",
            {"ids": universe_ids},
        ).result_set
        allowed |= {str(row[0]) for row in rows}
        allowed |= set(ids)
    kind_score: dict[str, float] = {entity_id: 1.0 for entity_id in ids}
    frontier = list(ids)
    seen: set[str] = set(ids)
    for _hop in range(2):
        if not frontier:
            break
        rows = graph.query(
            "MATCH (a:Entity)-[r]-(x:Entity) WHERE a.id IN $ids "
            "RETURN a.id, x.id, type(r)",
            {"ids": frontier},
        ).result_set
        next_frontier: list[str] = []
        for _from_id, to_id, rel_type in rows:
            candidate = str(to_id)
            if allowed is not None and candidate not in allowed:
                continue
            weight = EDGE_KIND_WEIGHTS.get(str(rel_type), 1.0)
            if weight > kind_score.get(candidate, 0.0):
                kind_score[candidate] = weight
            if candidate in seen:
                continue
            seen.add(candidate)
            next_frontier.append(candidate)
        frontier = next_frontier
    sims: dict[str, float] = {}
    if seen:
        with get_pool().connection() as conn:
            sim_rows = conn.execute(
                "SELECT id::text, 1 - (embedding <=> %s::vector) FROM cmap.entity "
                "WHERE id = ANY(%s::uuid[])",
                (vector_literal(vector), sorted(seen)),
            ).fetchall()
        for entity_id, sim in sim_rows:
            sims[str(entity_id)] = float(sim)

    def _score(entity_id: str) -> float:
        return sims.get(entity_id, 0.0) * kind_score.get(entity_id, 1.0)

    ranked = sorted(seen, key=_score, reverse=True)[:GRAPH_NODE_CAP]
    ranked_ids = set(ranked)
    nodes: list[dict[str, Any]] = []
    for entity in entities:
        if entity["id"] not in ranked_ids:
            continue
        nodes.append(
            {
                "id": entity["id"],
                "type": entity["type"],
                "name": entity["name"],
                "description": entity["description"],
            }
        )
    by_id = {node["id"] for node in nodes}
    for entity_id in ranked:
        if entity_id in by_id:
            continue
        rows = graph.query(
            "MATCH (x:Entity {id: $id}) RETURN x.type, x.name, x.description",
            {"id": entity_id},
        ).result_set
        if not rows:
            continue
        node_type, name, description = rows[0]
        nodes.append(
            {
                "id": entity_id,
                "type": str(node_type),
                "name": str(name),
                "description": str(description or ""),
            }
        )
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
    edges.sort(key=edge_rank, reverse=True)
    edges = edges[:GRAPH_EDGE_CAP]
    return _apply_fact_corrections(nodes[:GRAPH_NODE_CAP], edges)


def _select_chunks(
    vector: list[float],
    source_ids: list[str],
    include_history: bool = False,
    function_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Top chunks from the edge sources, plus the open-corpus top.

    C4: both queries are restricted to chunks assigned to the routed
    functions at weight ≥ the floor when ``function_ids`` is given, and every
    candidate must clear ``SIMILARITY_FLOOR`` — the nearest of nothing is
    never used. D2: chunks of superseded sources are excluded unless
    ``include_history``; every returned chunk is flagged ``superseded`` so the
    caller can label it.
    """
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    superseded_sql = (
        "c.source_id IN (SELECT supersedes_source_id FROM cmap.source_version "
        "WHERE decided_at IS NOT NULL)"
    )
    history_filter = "" if include_history else f" AND NOT ({superseded_sql})"
    function_filter = ""
    function_params: list[Any] = []
    if function_ids is not None:
        function_filter = (
            " AND EXISTS (SELECT 1 FROM cmap.chunk_function cf "
            "WHERE cf.chunk_id = c.id AND cf.function_id = ANY(%s::uuid[]) "
            "AND cf.weight >= %s)"
        )
        function_params = [function_ids, FUNCTION_WEIGHT_FLOOR]
    floor_sql = " AND 1 - (c.embedding <=> %s::vector) >= %s"
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
                    + function_filter
                    + floor_sql
                    + " ORDER BY c.embedding <=> %s::vector LIMIT %s",
                    [source_ids]
                    + function_params
                    + [vector_literal(vector), SIMILARITY_FLOOR, vector_literal(vector), CHUNKS_RESTRICTED],
                )
            )
        queries.append(
            (
                "SELECT c.id::text, c.source_id::text, s.title, c.locator, c.text, "
                f"{superseded_sql} AS is_superseded "
                "FROM cmap.chunk c JOIN cmap.source s ON s.id = c.source_id "
                "WHERE c.embedding IS NOT NULL"
                + history_filter
                + function_filter
                + floor_sql
                + " ORDER BY c.embedding <=> %s::vector LIMIT %s",
                function_params
                + [vector_literal(vector), SIMILARITY_FLOOR, vector_literal(vector), CHUNKS_UNRESTRICTED],
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


def _flow_items(function_ids: list[str] | None) -> list[str]:
    """Ordered process flows (E2) in scope, one line per flow and step."""
    with get_pool().connection() as conn:
        if function_ids is None:
            flows = conn.execute(
                "SELECT id::text, title, trigger, outcome FROM cmap.process_flow "
                "ORDER BY title"
            ).fetchall()
        elif function_ids:
            flows = conn.execute(
                "SELECT id::text, title, trigger, outcome FROM cmap.process_flow "
                "WHERE function_id = ANY(%s::uuid[]) ORDER BY title",
                (function_ids,),
            ).fetchall()
        else:
            flows = []
        items: list[str] = []
        for flow_id, title, trigger, outcome in flows:
            items.append(
                f"FLOW {title} (trigger: {trigger or '?'} → outcome: {outcome or '?'})"
            )
            steps = conn.execute(
                "SELECT ordinal, input, output, decision FROM cmap.flow_step "
                "WHERE flow_id = %s ORDER BY ordinal",
                (flow_id,),
            ).fetchall()
            for ordinal, step_input, step_output, decision in steps:
                line = (
                    f"  {ordinal}. in: {step_input or '?'} "
                    f"out: {step_output or '?'}"
                )
                if decision:
                    line += f" decision: {decision}"
                items.append(line)
    return items


def _report_items(reports: list[dict[str, Any]]) -> tuple[list[str], list[Any]]:
    """Render reports as budget items; per-item evidence (None for headings)."""
    lines: list[str] = []
    evidence: list[Any] = []
    for report in reports:
        lines.append(f"## {report['title']}")
        evidence.append(None)
        lines.append(report["summary"])
        evidence.append(None)
        for finding in report["findings"]:
            source_ids = [
                str(source_id) for source_id in (finding.get("source_ids") or [])
            ]
            text = str(finding.get("text") or "")
            lines.append(
                f"- [{finding.get('kind', '')}] {text} "
                f"(sources: {', '.join(source_ids)})"
            )
            evidence.append({"text": text, "source_ids": source_ids})
    return lines, evidence


def _function_report_items(
    function_ids: list[str] | None,
    include_history: bool,
    level: int,
) -> tuple[list[str], list[dict[str, Any]], list[Any]]:
    """One function report per routed function (C3: level 1, id = function id).

    Returns ``(lines, reports, evidence)`` — ``evidence`` is per-line (None
    for headings) so the budget can report exactly what reached the prompt.
    ``level=2`` loads the company report.
    """
    reports = _load_reports(include_history, level=level, function_ids=function_ids)
    lines, evidence = _report_items(reports)
    return lines, reports, evidence


def _assemble_context(
    tiers: list[tuple[str, list[str], Any]], ceiling: int
) -> tuple[dict[str, str], int, list[list[int]]]:
    """Fill each tier's items in priority order under a hard token ceiling.

    Each tier carries its own renderer (the quotes tier becomes a JSON
    array); items that do not fit are skipped (a later, smaller item still
    can). The rendered total is re-measured exactly and, on the worst case,
    the lowest-priority items are dropped until the ceiling holds. Never
    exceeds. Returns the rendered text per tier, its exact token count and
    the kept item indices per tier.
    """
    kept: list[list[int]] = [[] for _ in tiers]
    used = 0
    for (_name, items, _render), bucket in zip(tiers, kept, strict=True):
        for index, item in enumerate(items):
            cost = _tokens(item) + 3
            if used + cost > ceiling:
                continue
            bucket.append(index)
            used += cost

    def _render_all() -> tuple[dict[str, str], int]:
        rendered = {
            name: render([items[index] for index in bucket])
            for (name, items, render), bucket in zip(tiers, kept, strict=True)
        }
        total = _tokens("\n\n".join(text for text in rendered.values() if text))
        return rendered, total

    rendered, total = _render_all()
    while total > ceiling:
        dropped = False
        for bucket in reversed(kept):
            if bucket:
                bucket.pop()
                dropped = True
                break
        if not dropped:
            break
        rendered, total = _render_all()
    return rendered, total, kept


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


def _dont_know(
    question: str,
    functions_consulted: list[dict[str, Any]],
    mode_used: str,
) -> dict[str, Any]:
    """The honest empty-context answer: nothing in scope is close enough.

    The similarity floor exists so "nearest of nothing" never becomes
    evidence; when the floor (and the function scope) leave no report, flow,
    entity or chunk, no model call is made and the answer says so.
    """
    return {
        "answer_md": (
            "I don't know — nothing in the company map is close enough to "
            "this question to answer from it."
        ),
        "citations": [],
        "mode_used": mode_used,
        "entities": [],
        "communities": [],
        "unknowns": ["nothing in scope matched the question closely enough"],
        "functions_consulted": functions_consulted,
        "context_tokens": 0,
    }


def _local_answer(
    question: str,
    history: list[dict[str, str]],
    settings: Settings,
    usage: dict[str, int],
    function_ids: list[str] | None = None,
    functions_consulted: list[dict[str, Any]] | None = None,
    mode_used: str = "local",
    with_company_report: bool = False,
) -> dict[str, Any]:
    """Scoped mode: function-restricted retrieval under a hard token budget.

    D2: ``is_history_question`` is the history-reach seam — only a question
    explicitly about the past retrieves (labelled) superseded passages; every
    other question is current-only. C4: the context is assembled in priority
    order (function report → ordered flow → relations → quotes → passages)
    until ``BRAIN_ANSWER_CONTEXT_TOKENS`` is spent, and never past it.
    """
    include_history = is_history_question(question)
    vector = embed_texts([question], settings, usage)[0]
    with get_pool().connection() as conn:
        universe_ids = (
            None
            if function_ids is None
            else _function_entity_ids(conn, function_ids)
        )
    entities = _select_entities(question, vector, include_history, universe_ids)
    nodes, edges = _graph_context(entities, settings, vector, universe_ids)
    edge_sources = sorted(
        {
            ref["source_id"]
            for edge in edges
            for ref in edge["source_refs"]
            if ref["source_id"]
        }
    )
    chunks = _select_chunks(vector, edge_sources, include_history, function_ids)
    quotes = _quotes_for(chunks)
    texts = [
        _HISTORY_PREFIX + chunk["text"] if chunk.get("superseded") else chunk["text"]
        for chunk in chunks
    ]
    graph_block = _render_graph(nodes, edges)
    with get_pool().connection() as conn:
        disagreements = disagreement_lines(conn, [node["id"] for node in nodes])
    if disagreements:
        graph_block += "\n\nSOURCES DISAGREE:\n" + "\n".join(
            f"- {line}" for line in disagreements
        )
    report_lines, report_rows, report_evidence = _function_report_items(
        function_ids, include_history, level=1
    )
    company_lines: list[str] = []
    company_evidence: list[dict[str, Any]] = []
    if with_company_report:
        company_lines, company_rows, company_evidence = _function_report_items(
            None, include_history, level=2
        )
        report_rows = report_rows + company_rows
    flow_lines = _flow_items(function_ids)
    ceiling = settings.brain_answer_context_tokens
    # Priority (plan C4 step 4): function report → company report (hybrid
    # only) → ordered flow → relations → quotes → passages.
    quote_items = [json.dumps(quote, ensure_ascii=False) for quote in quotes]
    rendered, context_tokens, kept = _assemble_context(
        [
            ("function_reports", report_lines, "\n".join),
            ("company", company_lines, "\n".join),
            ("flow", flow_lines, "\n".join),
            ("graph", graph_block.split("\n"), "\n".join),
            ("quotes", quote_items, lambda items: "[" + ",".join(items) + "]"),
            ("passages", texts, "\n\n".join),
        ],
        ceiling,
    )
    passages_text = rendered["passages"]
    if passages_text and _tokens(passages_text) > COMPRESS_MIN_TOKENS:
        passages_text = _compress_passages(
            rendered["passages"].split("\n\n"), question, settings, usage
        )
    if not nodes and not chunks and not report_lines and not flow_lines and not company_lines:
        return _dont_know(
            question,
            functions_consulted or [],
            mode_used,
        )
    template = LOCAL_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{history}}", _render_history(history))
        .replace("{{question}}", question)
        .replace("{{function_reports}}", rendered["function_reports"] or "(none)")
        .replace("{{company}}", rendered["company"] or "(none)")
        .replace("{{flow}}", rendered["flow"] or "(none)")
        .replace("{{graph}}", rendered["graph"] or "(none)")
        .replace("{{passages}}", passages_text or "(none)")
        .replace("{{quotes}}", rendered["quotes"] or "[]")
    )
    raw = _ask(prompt, settings, usage)
    answer_md = str(raw.get("answer_md") or "")
    raw_citations = [
        item for item in (raw.get("citations") or []) if isinstance(item, dict)
    ]
    unknowns = [
        str(item) for item in (raw.get("unknowns") or []) if str(item).strip()
    ]
    report_kept = set(kept[0])
    company_kept = set(kept[1])
    evidence = [
        item
        for index, item in enumerate(report_evidence)
        if index in report_kept and item is not None
    ] + [
        item
        for index, item in enumerate(company_evidence)
        if index in company_kept and item is not None
    ]
    final_md, citations = _finalize_local(answer_md, raw_citations, chunks, evidence)
    return {
        "answer_md": final_md,
        "citations": citations,
        "mode_used": mode_used,
        "entities": entities,
        "communities": [
            {"id": row["id"], "level": row["level"], "title": row["title"]}
            for row in report_rows
        ],
        "unknowns": unknowns,
        "functions_consulted": functions_consulted or [],
        "context_tokens": context_tokens,
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


def _load_reports(
    include_history: bool = False,
    level: int | None = None,
    function_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """The current map's community reports (C3: level 1 per function, 2 company).

    Only rows stamped with the current graph version are read: older builds'
    reports stay in the table for a while and must never reach an answer.
    ``level`` and ``function_ids`` narrow the load (scoped mode reads just the
    routed functions' reports). D2: findings whose only sources are superseded
    are dropped unless the question is about the past.
    """
    where = "graph_version = %s"
    params: list[Any] = []
    with get_pool().connection() as conn:
        version = current_graph_version(conn)
        if version is None:
            return []
        params.append(version)
        if level is not None:
            where += " AND level = %s"
            params.append(level)
        else:
            where += " AND level IN (1, 2)"
        if function_ids is not None:
            where += " AND function_id = ANY(%s::uuid[])"
            params.append(function_ids)
        rows = conn.execute(
            "SELECT id::text, level, title, report_md, findings, function_id::text "
            f"FROM cmap.community WHERE {where} "
            "ORDER BY level, title",
            params,
        ).fetchall()
    reports: list[dict[str, Any]] = []
    for report_id, level, title, report_md, findings, function_id in rows:
        if not isinstance(findings, list):
            findings = []
        reports.append(
            {
                "id": report_id,
                "level": int(level),
                "title": str(title or ""),
                "summary": _report_summary(str(report_md or "")),
                "findings": [item for item in findings if isinstance(item, dict)],
                "function_id": str(function_id) if function_id else None,
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


def _consulted_functions(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The functions behind the consulted reports (C3: title = function name)."""
    wanted = [report["function_id"] for report in reports if report.get("function_id")]
    names: dict[str, tuple[str, str]] = {}
    if wanted:
        with get_pool().connection() as conn:
            rows = conn.execute(
                "SELECT id::text, key, name FROM cmap.function WHERE id = ANY(%s::uuid[])",
                (wanted,),
            ).fetchall()
        for function_id, key, name in rows:
            names[str(function_id)] = (str(key), str(name))
    out: list[dict[str, Any]] = []
    for report in reports:
        function_id = report.get("function_id")
        if function_id and function_id in names:
            key, name = names[function_id]
            out.append({"id": function_id, "key": key, "name": name})
        else:
            out.append({"id": function_id, "key": None, "name": report["title"]})
    return out


def _global_answer(
    question: str,
    history: list[dict[str, str]],
    settings: Settings,
    usage: dict[str, int],
) -> dict[str, Any]:
    """Company-wide mode: the company report plus function reports by relevance.

    C4 step 3: the function reports are always selected by relevance (the map
    step keeps the points the question needs) — never only above a one-call
    token budget. The company report is included unconditionally (budget
    permitting). D2: superseded findings reach an answer only for questions
    explicitly about the past.
    """
    include_history = is_history_question(question)
    reports = _load_reports(include_history)
    company_reports = [report for report in reports if report["level"] == 2]
    function_reports = [report for report in reports if report["level"] == 1]
    points = (
        _map_points(question, function_reports, settings, usage)
        if function_reports
        else []
    )
    company_lines, company_evidence = _report_items(company_reports)
    point_items = [
        f"- [{point.get('relevance', '')}] {point.get('text', '')} "
        f"(sources: {', '.join(point['source_ids'])})"
        for point in points
    ]
    point_evidence: list[Any] = [
        {"text": str(point.get("text") or ""), "source_ids": list(point["source_ids"])}
        for point in points
    ]
    ceiling = settings.brain_answer_context_tokens
    rendered, context_tokens, kept = _assemble_context(
        [
            (
                "company",
                company_lines,
                lambda items: ("REPORTS:\n" + "\n".join(items)) if items else "",
            ),
            (
                "points",
                point_items,
                lambda items: ("MAPPED POINTS:\n" + "\n".join(items)) if items else "",
            ),
        ],
        ceiling,
    )
    company_kept = set(kept[0])
    points_kept = set(kept[1])
    evidence = [
        item
        for index, item in enumerate(company_evidence)
        if index in company_kept and item is not None
    ] + [
        item
        for index, item in enumerate(point_evidence)
        if index in points_kept and item is not None
    ]
    context = "\n\n".join(text for text in rendered.values() if text)
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
        "functions_consulted": _consulted_functions(function_reports),
        "context_tokens": context_tokens,
    }


def answer_question(
    question: str,
    mode: str = "auto",
    history: list[dict[str, str]] | None = None,
    settings: Settings | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Answer one question; return the step-9 response shape (C4 adds two fields).

    ``mode`` is ``auto``, ``local`` or ``global``. The caller owns any
    session state: only ``history``'s last turns are used, never stored.
    ``auto`` routes first to 0–3 functions (history included, so follow-ups
    inherit scope): none ⇒ company-wide, a confident top function ⇒ scoped,
    low confidence ⇒ the top function's scope plus the company report in one
    prompt. ``local`` forces scoped mode (routing still scopes it; no routed
    function reads the whole map), ``global`` forces company-wide.
    H1 adds ``supported_share`` — the share of sentences the cited quotes
    support, after every other sentence was rewritten or marked. C4 adds
    ``functions_consulted`` and ``context_tokens``.
    """
    cfg = settings if settings is not None else get_settings()
    counters = usage if usage is not None else {}
    turns = list(history or [])
    text = question.strip()
    if not text:
        raise AnswerError("question is required")
    if mode not in {"auto", "local", "global"}:
        raise AnswerError("mode must be auto, local or global")
    if mode == "global":
        return _verify_support(_global_answer(text, turns, cfg, counters), cfg, counters)
    routed = _route_functions(text, turns, cfg, counters)
    routed_ids = [item["id"] for item in routed]
    if mode == "auto" and not routed:
        return _verify_support(_global_answer(text, turns, cfg, counters), cfg, counters)
    if mode == "auto" and routed[0]["weight"] < ROUTE_MIN_WEIGHT:
        # Low routing confidence: the top function's scope plus the company
        # report in ONE prompt — never two answers concatenated (C4 step 5).
        result = _local_answer(
            text,
            turns,
            cfg,
            counters,
            function_ids=[routed[0]["id"]],
            functions_consulted=routed[:1],
            mode_used="hybrid",
            with_company_report=True,
        )
        return _verify_support(result, cfg, counters)
    result = _local_answer(
        text,
        turns,
        cfg,
        counters,
        function_ids=routed_ids or None,
        functions_consulted=routed,
        mode_used="local",
    )
    return _verify_support(result, cfg, counters)
