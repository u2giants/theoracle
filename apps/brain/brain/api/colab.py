"""Pull-based Google Colab batch lease, submit, and status endpoints (#664 Step 3.2).

Ephemeral Colab GPU workers borrow small batches of ``relations`` prompts via
``POST /colab/lease`` (15-minute default TTL, hard ceiling 30 minutes) and
submit raw JSON strings back to ``POST /colab/submit`` for authoritative
server-side ``parse_relations_json`` + ``validate_response`` + mention embedding.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, field_validator

from brain.api.deps import User, admin_or_service, require_colab_worker
from brain.colab_packet import (
    DEFAULT_PACKET_MAX_TOKENS,
    MODEL_TAG_RE,
    ColabPacketError,
    ValidatedChunkItem,
    WindowSpec,
    export_relations_schema,
    load_source_windows,
    persist_validated_items,
    validate_chunk_submission,
)
from brain.config import get_settings
from brain.db import get_pool
from brain.extract.relations import DROP_REASONS, relations_prompt_hash

router = APIRouter(prefix="/colab", tags=["colab"])

MAX_SUBMIT_BYTES = 10 * 1024 * 1024  # 10 MB hard request body cap

_SWEEP_EXPIRED_SQL = """
WITH expired AS (
  UPDATE cmap.colab_lease
  SET state = 'expired'
  WHERE state = 'active' AND expires_at <= now()
  RETURNING id
)
UPDATE cmap.colab_lease_item AS cli
SET state = 'failed'
FROM expired
WHERE cli.lease_id = expired.id AND cli.state = 'leased'
"""

_SELECT_CANDIDATE_CHUNKS_SQL = """
SELECT c.id::text, c.source_id::text
FROM cmap.chunk AS c
JOIN cmap.source AS s ON s.id = c.source_id
WHERE s.colab_offload = true
  AND (
    c.passage_kind IS NOT NULL
    OR EXISTS (SELECT 1 FROM cmap.mention AS m0 WHERE m0.chunk_id = c.id)
  )
  AND (
    COALESCE(c.passage_kind, '') <> 'chatter'
    OR EXISTS (SELECT 1 FROM cmap.mention AS m1 WHERE m1.chunk_id = c.id)
  )
  AND NOT EXISTS (
    SELECT 1
    FROM cmap.interview_turn AS it
    JOIN cmap.interview_conversation AS ic ON ic.id = it.conversation_id
    WHERE it.source_id = s.id AND ic.state = 'processing'
  )
  AND NOT EXISTS (
    SELECT 1
    FROM cmap.job AS j
    WHERE j.kind IN ('read_source', 'classify_extract')
      AND j.payload->>'source_id' = s.id::text
      AND j.state IN ('queued', 'running')
  )
  AND NOT EXISTS (
    SELECT 1
    FROM cmap.extraction AS e
    WHERE e.chunk_id = c.id
      AND e.stage = 'relations'
      AND e.prompt_hash = %s
  )
  AND NOT EXISTS (
    SELECT 1
    FROM cmap.colab_lease_item AS cli
    WHERE cli.chunk_id = c.id AND cli.state = 'leased'
  )
ORDER BY s.created_at, c.ordinal
LIMIT %s
FOR UPDATE OF c SKIP LOCKED
"""


class LeaseRequest(BaseModel):
    """Payload for ``POST /colab/lease``."""

    worker_id: str = Field(min_length=1, max_length=128)
    max_items: int = Field(default=64, ge=1, le=256)

    @field_validator("worker_id")
    @classmethod
    def _clean_worker_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("worker_id must not be blank")
        return stripped


class SubmitItem(BaseModel):
    """One chunk completion inside ``POST /colab/submit``."""

    chunk_id: UUID
    raw_content: str = Field(min_length=1)
    finish_reason: str | None = None


class SubmitRequest(BaseModel):
    """Payload for ``POST /colab/submit``."""

    lease_id: UUID
    prompt_hash: str = Field(min_length=16, max_length=128)
    model_tag: str
    results: list[SubmitItem] = Field(min_length=1, max_length=256)

    @field_validator("model_tag")
    @classmethod
    def _validate_model_tag(cls, value: str) -> str:
        if MODEL_TAG_RE.fullmatch(value) is None:
            raise ValueError(
                "model_tag must match ^colab-vllm/[A-Za-z0-9._/@:+-]{3,120}$"
            )
        return value


def sweep_expired_leases(conn: Any) -> int:
    """Expire stale active leases and release their leased chunk slots."""
    res = conn.execute(_SWEEP_EXPIRED_SQL)
    return int(res.rowcount or 0)


def claim_lease_batch(
    conn: Any,
    *,
    worker_id: str,
    limit: int,
    prompt_hash: str,
    ttl_seconds: int,
) -> tuple[str | None, datetime | None, list[tuple[str, str]]]:
    """Atomically sweep expired leases and lock up to ``limit`` pending chunks."""
    sweep_expired_leases(conn)
    rows = conn.execute(_SELECT_CANDIDATE_CHUNKS_SQL, (prompt_hash, limit)).fetchall()
    if not rows:
        conn.commit()
        return None, None, []

    lease_row = conn.execute(
        "INSERT INTO cmap.colab_lease (worker_id, prompt_hash, expires_at, chunk_count) "
        "VALUES (%s, %s, now() + make_interval(secs => %s), %s) "
        "RETURNING id::text, expires_at",
        (worker_id, prompt_hash, ttl_seconds, len(rows)),
    ).fetchone()
    assert lease_row is not None
    lease_id = str(lease_row[0])
    expires_at: datetime = lease_row[1]

    claimed: list[tuple[str, str]] = []
    for cid, sid in rows:
        chunk_id, source_id = str(cid), str(sid)
        conn.execute(
            "INSERT INTO cmap.colab_lease_item (lease_id, chunk_id, source_id, state) "
            "VALUES (%s, %s, %s, 'leased')",
            (lease_id, chunk_id, source_id),
        )
        claimed.append((chunk_id, source_id))
    conn.commit()
    return lease_id, expires_at, claimed


@router.post("/lease")
def lease_chunks(
    req: LeaseRequest,
    _worker: Annotated[None, Depends(require_colab_worker)],
) -> dict[str, Any]:
    """Claim a bounded 15-minute batch of pending ``colab_offload`` chunks."""
    settings = get_settings()
    limit = min(req.max_items, settings.brain_colab_max_batch_size)
    prompt_hash = relations_prompt_hash()

    with get_pool().connection() as conn:
        lease_id, expires_at, claimed = claim_lease_batch(
            conn,
            worker_id=req.worker_id,
            limit=limit,
            prompt_hash=prompt_hash,
            ttl_seconds=settings.brain_colab_lease_ttl_seconds,
        )

    schema = export_relations_schema()
    if not claimed or lease_id is None or expires_at is None:
        return {
            "lease_id": None,
            "expires_at": None,
            "prompt_hash": prompt_hash,
            "relations_schema": schema,
            "items": [],
        }

    source_ids = list(dict.fromkeys(sid for _cid, sid in claimed))
    windows_by_chunk: dict[str, WindowSpec] = {}
    for source_id in source_ids:
        _done, eligible, _pending = load_source_windows(
            source_id, prompt_hash, only_pending=False
        )
        windows_by_chunk.update(eligible)

    items: list[dict[str, Any]] = []
    for chunk_id, source_id in claimed:
        spec = windows_by_chunk.get(chunk_id)
        if spec is None:
            continue
        items.append(
            {
                "chunk_id": chunk_id,
                "source_id": source_id,
                "max_tokens": DEFAULT_PACKET_MAX_TOKENS,
                "prompt": spec.prompt,
            }
        )

    return {
        "lease_id": lease_id,
        "expires_at": expires_at.isoformat(),
        "prompt_hash": prompt_hash,
        "relations_schema": schema,
        "items": items,
    }


async def _read_bounded_body(request: Request, max_bytes: int) -> bytes:
    """Read request body up to ``max_bytes`` BEFORE JSON parsing (413 on overflow)."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"request body exceeds {max_bytes} bytes",
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"request body exceeds {max_bytes} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/submit")
async def submit_lease(
    request: Request,
    _worker: Annotated[None, Depends(require_colab_worker)],
) -> dict[str, Any]:
    """Validate and persist model outputs for an active Colab lease."""
    raw_body = await _read_bounded_body(request, MAX_SUBMIT_BYTES)
    try:
        req = SubmitRequest.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False, include_context=False),
        ) from exc

    seen_chunks: set[str] = set()
    for item in req.results:
        cid_str = str(item.chunk_id)
        if cid_str in seen_chunks:
            raise HTTPException(status_code=400, detail=f"duplicate chunk_id {cid_str}")
        seen_chunks.add(cid_str)

    current_hash = relations_prompt_hash()
    lease_id_str = str(req.lease_id)

    with get_pool().connection() as conn:
        lease_row = conn.execute(
            "SELECT state, prompt_hash, (expires_at <= now()) "
            "FROM cmap.colab_lease WHERE id = %s FOR UPDATE",
            (lease_id_str,),
        ).fetchone()
        if lease_row is None:
            raise HTTPException(status_code=409, detail="unknown lease_id")

        lease_state, lease_prompt_hash, is_expired = (
            str(lease_row[0]),
            str(lease_row[1]),
            bool(lease_row[2]),
        )
        if lease_state != "active" or is_expired:
            if lease_state == "active" and is_expired:
                conn.execute(
                    "UPDATE cmap.colab_lease SET state = 'expired' WHERE id = %s",
                    (lease_id_str,),
                )
                conn.execute(
                    "UPDATE cmap.colab_lease_item SET state = 'failed' "
                    "WHERE lease_id = %s AND state = 'leased'",
                    (lease_id_str,),
                )
                conn.commit()
            raise HTTPException(status_code=409, detail="lease is expired or no longer active")

        if req.prompt_hash != current_hash or lease_prompt_hash != current_hash:
            conn.execute(
                "UPDATE cmap.colab_lease SET state = 'expired' WHERE id = %s",
                (lease_id_str,),
            )
            conn.execute(
                "UPDATE cmap.colab_lease_item SET state = 'failed' "
                "WHERE lease_id = %s AND state = 'leased'",
                (lease_id_str,),
            )
            conn.commit()
            raise HTTPException(status_code=409, detail="prompt_hash mismatch")

        item_rows = conn.execute(
            "SELECT chunk_id::text, source_id::text FROM cmap.colab_lease_item "
            "WHERE lease_id = %s AND state = 'leased'",
            (lease_id_str,),
        ).fetchall()
        leased_map = {str(cid): str(sid) for cid, sid in item_rows}

        for item in req.results:
            cid_str = str(item.chunk_id)
            if cid_str not in leased_map:
                raise HTTPException(
                    status_code=400,
                    detail=f"chunk_id {cid_str} does not belong to active lease {lease_id_str}",
                )

    needed_sources = list(
        dict.fromkeys(leased_map[str(item.chunk_id)] for item in req.results)
    )
    windows_by_chunk: dict[str, WindowSpec] = {}
    for source_id in needed_sources:
        _done, eligible, _pending = load_source_windows(
            source_id, current_hash, only_pending=False
        )
        windows_by_chunk.update(eligible)

    validated_items: list[ValidatedChunkItem] = []
    for item in req.results:
        cid_str = str(item.chunk_id)
        spec = windows_by_chunk.get(cid_str)
        if spec is None:
            raise HTTPException(
                status_code=400,
                detail=f"chunk_id {cid_str} is no longer eligible",
            )
        try:
            v_item = validate_chunk_submission(
                spec,
                raw_content=item.raw_content,
                finish_reason=item.finish_reason,
                model_full=req.model_tag,
            )
        except ColabPacketError as exc:
            # Cut-off JSON before the first array item arrived: salvage as empty truncated reply
            if item.raw_content.lstrip().startswith("{"):
                drops = dict.fromkeys(DROP_REASONS, 0)
                drops["truncation"] = 1
                v_item = ValidatedChunkItem(
                    source_id=spec.source_id,
                    chunk_id=spec.chunk_id,
                    model=req.model_tag,
                    known={k.key: k for k in spec.known},
                    payload={"relations": [], "new_mentions": [], "truncated": True},
                    relations=[],
                    new_mentions=[],
                    drops=drops,
                    truncated=True,
                )
            else:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        validated_items.append(v_item)

    settings = get_settings()
    completed_sources = persist_validated_items(
        validated_items,
        prompt_hash=current_hash,
        settings=settings,
    )

    accepted_ids = [item.chunk_id for item in validated_items]
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.colab_lease_item SET state = 'accepted' "
            "WHERE lease_id = %s AND chunk_id = ANY(%s::uuid[])",
            (lease_id_str, accepted_ids),
        )
        still_leased = conn.execute(
            "SELECT 1 FROM cmap.colab_lease_item WHERE lease_id = %s AND state = 'leased' LIMIT 1",
            (lease_id_str,),
        ).fetchone()
        if still_leased is None:
            conn.execute(
                "UPDATE cmap.colab_lease "
                "SET state = 'completed', model_tag = %s, completed_at = now() "
                "WHERE id = %s",
                (req.model_tag, lease_id_str),
            )
        conn.commit()

    total_drops = dict.fromkeys(DROP_REASONS, 0)
    for item in validated_items:
        for reason, amount in item.drops.items():
            total_drops[reason] = total_drops.get(reason, 0) + amount

    return {
        "lease_id": lease_id_str,
        "accepted_chunks": len(validated_items),
        "relations_written": sum(len(i.relations) for i in validated_items),
        "new_mentions_written": sum(len(i.new_mentions) for i in validated_items),
        "drops": total_drops,
        "completed_sources": completed_sources,
    }


@router.get("/status")
def colab_status(
    _caller: Annotated[User | None, Depends(admin_or_service)],
) -> dict[str, Any]:
    """Return pending Colab offload queue depth, active leases, and 24h throughput."""
    settings = get_settings()
    prompt_hash = relations_prompt_hash()
    with get_pool().connection() as conn:
        sweep_expired_leases(conn)
        conn.commit()

        pending_row = conn.execute(
            "SELECT count(*) FROM cmap.chunk AS c "
            "JOIN cmap.source AS s ON s.id = c.source_id "
            "WHERE s.colab_offload = true "
            "AND (c.passage_kind IS NOT NULL OR EXISTS (SELECT 1 FROM cmap.mention m0 WHERE m0.chunk_id = c.id)) "
            "AND (COALESCE(c.passage_kind, '') <> 'chatter' OR EXISTS (SELECT 1 FROM cmap.mention m1 WHERE m1.chunk_id = c.id)) "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM cmap.extraction e "
            "  WHERE e.chunk_id = c.id AND e.stage = 'relations' AND e.prompt_hash = %s"
            ")",
            (prompt_hash,),
        ).fetchone()
        active_row = conn.execute(
            "SELECT count(*) FROM cmap.colab_lease WHERE state = 'active' AND expires_at > now()"
        ).fetchone()
        completed_24h_row = conn.execute(
            "SELECT count(*) FROM cmap.extraction e "
            "JOIN cmap.chunk c ON c.id = e.chunk_id "
            "JOIN cmap.source s ON s.id = c.source_id "
            "WHERE s.colab_offload = true AND e.stage = 'relations' "
            "AND e.model LIKE 'colab-vllm/%%' "
            "AND e.created_at >= now() - interval '24 hours'"
        ).fetchone()
        drop_rows = conn.execute(
            "SELECT read_notes->'drop_reasons' FROM cmap.source WHERE colab_offload = true"
        ).fetchall()

    drops_total = dict.fromkeys(DROP_REASONS, 0)
    for (drop_obj,) in drop_rows:
        if isinstance(drop_obj, dict):
            for reason in DROP_REASONS:
                drops_total[reason] += int(drop_obj.get(reason) or 0)

    return {
        "lease_enabled": settings.brain_colab_lease_enabled,
        "pending_chunks": int(pending_row[0]) if pending_row else 0,
        "active_leases": int(active_row[0]) if active_row else 0,
        "completed_chunks_24h": int(completed_24h_row[0]) if completed_24h_row else 0,
        "drop_reasons": drops_total,
    }
