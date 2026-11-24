"""Kept thread becomes a source (plan_pm_message_intake.md step 1.6, issue #607).

Run: ``python -m brain.intake.ingest [--origin email] [--limit N] [--thread-prefix PREFIX]`` or the
``intake_ingest`` job. Each cleaned, pending thread is rendered as the JSON
turn list the transcript reader accepts (``speaker``, ``text``, ``timestamp``)
and stored as a ``transcript`` source with ``origin`` and ``external_ref``
set and its date taken from the first record (no date model call). The
reader packs its messages into full passages (``read_message_thread``).

A thread that gained messages since it was ingested becomes a NEW source
that supersedes the old one (``cmap.source_version``, origin
``intake_update``); an unchanged thread is skipped.

Spend: refuses to run without BRAIN_INTAKE_MAX_USD, and stops queueing once
the estimated downstream cost of this run reaches the cap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from brain import storage as storage_mod
from brain.config import Settings, get_settings, intake_spend_cap, openai_api_key
from brain.db import enqueue_job, get_pool
from brain.intake.gate import gate_pending_threads
from brain.read.chunk import WINDOW_TOKENS, count_tokens
from brain.seats import message_relations_chosen

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")
REMOVED_MARKER = "[message removed]"
# Upper bound per passage for flat + relations + function_assign (#607). Rounded
# up so BRAIN_INTAKE_MAX_USD trips early rather than late.
EST_USD_PER_PASSAGE = 0.001
EST_USD_PER_PASSAGE_BATCH_3PASS = 0.0018
EST_USD_PER_PASSAGE_SYNC_3PASS = 0.0032
EST_USD_PER_PASSAGE_RAG_ONLY = 0.0002
INTAKE_SWEEP_SECONDS = 3600


def estimated_usd_per_passage(settings: Settings) -> float:
    """Conservative per-passage dollar ceiling for the active message route."""
    if not message_relations_chosen(settings):
        return EST_USD_PER_PASSAGE
    if settings.brain_relations_batch_enabled and openai_api_key(settings):
        return EST_USD_PER_PASSAGE_BATCH_3PASS
    return EST_USD_PER_PASSAGE_SYNC_3PASS


def estimated_usd_per_thread_passage(settings: Settings, tier: str | None) -> float:
    """Per-passage estimate accounting for RAG-only vs full extraction tiers."""
    if tier == "transactional_routine":
        return EST_USD_PER_PASSAGE_RAG_ONLY
    return estimated_usd_per_passage(settings)


def speaker_of(origin: str, author_ref: str | None, raw: dict[str, Any]) -> str:
    """Display name of a message's author, from the record itself."""
    name: Any = None
    if origin == "teams_chat":
        name = ((raw.get("from") or {}).get("user") or {}).get("displayName")
    elif origin == "email":
        name = ((raw.get("from") or {}).get("emailAddress") or {}).get("name")
    elif origin == "clickup":
        if author_ref == "ClickUp":
            return "ClickUp"
        name = (raw.get("user") or {}).get("username") or (
            raw.get("creator") or {}
        ).get("username")
    name = " ".join(str(name or "").split())
    return name or "Unknown"


def safe_time(
    sent_at: datetime | None, collected_at: datetime, now: datetime
) -> datetime:
    """A record's time: its own, else when it was collected; never in the future."""
    t = sent_at or collected_at
    return min(t, now)


def render_thread(rows: list[dict[str, Any]], origin: str, now: datetime) -> str:
    """JSON turn list; a secret-dropped message stays as a marker turn."""
    turns = []
    for r in rows:
        when = safe_time(r["sent_at"], r["collected_at"], now)
        text = REMOVED_MARKER if r["drop_reason"] == "secret" else r["body_text"]
        turns.append(
            {
                "speaker": speaker_of(origin, r["author_ref"], r["raw"] or {}),
                "text": text,
                "timestamp": when.astimezone(UTC).isoformat(),
            }
        )
    return json.dumps(turns, ensure_ascii=False, indent=0)


def estimate_passages(text_tokens: int) -> int:
    return max(1, -(-text_tokens // WINDOW_TOKENS))


def _threads(
    conn: Any,
    origin: str | None,
    limit: int | None,
    prefix: str | None = None,
    since: datetime | None = None,
) -> list[tuple]:
    sql = (
        "SELECT origin, thread_key, title, source_id, tier FROM cmap.intake_thread "
        "WHERE verdict = 'kept' "
        + ("AND origin = %(o)s " if origin else "")
        + ("AND starts_with(thread_key, %(prefix)s) " if prefix is not None else "")
        + (
            "AND COALESCE(ended_at, started_at, updated_at) >= %(since)s "
            if since is not None
            else ""
        )
        + "ORDER BY started_at NULLS LAST, thread_key"
        + (" LIMIT %(n)s" if limit else "")
    )
    return conn.execute(
        sql, {"o": origin, "n": limit, "prefix": prefix, "since": since}
    ).fetchall()


def _items(conn: Any, origin: str, key: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT author_ref, sent_at, body_text, raw, drop_reason, collected_at "
        "FROM cmap.intake_item WHERE origin = %s AND thread_key = %s "
        "AND (drop_reason IS NULL OR drop_reason = 'secret') "
        "ORDER BY sent_at NULLS LAST, id",
        (origin, key),
    ).fetchall()
    cols = ("author_ref", "sent_at", "body_text", "raw", "drop_reason", "collected_at")
    return [dict(zip(cols, r, strict=True)) for r in rows]


def _source_routing_for_tier(tier: str | None) -> tuple[str, bool]:
    if tier == "transactional_routine":
        return "rag_only", False
    return "full", True


def ingest_thread(
    conn: Any,
    origin: str,
    key: str,
    title: str | None,
    old_source: Any,
    now: datetime,
    *,
    tier: str | None = None,
    can_afford: Callable[[int], bool] | None = None,
) -> tuple[str, int]:
    """Store one thread as a source. Returns (outcome, estimated passages).

    outcome: 'created', 'versioned', 'unchanged', 'empty' or 'capped'.
    """
    rows = _items(conn, origin, key)
    if not any(r["drop_reason"] is None for r in rows):
        return "empty", 0
    rendered = render_thread(rows, origin, now)
    data = rendered.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    ingest_tier, map_eligible = _source_routing_for_tier(tier)
    existing = conn.execute(
        "SELECT id::text FROM cmap.source WHERE sha256 = %s", (sha,)
    ).fetchone()
    if existing is not None:
        conn.execute(
            "UPDATE cmap.source SET ingest_tier = %s, map_eligible = %s "
            "WHERE id = %s AND (ingest_tier IS DISTINCT FROM %s OR map_eligible IS DISTINCT FROM %s)",
            (ingest_tier, map_eligible, existing[0], ingest_tier, map_eligible),
        )
        conn.execute(
            "UPDATE cmap.intake_thread SET verdict = 'kept', source_id = %s, updated_at = now() "
            "WHERE origin = %s AND thread_key = %s",
            (existing[0], origin, key),
        )
        return "unchanged", 0
    text_tokens = sum(count_tokens(r["body_text"] or "") for r in rows)
    passages = estimate_passages(text_tokens)
    if can_afford is not None and not can_afford(passages):
        return "capped", passages
    source_id = str(uuid.uuid4())
    storage_path = f"cmap/{source_id}/thread.json"
    storage_mod.get_storage().upload(storage_path, data, "application/json")
    started = safe_time(rows[0]["sent_at"], rows[0]["collected_at"], now)
    conn.execute(
        "INSERT INTO cmap.source (id, kind, title, original_filename, storage_path, sha256, "
        "bytes, effective_date, date_origin, origin, external_ref, read_state, ingest_tier, map_eligible) "
        "VALUES (%s, 'transcript', %s, 'thread.json', %s, %s, %s, %s, 'message_record', "
        "%s, %s, 'queued', %s, %s)",
        (
            source_id,
            (title or f"{origin} thread")[:300],
            storage_path,
            sha,
            len(data),
            started.astimezone(EASTERN).date(),
            origin,
            key,
            ingest_tier,
            map_eligible,
        ),
    )
    outcome = "created"
    if old_source is not None:
        conn.execute(
            "INSERT INTO cmap.source_version (source_id, supersedes_source_id, origin, decided_at) "
            "VALUES (%s, %s, 'intake_update', now()) ON CONFLICT DO NOTHING",
            (source_id, str(old_source)),
        )
        outcome = "versioned"
    conn.execute(
        "UPDATE cmap.intake_thread SET verdict = 'kept', source_id = %s, updated_at = now() "
        "WHERE origin = %s AND thread_key = %s",
        (source_id, origin, key),
    )
    return outcome, passages


def run(
    settings: Settings,
    origin: str | None = None,
    limit: int | None = None,
    *,
    thread_prefix: str | None = None,
    days: int | None = None,
    run_gate: bool = True,
) -> dict[str, Any]:
    """Gate pending threads, then ingest kept threads until done or spend cap reached."""
    if thread_prefix is not None and not thread_prefix.strip():
        raise ValueError("the thread prefix must not be empty")
    if days is not None and days <= 0:
        raise ValueError("days must be positive")
    cap = intake_spend_cap(settings)
    now = datetime.now(UTC)
    since = now - timedelta(days=days) if days is not None else None
    counts: dict[str, Any] = {"estimated_usd": 0.0}
    queued: list[str] = []
    pool = get_pool(settings)
    with pool.connection() as conn:
        if run_gate:
            gate_stats = gate_pending_threads(
                conn,
                settings,
                origin=origin,
                limit=limit,
                thread_prefix=thread_prefix,
                since=since,
            )
            if gate_stats["judged"] or gate_stats["errors"]:
                counts["gate"] = gate_stats
        for th_origin, key, title, old, tier in _threads(
            conn, origin, limit, thread_prefix, since=since
        ):
            per_passage = estimated_usd_per_thread_passage(settings, tier)
            outcome, passages = ingest_thread(
                conn,
                th_origin,
                key,
                title,
                old,
                now,
                tier=tier,
                can_afford=lambda p, rate=per_passage: (
                    counts["estimated_usd"] + p * rate <= cap
                ),
            )
            if outcome == "capped":
                counts["stopped_at_cap"] = True
                break
            cost = passages * per_passage
            if outcome in ("created", "versioned"):
                counts["estimated_usd"] += cost
                sid = conn.execute(
                    "SELECT source_id::text FROM cmap.intake_thread "
                    "WHERE origin = %s AND thread_key = %s",
                    (th_origin, key),
                ).fetchone()[0]
                queued.append(sid)
            conn.commit()
            counts[outcome] = counts.get(outcome, 0) + 1
    for sid in queued:
        enqueue_job("read_source", {"source_id": sid}, settings)
    counts["estimated_usd"] = round(counts["estimated_usd"], 4)
    return counts


def _parse_positive_int(raw: Any, field_name: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    if isinstance(raw, int):
        val = raw
    elif isinstance(raw, str):
        try:
            val = int(raw)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a positive integer") from exc
    else:
        raise ValueError(f"{field_name} must be a positive integer")
    if val <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return val


def handle_intake_ingest(job: dict[str, Any]) -> None:
    payload = job.get("payload") or {}
    days = _parse_positive_int(payload.get("days"), "days")
    limit = _parse_positive_int(payload.get("limit"), "limit")
    counts = run(
        get_settings(),
        payload.get("origin"),
        limit,
        thread_prefix=payload.get("thread_prefix"),
        days=days,
    )
    logger.info("intake_ingest: %s", counts)


def maybe_queue_intake(settings: Settings | None = None) -> bool:
    """Queue one ``intake_ingest`` an hour; does nothing unless BRAIN_INTAKE_ENABLED."""
    cfg = settings if settings is not None else get_settings()
    if not cfg.brain_intake_enabled or not cfg.brain_intake_max_usd:
        return False
    with get_pool(cfg).connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'intake_ingest', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'intake_ingest' "
            "AND (state IN ('queued', 'running') "
            "OR finished_at > now() - make_interval(secs => %s))) RETURNING id",
            (INTAKE_SWEEP_SECONDS,),
        ).fetchone()
        conn.commit()
    return row is not None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", choices=["clickup", "teams_chat", "email"])
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--days", type=int, help="Only ingest threads active within the last N days"
    )
    ap.add_argument(
        "--thread-prefix", help="Only import threads with this literal key prefix"
    )
    a = ap.parse_args(argv)
    result = run(
        get_settings(),
        a.origin,
        a.limit,
        thread_prefix=a.thread_prefix,
        days=a.days,
    )
    print(f"intake_ingest: {result}")


if __name__ == "__main__":
    main()
