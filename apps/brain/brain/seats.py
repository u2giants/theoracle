"""Per-stage model seats (Albert's direction 2026-11-03).

Each of the nine model-touching stages reads its model from
``cmap.model_seat`` when the admin model page has set one, else from the env
seat it always used (plan §11). Model ids still never appear in code: the
table holds whatever the admin picked, and the env stays the fallback.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from brain.config import Settings
from brain.db import get_pool

STAGES = (
    "vision",
    "embed",
    "flat",
    "relations",
    "resolve",
    "reports",
    "answer",
    "recommend",
    "grade",
)

# Seats change rarely; a short cache keeps one lookup per call off the hot path
# while a page change still lands within seconds.
_CACHE_SECONDS = 15.0
_cache: dict[str, str] = {}
_cache_at = 0.0
_lock = threading.Lock()


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
    except Exception:  # noqa: BLE001 - no table yet / no database: env seats apply
        rows = []
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
    if stage == "answer":
        return settings.brain_chat_model or settings.brain_frontier_model
    if stage == "grade":
        return settings.brain_eval_model or settings.brain_frontier_model
    return settings.brain_frontier_model


def stage_model(settings: Settings, stage: str) -> str | None:
    """The model a stage should call: the page's seat, else its env seat."""
    if stage not in STAGES:
        raise ValueError(f"unknown model stage {stage!r}")
    return _db_seats().get(stage) or env_model(settings, stage)


def seat_report(settings: Settings) -> dict[str, dict[str, Any]]:
    """Every stage's live model and whether the page or the env set it."""
    seats = _db_seats()
    return {
        stage: {
            "model": seats.get(stage) or env_model(settings, stage),
            "source": "page" if stage in seats else "env",
            "env_model": env_model(settings, stage),
        }
        for stage in STAGES
    }


def set_seat(stage: str, model: str, updated_by: str | None) -> None:
    """Store the page's choice for one stage."""
    if stage not in STAGES:
        raise ValueError(f"unknown model stage {stage!r}")
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO cmap.model_seat (stage, model, updated_by) VALUES (%s, %s, %s) "
            "ON CONFLICT (stage) DO UPDATE SET model = EXCLUDED.model, "
            "updated_at = now(), updated_by = EXCLUDED.updated_by",
            (stage, model, updated_by),
        )
        conn.commit()
    clear_cache()
