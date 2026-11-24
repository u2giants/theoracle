"""Per-stage model seats (Albert's direction 2026-11-03).

Each of the model-touching stages reads its model from
``cmap.model_seat`` when the admin model page has set one, else from the env
seat it always used (plan §11). Model ids still never appear in code: the
table holds whatever the admin picked, and the env stays the fallback.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import psycopg
from psycopg import errors as pg_errors

from brain.config import Settings
from brain.db import get_pool

STAGES = (
    "vision",
    "embed",
    "flat",
    "relations",
    "relations_messages",
    "resolve",
    "process",
    "reports",
    "answer",
    "recommend",
    "grade",
    "contradictions",
    "converse",
    "intake_gate",
)

# Seats change rarely; a short cache keeps one lookup per call off the hot path
# while a page change still lands within seconds.
_CACHE_SECONDS = 15.0
_cache: dict[str, str] = {}
_cache_at = 0.0
_lock = threading.Lock()

logger = logging.getLogger(__name__)


def clear_cache() -> None:
    """Forget cached seats (after a change, and in tests)."""
    global _cache_at
    with _lock:
        _cache.clear()
        _cache_at = 0.0


def _db_seats() -> dict[str, str]:
    global _cache_at
    with _lock:
        if time.monotonic() - _cache_at < _CACHE_SECONDS:
            return dict(_cache)
    try:
        with get_pool().connection() as conn:
            rows = conn.execute("SELECT stage, model FROM cmap.model_seat").fetchall()
    except pg_errors.UndefinedTable:
        rows = []  # before migration 005: env seats apply, and that is stable
    except Exception as exc:  # noqa: BLE001 - a transient read failure
        # Never cache a failure as "no seats": that would silently swap every
        # stage back to its env seat for the cache window. Keep the last good
        # seats (if any) and retry on the next call.
        logger.warning("model seat read failed; keeping last known seats: %s", exc)
        with _lock:
            return dict(_cache)
    seats = {str(stage): str(model) for stage, model in rows}
    with _lock:
        _cache.clear()
        _cache.update(seats)
        _cache_at = time.monotonic()
    return seats


def env_model(settings: Settings, stage: str) -> str | None:
    """The env seat a stage used before the admin page could choose."""
    if stage == "vision":
        return settings.brain_vision_model
    if stage == "embed":
        return settings.brain_embed_model
    if stage in {"answer", "converse"}:
        # The interview composer (#604) defaults to the seat follow-ups used.
        return settings.brain_chat_model or settings.brain_frontier_model
    if stage == "grade":
        return settings.brain_eval_model or settings.brain_frontier_model
    if stage == "flat":
        return settings.brain_flat_model or settings.brain_frontier_model
    if stage == "relations_messages":
        return settings.brain_message_relations_model or settings.brain_frontier_model
    if stage == "intake_gate":
        return (
            settings.brain_intake_gate_model
            or settings.brain_message_relations_model
            or settings.brain_frontier_model
        )
    if stage == "contradictions":
        return settings.brain_contradictions_model or settings.brain_frontier_model
    return settings.brain_frontier_model


def _resolve_stage(
    settings: Settings, stage: str, seats: dict[str, str]
) -> tuple[str | None, str]:
    """Return ``(model, source)`` for ``stage``, keeping stage_model and seat_report aligned."""
    if stage not in STAGES:
        raise ValueError(f"unknown model stage {stage!r}")
    if stage == "relations_messages":
        if seats.get("relations_messages"):
            return seats["relations_messages"], "page"
        if settings.brain_message_relations_model:
            return settings.brain_message_relations_model, "env"
        if seats.get("relations"):
            return seats["relations"], "page"
        return settings.brain_frontier_model, "env"
    if stage == "intake_gate":
        if seats.get("intake_gate"):
            return seats["intake_gate"], "page"
        if settings.brain_intake_gate_model:
            return settings.brain_intake_gate_model, "env"
        if seats.get("relations_messages"):
            return seats["relations_messages"], "page"
        if settings.brain_message_relations_model:
            return settings.brain_message_relations_model, "env"
        return settings.brain_frontier_model, "env"
    if seats.get(stage):
        return seats[stage], "page"
    return env_model(settings, stage), "env"


def stage_model(settings: Settings, stage: str) -> str | None:
    """The model a stage should call: the page's seat, else its env seat."""
    model, _source = _resolve_stage(settings, stage, _db_seats())
    return model


def message_relations_chosen(settings: Settings) -> bool:
    """Whether a dedicated message-relations seat or env model is configured (#607)."""
    return (
        "relations_messages" in _db_seats()
        or settings.brain_message_relations_model is not None
    )


def flat_model_chosen(settings: Settings) -> bool:
    """Whether a model (not ScaleDown /extract) picks up every chunk's entities.

    Set by a page seat for the flat stage or by ``BRAIN_FLAT_MODEL``; without
    either, ScaleDown extracts and the frontier model is only the fallback.
    """
    return "flat" in _db_seats() or settings.brain_flat_model is not None


def seat_report(settings: Settings) -> dict[str, dict[str, Any]]:
    """Every stage's live model and whether the page or the env set it."""
    seats = _db_seats()
    report: dict[str, dict[str, Any]] = {}
    for stage in STAGES:
        model, source = _resolve_stage(settings, stage, seats)
        report[stage] = {
            "model": model,
            "source": source,
            "env_model": env_model(settings, stage),
        }
    return report


def set_seat(
    stage: str,
    model: str,
    updated_by: str | None,
    conn: psycopg.Connection | None = None,
) -> None:
    """Store the page's choice for one stage.

    With ``conn`` the write joins the caller's transaction (the caller commits
    and then calls ``clear_cache``); without it the seat commits on its own.
    """
    if stage not in STAGES:
        raise ValueError(f"unknown model stage {stage!r}")
    if conn is not None:
        _write_seat(conn, stage, model, updated_by)
        return
    with get_pool().connection() as own:
        _write_seat(own, stage, model, updated_by)
        own.commit()
    clear_cache()


def _write_seat(
    conn: psycopg.Connection, stage: str, model: str, updated_by: str | None
) -> None:
    conn.execute(
        "INSERT INTO cmap.model_seat (stage, model, updated_by) VALUES (%s, %s, %s) "
        "ON CONFLICT (stage) DO UPDATE SET model = EXCLUDED.model, "
        "updated_at = now(), updated_by = EXCLUDED.updated_by",
        (stage, model, updated_by),
    )
