"""Content-keyed human corrections (repair plan G1, issue #520).

A correction is a human verdict on one piece of the map. Human corrections
always win over extraction and survive every rebuild, so a correction never
names a row id: its ``target_key`` is derived from the content of the thing it
corrects (plan Phase G; a full re-read re-creates entities and every row id
changes, see the plan's Phase A drift note).

The target_key scheme (also documented in the PR that introduced it):

* entity — ``"<normalised canonical name>|<entity_type>"``, i.e.
  ``normalize_name(canonical_name, entity_type) + "|" + entity_type`` — the
  entity's canonical key plus its type.
* relation — ``"<source-entity key>|<rel_type>|<target-entity key>"``, i.e.
  the normalised source-entity key, the relation type, and the target-entity
  key, each key in the entity form above.
* two-entity corrections (merge / split / never-merge) keep the entity form as
  ``target_key`` and name the counterpart in ``payload["pair"]`` (the other
  entity's key); the pair is matched order-independently. A ``reject`` on a
  pair is the never-merge pair: resolution must never join those two names.

Matching is key-set based: an entity carries its canonical key plus one key per
alias (``cmap.entity_alias``, which resolution fills with every mention name).
Corrections written before a rename or a description rewrite keep matching
through those keys, and applying a rename records the old key as an alias so
the mapping never drifts.

Actions: ``reject`` (never shown / never merged), ``edit`` (the payload
replaces the fact's fields), ``confirm`` (ranked first), ``merge``/``split``
(pair steering at resolution), ``rename`` (``payload["name"]`` wins), and
``reassign`` (reserved for assignment targets; not applied at G1's three
points). For each target the newest active correction of its kind is the one
in force; ``active = false`` undoes one.

Applied at three points (plan Phase G): resolution (``brain/resolve``),
projection (``brain/graph/project.py``) and answer/report assembly
(``brain/answer/answer.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from psycopg.types.json import Json

from brain.extract.normalize import normalize_name

logger = logging.getLogger(__name__)

CORRECTION_KINDS = frozenset({"entity", "relation", "flow_step", "assignment", "source"})
CORRECTION_ACTIONS = frozenset(
    {"reject", "edit", "confirm", "merge", "split", "rename", "reassign"}
)
PAIR_ACTIONS = frozenset({"merge", "split", "reject"})
VERDICT_ACTIONS = frozenset({"reject", "confirm"})
_RENAME_ALIAS_SOURCE = "correction"


# ------------------------------------------------------------------- keys


def entity_key(canonical_name: str, entity_type: str) -> str:
    """Content key of one entity: normalised canonical name plus its type."""
    return f"{normalize_name(canonical_name, entity_type)}|{entity_type}"


def mention_key(normalized_name: str, entity_type: str) -> str:
    """Content key of one mention name (``normalized_name`` is already normalised)."""
    return f"{normalized_name}|{entity_type}"


def relation_key(
    from_name: str, from_type: str, rel_type: str, to_name: str, to_type: str
) -> str:
    """Content key of one relation: source-entity key + type + target-entity key."""
    return f"{entity_key(from_name, from_type)}|{rel_type}|{entity_key(to_name, to_type)}"


# ----------------------------------------------------------------- records


@dataclass(frozen=True)
class Correction:
    """One in-force human correction."""

    id: str
    target_kind: str
    target_key: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    by: str | None = None
    at: Any = None

    @property
    def pair(self) -> str | None:
        """The counterpart entity key of a pair correction, if any."""
        value = self.payload.get("pair")
        return str(value) if isinstance(value, str) and value.strip() else None

    def newer_than(self, other: Correction) -> bool:
        return (self.at, self.id) > (other.at, other.id)


@dataclass
class Corrections:
    """Active corrections in force, newest per target and kind of verdict."""

    verdicts: dict[str, Correction] = field(default_factory=dict)  # reject/confirm
    edits: dict[str, Correction] = field(default_factory=dict)
    renames: dict[str, Correction] = field(default_factory=dict)
    pairs: dict[frozenset[str], Correction] = field(default_factory=dict)

    def verdict_for(self, keys: set[str]) -> Correction | None:
        return _best(self.verdicts, keys)

    def edit_for(self, keys: set[str]) -> Correction | None:
        return _best(self.edits, keys)

    def rename_for(self, keys: set[str]) -> Correction | None:
        return _best(self.renames, keys)

    def relation_verdict_for(
        self, from_keys: set[str], to_keys: set[str], rel_type: str
    ) -> Correction | None:
        return _best_relation(self.verdicts, from_keys, to_keys, rel_type)

    def relation_edit_for(
        self, from_keys: set[str], to_keys: set[str], rel_type: str
    ) -> Correction | None:
        return _best_relation(self.edits, from_keys, to_keys, rel_type)

    def blocks_join(
        self, name_key: str, canonical_key: str | None, entity_keys: set[str]
    ) -> bool:
        """True when a never-merge/split pair forbids joining this entity.

        Joining an entity under its own canonical name is never blocked (that
        is not a merge of two names). A pair does block every other crossing —
        including a same-name join through an alias the pair names, which is
        exactly the merge the human refused.
        """
        if canonical_key is not None and name_key == canonical_key:
            return False
        for other in entity_keys:
            if other == name_key:
                continue
            pair = self.pairs.get(frozenset({name_key, other}))
            if pair is not None and pair.action in {"reject", "split"}:
                return True
        return False

    def merge_partner(self, name_key: str) -> str | None:
        """The counterpart key of a merge pair holding ``name_key``, if any."""
        for pair, corr in self.pairs.items():
            if corr.action == "merge" and name_key in pair:
                rest = pair - {name_key}
                if rest:
                    return next(iter(rest))
        return None


def _best(table: dict[str, Correction], keys: set[str]) -> Correction | None:
    best: Correction | None = None
    for key in keys:
        corr = table.get(key)
        if corr is not None and (best is None or corr.newer_than(best)):
            best = corr
    return best


def _best_relation(
    table: dict[str, Correction],
    from_keys: set[str],
    to_keys: set[str],
    rel_type: str,
) -> Correction | None:
    best: Correction | None = None
    for from_key in from_keys:
        for to_key in to_keys:
            corr = table.get(f"{from_key}|{rel_type}|{to_key}")
            if corr is not None and (best is None or corr.newer_than(best)):
                best = corr
    return best


def _row_to_correction(row: tuple) -> Correction:
    corr_id, target_kind, target_key, action, payload, reason, by, at = row
    return Correction(
        id=str(corr_id),
        target_kind=str(target_kind),
        target_key=str(target_key),
        action=str(action),
        payload=dict(payload) if isinstance(payload, dict) else {},
        reason=str(reason) if reason is not None else None,
        by=str(by) if by is not None else None,
        at=at,
    )


def load_corrections(conn: Any) -> Corrections:
    """Every active correction, newest in force per target key and kind."""
    rows = conn.execute(
        "SELECT id, target_kind, target_key, action, payload, reason, by, at "
        "FROM cmap.correction WHERE active ORDER BY at, id"
    ).fetchall()
    out = Corrections()
    for row in rows:
        corr = _row_to_correction(row)
        if corr.pair is not None and corr.action in PAIR_ACTIONS:
            out.pairs[frozenset({corr.target_key, str(corr.pair)})] = corr
        elif corr.action in VERDICT_ACTIONS:
            _put(out.verdicts, corr)
        elif corr.action == "edit":
            _put(out.edits, corr)
        elif corr.action == "rename":
            _put(out.renames, corr)
    return out


def _put(table: dict[str, Correction], corr: Correction) -> None:
    existing = table.get(corr.target_key)
    if existing is None or corr.newer_than(existing):
        table[corr.target_key] = corr


# --------------------------------------------------------------- key sets


def entity_key_sets(conn: Any, entity_ids: list[str] | None = None) -> dict[str, set[str]]:
    """Content keys per entity: its canonical key plus one key per alias.

    With ``entity_ids`` only those entities are read; with ``None`` the whole
    corpus. A mention name and an entity's pre-rename canonical name land in
    ``cmap.entity_alias``, so corrections written against either keep matching.
    """
    where = "WHERE e.id = ANY(%s::uuid[])" if entity_ids is not None else ""
    params: tuple[Any, ...] = (sorted(entity_ids),) if entity_ids is not None else ()
    keys: dict[str, set[str]] = {}
    for entity_id, name, etype in conn.execute(
        "SELECT e.id::text, e.canonical_name, e.entity_type FROM cmap.entity e " + where,
        params,
    ).fetchall():
        keys.setdefault(str(entity_id), set()).add(entity_key(str(name), str(etype)))
    alias_where = "WHERE a.entity_id = ANY(%s::uuid[])" if entity_ids is not None else ""
    for entity_id, norm, etype in conn.execute(
        "SELECT a.entity_id::text, a.normalized_name, a.entity_type "
        "FROM cmap.entity_alias a " + alias_where,
        params,
    ).fetchall():
        keys.setdefault(str(entity_id), set()).add(mention_key(str(norm), str(etype)))
    return keys


# ----------------------------------------------------------------- writer


def record_correction(
    conn: Any,
    *,
    target_kind: str,
    target_key: str,
    action: str,
    payload: dict[str, Any] | None = None,
    reason: str | None = None,
    by: str | None = None,
) -> dict[str, Any]:
    """Insert one correction row; the caller commits.

    ``merge`` and ``split`` corrections must carry ``payload["pair"]``, the
    counterpart entity's content key; a ``reject`` that carries one is the
    never-merge pair, a ``reject`` without one rejects a single target.
    """
    if target_kind not in CORRECTION_KINDS:
        raise ValueError(f"unknown target_kind {target_kind!r}")
    if action not in CORRECTION_ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    body = dict(payload or {})
    # merge and split are inherently two-entity; a reject carrying a pair is
    # the never-merge pair, while a plain reject names one target.
    if action in {"merge", "split"}:
        pair = body.get("pair")
        if not isinstance(pair, str) or not pair.strip():
            raise ValueError(f"action {action!r} needs payload['pair']")
    if action == "rename" and not str(body.get("name") or "").strip():
        raise ValueError("action 'rename' needs payload['name']")
    row = conn.execute(
        "INSERT INTO cmap.correction "
        "(target_kind, target_key, action, payload, reason, by) "
        "VALUES (%s, %s, %s, %s, %s, %s) "
        "RETURNING id, target_kind, target_key, action, payload, reason, by, at",
        (target_kind, target_key, action, Json(body), reason, by),
    ).fetchone()
    return {
        "id": str(row[0]),
        "target_kind": str(row[1]),
        "target_key": str(row[2]),
        "action": str(row[3]),
        "payload": dict(row[4]) if isinstance(row[4], dict) else {},
        "reason": str(row[5]) if row[5] is not None else None,
        "by": str(row[6]) if row[6] is not None else None,
        "at": row[7].isoformat() if row[7] is not None else None,
    }


# ------------------------------------------------------------------- apply


EDGE_EDIT_FIELDS = (
    "rel_type",
    "weight",
    "descriptions",
    "stances",
    "confidence_max",
    "source_refs",
)


def apply_edge_edit(edge: dict[str, Any], payload: dict[str, Any]) -> None:
    """Replace an edge's fields from an ``edit`` correction payload.

    Only the projected edge fields are replaceable; anything else in the
    payload is ignored (the correction still stands on the fields it names).
    """
    for key in EDGE_EDIT_FIELDS:
        if key in payload:
            edge[key] = payload[key]


def apply_renames(conn: Any, corrections: Corrections) -> int:
    """Force ``payload['name']`` onto every entity a rename correction names.

    The pre-rename key is kept as an alias (source ``correction``) so relation
    and pair corrections written against the old name keep matching after the
    rename. Returns the number of entities renamed.
    """
    if not corrections.renames:
        return 0
    keys = entity_key_sets(conn)
    renamed = 0
    for entity_id, entity_keys in keys.items():
        corr = corrections.rename_for(entity_keys)
        if corr is None:
            continue
        new_name = str(corr.payload.get("name") or "").strip()
        if not new_name:
            continue
        row = conn.execute(
            "SELECT canonical_name, entity_type FROM cmap.entity WHERE id = %s",
            (entity_id,),
        ).fetchone()
        if row is None:
            continue
        old_name, etype = str(row[0]), str(row[1])
        if old_name == new_name:
            continue
        old_key_norm = normalize_name(old_name, etype)
        conn.execute(
            "UPDATE cmap.entity SET canonical_name = %s, updated_at = now() WHERE id = %s",
            (new_name, entity_id),
        )
        if old_key_norm:
            conn.execute(
                "INSERT INTO cmap.entity_alias "
                "(entity_id, entity_type, normalized_name, lang, source) "
                "VALUES (%s, %s, %s, 'en', %s) "
                "ON CONFLICT (entity_type, normalized_name) DO NOTHING",
                (entity_id, etype, old_key_norm, _RENAME_ALIAS_SOURCE),
            )
        renamed += 1
    return renamed


# --------------------------------------------------------------- migration


def migrate_review_flags(conn: Any) -> dict[str, int]:
    """Copy the pre-G1 review flags into ``cmap.correction`` (idempotent).

    A flag marked an item as wrong, so a flag naming a concrete, still-present
    target becomes a ``reject`` correction (reason = the note, ``by`` = the
    flagger, ``at`` = when it was flagged) and gains that action on its row.
    Pure notes — community flags, which have no correction target kind, and
    flags whose entity rows are gone so no content key can be built — are
    skipped and counted. Only rows without an action are processed, so running
    again after a restart or a resolve does nothing.
    """
    counts = {"migrated": 0, "skipped_note": 0, "skipped_target_gone": 0}
    rows = conn.execute(
        "SELECT id, item_type, item_id, note, created_by, created_at "
        "FROM cmap.review_flag WHERE action IS NULL"
    ).fetchall()
    for flag_id, item_type, item_id, note, created_by, created_at in rows:
        target = flag_target(conn, str(item_type), str(item_id))
        if target is None:
            if str(item_type) == "community":
                counts["skipped_note"] += 1
            else:
                counts["skipped_target_gone"] += 1
            continue
        target_kind, target_key = target
        conn.execute(
            "INSERT INTO cmap.correction "
            "(target_kind, target_key, action, payload, reason, by, at) "
            "VALUES (%s, %s, 'reject', '{}'::jsonb, %s, %s, %s)",
            (
                target_kind,
                target_key,
                str(note) if note is not None else None,
                str(created_by) if created_by is not None else None,
                created_at,
            ),
        )
        conn.execute(
            "UPDATE cmap.review_flag SET action = 'reject' WHERE id = %s",
            (str(flag_id),),
        )
        counts["migrated"] += 1
    conn.commit()
    if rows:
        logger.info("review_flag→correction migration: %s", counts)
    return counts


def flag_target(conn: Any, item_type: str, item_id: str) -> tuple[str, str] | None:
    """The correction target of one review-flag row, or None when it names none.

    Community flags have no correction target kind and stale flags whose entity
    rows are gone yield no content key; both are notes, not corrections.
    """
    if item_type == "entity":
        key = _entity_key_of(conn, item_id)
        return ("entity", key) if key is not None else None
    if item_type == "relation":
        parts = item_id.split(":")
        if len(parts) != 3:
            return None
        from_key = _entity_key_of(conn, parts[0])
        to_key = _entity_key_of(conn, parts[1])
        if from_key is None or to_key is None:
            return None
        return ("relation", f"{from_key}|{parts[2].strip()}|{to_key}")
    return None


def _entity_key_of(conn: Any, entity_id: str) -> str | None:
    row = conn.execute(
        "SELECT canonical_name, entity_type FROM cmap.entity WHERE id = %s",
        (entity_id,),
    ).fetchone()
    if row is None:
        return None
    return entity_key(str(row[0]), str(row[1]))
