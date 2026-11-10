"""Translation sidecar for stored map prose (plan step 1.3).

English canonical text stays in the existing columns; this table carries the
companion translations so zh-CN readers see Chinese without a per-view model
call. Same access pattern as the neighboring cmap tables (brain service role).
"""

from __future__ import annotations

from brain.db import get_pool

VALID_KINDS = ("entity", "community", "edge")
VALID_LANGS = ("en", "zh-CN")


def upsert_translation(kind: str, ref_id: str, field: str, lang: str, text: str) -> None:
    """Store (or overwrite) one translated field for one artifact."""
    body = text.strip()
    if not body:
        return
    if kind not in VALID_KINDS or lang not in VALID_LANGS:
        raise ValueError(f"invalid translation key: kind={kind!r} lang={lang!r}")
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO cmap.translation (kind, ref_id, field, lang, text) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (kind, ref_id, field, lang) DO UPDATE SET text = EXCLUDED.text",
            (kind, ref_id, field, lang, body),
        )
        conn.commit()


def translations_for(kind: str, ref_id: str) -> dict[str, dict[str, str]]:
    """Return ``{lang: {field: text}}`` for one artifact."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT lang, field, text FROM cmap.translation "
            "WHERE kind = %s AND ref_id = %s",
            (kind, ref_id),
        ).fetchall()
    out: dict[str, dict[str, str]] = {}
    for lang, field, text in rows:
        out.setdefault(str(lang), {})[str(field)] = str(text)
    return out
