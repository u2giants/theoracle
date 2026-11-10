"""Translation sidecar for stored map prose (plan step 1.3).

English canonical text stays in the existing columns; this table carries the
companion translations so zh-CN readers see Chinese without a per-view model
call. Same access pattern as the neighboring cmap tables (brain service role).
"""

from __future__ import annotations

from brain.db import get_pool
from brain.lang import detect_language

VALID_KINDS = ("entity", "community", "edge")
VALID_LANGS = ("en", "zh-CN")


def english_text(source: str, companion: str = "") -> str:
    """Require an English canonical rather than mislabel source-language prose."""
    body = (companion or source).strip()
    if body and detect_language(body) != "en":
        raise ValueError("English companion required for non-English prose")
    return body


def upsert_translation(
    kind: str, ref_id: str, field: str, lang: str, text: str, *, conn=None
) -> None:
    """Replace a field, deleting an empty value, in the caller's transaction."""
    if kind not in VALID_KINDS or lang not in VALID_LANGS:
        raise ValueError(f"invalid translation key: kind={kind!r} lang={lang!r}")
    if conn is None:
        with get_pool().connection() as owned:
            upsert_translation(kind, ref_id, field, lang, text, conn=owned)
            owned.commit()
        return
    body = text.strip()
    if not body:
        conn.execute(
            "DELETE FROM cmap.translation WHERE kind = %s AND ref_id = %s "
            "AND field = %s AND lang = %s", (kind, ref_id, field, lang),
        )
        return
    conn.execute(
        "INSERT INTO cmap.translation (kind, ref_id, field, lang, text) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (kind, ref_id, field, lang) DO UPDATE SET text = EXCLUDED.text",
        (kind, ref_id, field, lang, body),
    )


def cleanup_translations(conn) -> None:
    """Remove sidecars whose artifacts were deleted, including legacy orphans."""
    for kind in ("entity", "community"):
        conn.execute(
            f"DELETE FROM cmap.translation t WHERE kind = %s AND NOT EXISTS "
            f"(SELECT 1 FROM cmap.{kind} a WHERE a.id = t.ref_id)", (kind,),
        )


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
