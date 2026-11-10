"""Translation sidecar for stored map prose (plan step 1.3).

English canonical text stays in the existing columns; this table carries the
companion translations so zh-CN readers see Chinese without a per-view model
call. Same access pattern as the neighboring cmap tables (brain service role).
"""

from __future__ import annotations

from contextlib import nullcontext

import psycopg

from brain.db import get_pool

VALID_KINDS = ("entity", "community", "edge", "question")
VALID_LANGS = ("en", "zh-CN")


def upsert_translation(
    kind: str, ref_id: str, field: str, lang: str, text: str,
    *, conn: psycopg.Connection | None = None,
) -> None:
    """Store one translated field. Question versions are immutable."""
    body = text.strip()
    if not body:
        return
    if kind not in VALID_KINDS or lang not in VALID_LANGS:
        raise ValueError(f"invalid translation key: kind={kind!r} lang={lang!r}")
    conflict = (
        "DO NOTHING" if kind == "question" else "DO UPDATE SET text = EXCLUDED.text"
    )
    with (nullcontext(conn) if conn is not None else get_pool().connection()) as db:
        db.execute(
            "INSERT INTO cmap.translation (kind, ref_id, field, lang, text) "
            "VALUES (%s, %s, %s, %s, %s) "
            f"ON CONFLICT (kind, ref_id, field, lang) {conflict}",
            (kind, ref_id, field, lang, body),
        )
        if conn is None:
            db.commit()


def translations_for(
    kind: str, ref_id: str, *, conn: psycopg.Connection | None = None,
) -> dict[str, dict[str, str]]:
    """Return ``{lang: {field: text}}`` for one artifact."""
    with (nullcontext(conn) if conn is not None else get_pool().connection()) as db:
        rows = db.execute(
            "SELECT lang, field, text FROM cmap.translation "
            "WHERE kind = %s AND ref_id = %s",
            (kind, ref_id),
        ).fetchall()
    out: dict[str, dict[str, str]] = {}
    for lang, field, text in rows:
        out.setdefault(str(lang), {})[str(field)] = str(text)
    return out
