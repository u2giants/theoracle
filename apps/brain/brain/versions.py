"""Source supersession (repair plan D2).

One source can be a newer version of another. ``cmap.source_version`` records
that link (``source_id`` is the newer document, ``supersedes_source_id`` the
older one); a row with ``decided_at IS NULL`` is a pending proposal awaiting
the one-click confirm on the sources page.

Detection runs at upload (``detect_title``): same normalised title key, or —
once the first chunks are embedded during ``read_source`` — mean-pooled
embedding similarity of the first 3 chunks >= ``SIMILARITY_THRESHOLD`` with a
different content hash. Auto-accept only when the title key matches AND the
new source's ``effective_date`` is strictly later (and the title is specific
enough — ``AUTO_ACCEPT_MIN_TITLE_TOKENS``); everything else is a proposal.

``cmap.relation.status`` is COMPUTED, never hand-set: ``recompute_relation_status``
marks a relation ``superseded`` when every source supporting its fact is
superseded, else ``current``. The DB trigger added in ``sql/028`` rejects any
hand-set UPDATE. Mentions carry no column: the same rule is applied at query
time (a mention is history-only when every mention of its entity sits in a
superseded source).

Supersession never blocks ingestion or reading; detection failures are logged
and the upload continues.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from brain.text_util import fold_key

logger = logging.getLogger(__name__)

# Tuned thresholds (D2): see the PR body for the rationale.
SIMILARITY_THRESHOLD = 0.9
SIMILARITY_FIRST_CHUNKS = 3
# Auto-accept needs a specific title: one-word titles ("Transcript", "Handbook")
# collide across unrelated documents and must go to the one-click confirm.
AUTO_ACCEPT_MIN_TITLE_TOKENS = 2

ORIGIN_AUTO_TITLE = "auto_title"
ORIGIN_AUTO_SIMILARITY = "auto_similarity"
ORIGIN_ADMIN = "admin"

_TITLE_EXTENSIONS = frozenset(
    {
        "pdf", "docx", "xlsx", "pptx", "txt", "text", "md", "csv", "tsv",
        "png", "jpg", "jpeg", "svg", "json", "vtt", "doc", "xls", "ppt",
    }
)
_EXT_RE = re.compile(r"\.([A-Za-z0-9]{1,5})$")


def title_key(title: str) -> str:
    """Normalised title key: drop a known file extension, then ``fold_key``.

    G1's content-key style: "Widget Policy.pdf" and "WIDGET POLICY" both fold
    to ``widget policy``. Unknown dotted suffixes are kept ("Q3.report" is a
    title, not a file name).
    """
    text = (title or "").strip()
    match = _EXT_RE.search(text)
    if match and match.group(1).casefold() in _TITLE_EXTENSIONS:
        text = text[: match.start()]
    return fold_key(text)


def superseded_source_ids(conn: Any) -> set[str]:
    """Ids of every source a decided supersession replaces (the older ones)."""
    rows = conn.execute(
        "SELECT supersedes_source_id::text FROM cmap.source_version "
        "WHERE decided_at IS NOT NULL"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _vector(text: str) -> list[float]:
    """Parse a pgvector ``::text`` value back into floats."""
    return [float(part) for part in text.strip("[]").split(",") if part]


def _mean(vectors: list[list[float]]) -> list[float]:
    size = len(vectors[0])
    total = [0.0] * size
    for vector in vectors:
        for index, value in enumerate(vector):
            total[index] += value
    return [value / len(vectors) for value in total]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _first_chunk_means(conn: Any) -> dict[str, list[float]]:
    """Mean-pooled embedding of each source's first ``SIMILARITY_FIRST_CHUNKS`` chunks."""
    rows = conn.execute(
        "SELECT source_id::text, embedding::text FROM ("
        "  SELECT source_id, embedding, "
        "    row_number() OVER (PARTITION BY source_id ORDER BY ordinal) AS rn "
        "  FROM cmap.chunk WHERE embedding IS NOT NULL"
        ") ranked WHERE rn <= %s",
        (SIMILARITY_FIRST_CHUNKS,),
    ).fetchall()
    by_source: dict[str, list[list[float]]] = {}
    for source_id, raw in rows:
        by_source.setdefault(str(source_id), []).append(_vector(str(raw)))
    return {source_id: _mean(vectors) for source_id, vectors in by_source.items()}


def _queue_project(conn: Any) -> None:
    """Queue one whole-corpus ``project`` job unless one is waiting."""
    conn.execute(
        "INSERT INTO cmap.job (kind, payload) SELECT 'project', '{}'::jsonb "
        "WHERE NOT EXISTS (SELECT 1 FROM cmap.job "
        "WHERE kind = 'project' AND state = 'queued')"
    )


def recompute_relation_status(conn: Any) -> dict[str, int]:
    """Recompute ``cmap.relation.status`` for every row; return the counts.

    Fact key = (from entity or normalised mention key, rel_type, to entity or
    normalised mention key). The fact is ``superseded`` iff every source of
    every relation row sharing the key is superseded — so a fact that also
    lives in a live source stays ``current`` everywhere (D2 gate). This is
    the only writer of the column (guarded by the SQL trigger).
    """
    conn.execute("SELECT set_config('cmap.status_recompute', 'on', true)")
    rows = conn.execute(
        "WITH superseded AS ("
        "  SELECT supersedes_source_id AS source_id FROM cmap.source_version "
        "  WHERE decided_at IS NOT NULL"
        "), fact AS ("
        "  SELECT r.id AS rel_id, r.rel_type, ch.source_id,"
        "    COALESCE(fm.entity_id::text, fm.normalized_name || '|' || fm.entity_type) AS from_key,"
        "    COALESCE(tm.entity_id::text, tm.normalized_name || '|' || tm.entity_type) AS to_key"
        "  FROM cmap.relation r"
        "  JOIN cmap.mention fm ON fm.id = r.from_mention_id"
        "  JOIN cmap.mention tm ON tm.id = r.to_mention_id"
        "  JOIN cmap.chunk ch ON ch.id = r.chunk_id"
        "), verdict AS ("
        "  SELECT from_key, to_key, rel_type,"
        "    CASE WHEN bool_and(source_id IN (SELECT source_id FROM superseded))"
        "      THEN 'superseded' ELSE 'current' END AS status"
        "  FROM fact GROUP BY from_key, to_key, rel_type"
        ")"
        "UPDATE cmap.relation r SET status = v.status"
        " FROM fact f JOIN verdict v USING (from_key, to_key, rel_type)"
        " WHERE f.rel_id = r.id AND r.status IS DISTINCT FROM v.status"
        " RETURNING r.status"
    ).fetchall()
    counts = {"current": 0, "superseded": 0}
    for (status,) in rows:
        counts[str(status)] += 1
    logger.info("relation status recomputed: %s", counts)
    return counts


def decide_supersession(
    conn: Any, source_id: str, supersedes_source_id: str, origin: str
) -> dict[str, Any]:
    """Record (or confirm) one supersession and refresh the computed statuses.

    ``origin`` is how it was decided: ``auto_title`` / ``auto_similarity`` /
    ``admin``. An existing decision is kept (``ON CONFLICT DO NOTHING``) so a
    later stale detection never downgrades an admin decision; confirming a
    pending proposal sets ``origin='admin'`` and stamps ``decided_at``.
    """
    if origin not in (ORIGIN_AUTO_TITLE, ORIGIN_AUTO_SIMILARITY, ORIGIN_ADMIN):
        raise ValueError(f"unknown supersession origin {origin!r}")
    conn.execute(
        "INSERT INTO cmap.source_version "
        "(source_id, supersedes_source_id, origin, decided_at) "
        "VALUES (%s, %s, %s, now()) "
        "ON CONFLICT (source_id, supersedes_source_id) DO UPDATE "
        "SET origin = EXCLUDED.origin, decided_at = now() "
        "WHERE cmap.source_version.decided_at IS NULL",
        (source_id, supersedes_source_id, origin),
    )
    row = conn.execute(
        "SELECT origin, decided_at FROM cmap.source_version "
        "WHERE source_id = %s AND supersedes_source_id = %s",
        (source_id, supersedes_source_id),
    ).fetchone()
    counts = recompute_relation_status(conn)
    _queue_project(conn)
    return {
        "source_id": source_id,
        "supersedes_source_id": supersedes_source_id,
        "origin": str(row[0]) if row is not None else origin,
        "decided_at": row[1].isoformat() if row is not None and row[1] else None,
        "status_counts": counts,
    }


def _propose(conn: Any, source_id: str, supersedes_source_id: str, origin: str) -> bool:
    """Insert one pending proposal (or a decided row) without touching decisions.

    Returns True when a new row was inserted. The reverse direction is refused:
    if the older source already supersedes this one, no contradictory row is
    added.
    """
    if source_id == supersedes_source_id:
        return False
    row = conn.execute(
        "INSERT INTO cmap.source_version "
        "(source_id, supersedes_source_id, origin, decided_at) "
        "SELECT %s, %s, %s, NULL "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM cmap.source_version "
        "  WHERE source_id = %s AND supersedes_source_id = %s"
        ") ON CONFLICT (source_id, supersedes_source_id) DO NOTHING "
        "RETURNING source_id",
        (source_id, supersedes_source_id, origin, supersedes_source_id, source_id),
    ).fetchone()
    return row is not None


def detect_title(
    conn: Any,
    source_id: str,
    title: str,
    effective_date: Any,
) -> list[dict[str, Any]]:
    """At-upload title detection: same normalised title ⇒ newer version of X.

    Auto-accepts (``origin='auto_title'``, decided now) only when the title key
    matches, has at least ``AUTO_ACCEPT_MIN_TITLE_TOKENS`` words and the new
    source's date is strictly later. Anything else lands as a pending proposal
    for the one-click confirm. Returns the rows written (decided or pending).
    """
    key = title_key(title)
    if not key:
        return []
    rows = conn.execute(
        "SELECT id::text, title, effective_date FROM cmap.source WHERE id <> %s",
        (source_id,),
    ).fetchall()
    written: list[dict[str, Any]] = []
    specific = len(key.split()) >= AUTO_ACCEPT_MIN_TITLE_TOKENS
    for other_id, other_title, other_date in rows:
        if title_key(str(other_title)) != key:
            continue
        auto = (
            specific
            and effective_date is not None
            and other_date is not None
            and effective_date > other_date
        )
        if auto:
            decision = decide_supersession(conn, source_id, other_id, ORIGIN_AUTO_TITLE)
            decision["match"] = "title"
            written.append(decision)
        elif _propose(conn, source_id, other_id, ORIGIN_AUTO_TITLE):
            written.append(
                {
                    "source_id": source_id,
                    "supersedes_source_id": other_id,
                    "origin": ORIGIN_AUTO_TITLE,
                    "decided_at": None,
                    "match": "title",
                }
            )
    return written


def detect_similarity(conn: Any, source_id: str) -> list[dict[str, Any]]:
    """First-3-chunk similarity detection (the upload's other arm, D2).

    Runs as soon as the source's chunks are embedded (the earliest moment the
    comparison exists at all). Cosine of the two mean-pooled first-chunk
    vectors >= ``SIMILARITY_THRESHOLD`` with a different content hash ⇒
    pending proposal ``origin='auto_similarity'`` (similarity alone never
    auto-accepts; that stays title+date only). Distinct rows always have
    distinct hashes (``cmap.source.sha256`` is UNIQUE).
    """
    means = _first_chunk_means(conn)
    mine = means.get(source_id)
    if mine is None:
        return []
    written: list[dict[str, Any]] = []
    for other_id, other_mean in means.items():
        if other_id == source_id:
            continue
        if _cosine(mine, other_mean) < SIMILARITY_THRESHOLD:
            continue
        if _propose(conn, source_id, other_id, ORIGIN_AUTO_SIMILARITY):
            written.append(
                {
                    "source_id": source_id,
                    "supersedes_source_id": other_id,
                    "origin": ORIGIN_AUTO_SIMILARITY,
                    "decided_at": None,
                    "match": "similarity",
                }
            )
    return written
