"""Whole-document process pass (repair plan E2).

Job ``process_pass`` turns a procedure, process description or flowchart into
an ordered, branching step list — the document-level read the paragraph-level
graph cannot make (plan key finding 3). It runs per flow-bearing source (flat
classification labelled its passages ``process``, or the vision reader
recognised a diagram) and, at write time, per Process entity whose steps come
from several sources: a second source's steps merge into the process's one
flow, and structural disagreements become D3 contradictions.

Input to the model is never the raw full text: the source's outline plus its
already-extracted Step/Decision/Role/System entities with verbatim quotes and
the relations/mentions that may ground each step (plan E2). The grounding
contract is locked: every step must cite an existing relation or mention;
steps the model cannot ground are dropped and logged — counts per source under
``cmap.source.read_notes['process_pass']['drop_reasons']`` (the plan E1
read_notes drop-reason pattern, namespaced because E1 owns ``drop_reasons``).
Diagram sources get the same pass: the rendered flowchart edges are order
evidence and arrive in the outline.

The model is resolved through ``brain.seats`` on the ``process`` seat (the
heavy/frontier seat of plan §8); model ids never appear here. Cross-source
merge is deterministic: steps are matched by their Step entity, ordering and
performer/system disagreements are recorded in ``cmap.contradiction`` (D3
shape; see sql/033), and the merged order anchors new steps between the shared
steps they sit among.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.extract.normalize import normalize_name
from brain.llm import message_content, post_chat_with_rescue
from brain.seats import stage_model

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "process_pass.md"

MAX_TOKENS = 8000
# Drop reasons counted per source in ``read_notes['process_pass']`` (plan E2,
# following the plan E1 read_notes drop-reason pattern).
DROP_REASONS: tuple[str, ...] = (
    "ungrounded_step",
    "unknown_evidence",
    "unknown_entity",
)
# Entity types the pass reads as flow material (plan E2 input contract).
INVENTORY_TYPES: tuple[str, ...] = ("Process", "Step", "Decision", "Role", "System")
PROCESS_TYPE = "Process"
FLOW_KIND_LABEL = "true_contradiction"


class ProcessPassError(RuntimeError):
    """Raised when the process pass cannot finish a source."""


# ------------------------------------------------------------------ prompts


def load_process_pass_prompt() -> str:
    """Return the runtime prompt text (plan §8: prompts live in Markdown)."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def process_pass_prompt_hash() -> str:
    """Hash of the prompt file, recorded on every source marker."""
    prompt_sha = hashlib.sha256(load_process_pass_prompt().encode("utf-8")).hexdigest()
    return hashlib.sha256(f"process_pass:{prompt_sha}".encode()).hexdigest()


def build_prompt(
    source_title: str,
    outline: str,
    entities_json: str,
    evidence_json: str,
) -> str:
    """Fill ``prompts/process_pass.md`` for one source."""
    return (
        load_process_pass_prompt()
        .replace("{{source_title}}", source_title)
        .replace("{{outline}}", outline)
        .replace("{{entities_json}}", entities_json)
        .replace("{{evidence_json}}", evidence_json)
    )


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one frontier chat-completions request in JSON mode."""
    model = stage_model(settings, "process")
    if model is None:
        raise ProcessPassError("no model on the process seat (BRAIN_FRONTIER_MODEL)")
    return post_chat_with_rescue(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
        },
        settings=settings,
        timeout=180.0,
        error_cls=ProcessPassError,
        label="frontier process pass",
    )


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse_process_json(content: str) -> dict[str, Any]:
    """Parse one model reply into the flow payload object."""
    raw = _FENCE.sub("", (content or "").strip()).strip()
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise ProcessPassError("process pass response is not JSON") from exc
    if not isinstance(payload, dict):
        raise ProcessPassError("process pass response is not a JSON object")
    return payload


# ------------------------------------------------------------------ context


@dataclass
class EntityInfo:
    """One extracted entity with its verbatim quotes from this source."""

    key: str
    entity_id: str
    entity_type: str
    name: str
    quotes: list[str] = field(default_factory=list)


@dataclass
class EvidenceItem:
    """One citeable grounding item (relation or mention) under a short key."""

    key: str
    ref_id: str
    kind: str  # 'relation' | 'mention'
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceContext:
    """Everything one pass needs: outline, entities, evidence, candidates."""

    source_id: str
    title: str
    outline: str
    entities: list[EntityInfo]
    evidence: list[EvidenceItem]
    flow_bearing: bool
    diagram: bool

    @property
    def entity_by_key(self) -> dict[str, EntityInfo]:
        return {item.key: item for item in self.entities}

    @property
    def evidence_by_key(self) -> dict[str, EvidenceItem]:
        return {item.key: item for item in self.evidence}


@dataclass
class FlowStepDraft:
    """One validated step, grounded and ready to store."""

    ordinal: int
    model_ordinal: int
    step_entity_id: str | None
    performer_entity_id: str | None
    system_entity_id: str | None
    input: str
    output: str
    decision: str
    branch_of: int | None
    typical_duration: str
    evidence_ids: list[str]


DIAGRAM_HEAD = re.compile(r"^(FLOWCHART|ORG_CHART|TABLE|FORM|OTHER)\b")


def _quote_position(text: str, quote: str) -> int:
    at = text.casefold().find((quote or "").casefold())
    return at if at >= 0 else len(text)


def _load_chunks(conn: Any, source_id: str) -> list[tuple[str, int, str, str | None, dict[str, Any]]]:
    rows = conn.execute(
        "SELECT id::text, ordinal, text, passage_kind, locator "
        "FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal",
        (source_id,),
    ).fetchall()
    return [(str(r[0]), int(r[1]), str(r[2]), r[3], r[4] or {}) for r in rows]


def _build_outline(chunks: list[tuple[str, int, str, str | None, dict[str, Any]]]) -> tuple[str, bool]:
    """One outline line per passage; a diagram chunk carries its edge list.

    The outline is structure, not raw prose: a heading line per passage. A
    rendered diagram (vision output) is included in full because its edges are
    the best evidence of step order (plan E2).
    """
    lines: list[str] = []
    diagram = False
    for _chunk_id, ordinal, text, passage_kind, locator in chunks:
        if locator.get("visual") or DIAGRAM_HEAD.match(text.strip()):
            diagram = True
            lines.append(f"[{ordinal}] (diagram)\n{text.strip()}")
            continue
        head = next((line for line in text.strip().splitlines() if line.strip()), "")
        lines.append(f"[{ordinal}] ({passage_kind or '-'}) {head[:160]}")
    return "\n".join(lines), diagram


def _load_context(conn: Any, source_id: str) -> SourceContext:
    """Build one source's outline, entity inventory and citeable evidence."""
    row = conn.execute(
        "SELECT title FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    if row is None:
        raise ProcessPassError(f"source {source_id} not found")
    title = str(row[0])
    chunks = _load_chunks(conn, source_id)
    outline, diagram = _build_outline(chunks)
    flow_bearing = diagram or any(kind == "process" for _c, _o, _t, kind, _l in chunks)
    text_by_chunk = {chunk_id: text for chunk_id, _o, text, _k, _l in chunks}
    ordinal_by_chunk = {chunk_id: ordinal for chunk_id, ordinal, _t, _k, _l in chunks}

    mentions = conn.execute(
        "SELECT m.id::text, m.entity_type, m.surface_name, m.quote, m.entity_id::text, "
        "m.chunk_id::text FROM cmap.mention m "
        "JOIN cmap.chunk c ON c.id = m.chunk_id "
        "WHERE c.source_id = %s AND m.entity_type = ANY(%s) AND m.entity_id IS NOT NULL",
        (source_id, list(INVENTORY_TYPES)),
    ).fetchall()
    groups: dict[str, dict[str, Any]] = {}
    for _mention_id, entity_type, surface, quote, entity_id, _chunk_id in mentions:
        group = groups.setdefault(
            str(entity_id),
            {"entity_type": str(entity_type), "name": str(surface), "quotes": []},
        )
        group["quotes"].append(str(quote))
    # Deterministic key order: reading order of each entity's first quote.
    first_seen: dict[str, tuple[int, int, str, str]] = {}
    for _mention_id, entity_type, surface, quote, entity_id, chunk_id in mentions:
        position = _quote_position(text_by_chunk.get(str(chunk_id), ""), str(quote))
        key_at = (ordinal_by_chunk.get(str(chunk_id), 0), position, str(entity_type), str(surface))
        current = first_seen.get(str(entity_id))
        if current is None or key_at < current:
            first_seen[str(entity_id)] = key_at
    entities: list[EntityInfo] = []
    for entity_id, _at in sorted(first_seen.items(), key=lambda item: item[1]):
        group = groups[entity_id]
        entities.append(
            EntityInfo(
                key=f"e{len(entities) + 1}",
                entity_id=entity_id,
                entity_type=str(group["entity_type"]),
                name=str(group["name"]),
                quotes=list(dict.fromkeys(group["quotes"])),
            )
        )

    evidence: list[EvidenceItem] = []
    relation_rows = conn.execute(
        "SELECT r.id::text, r.rel_type, r.description, r.quote, "
        "fm.surface_name, tm.surface_name, r.chunk_id::text "
        "FROM cmap.relation r JOIN cmap.chunk c ON c.id = r.chunk_id "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "WHERE c.source_id = %s",
        (source_id,),
    ).fetchall()
    relation_items = []
    for rel_id, rel_type, description, quote, from_name, to_name, chunk_id in relation_rows:
        relation_items.append(
            (
                ordinal_by_chunk.get(str(chunk_id), 0),
                _quote_position(text_by_chunk.get(str(chunk_id), ""), str(quote)),
                EvidenceItem(
                    key="",
                    ref_id=str(rel_id),
                    kind="relation",
                    payload={
                        "kind": "relation",
                        "type": str(rel_type),
                        "from": str(from_name),
                        "to": str(to_name),
                        "description": str(description),
                        "quote": str(quote),
                    },
                ),
            )
        )
    for _at, _pos, item in sorted(relation_items, key=lambda entry: entry[:2]):
        item.key = f"r{len(evidence) + 1}"
        evidence.append(item)

    all_mentions = conn.execute(
        "SELECT m.id::text, m.entity_type, m.surface_name, m.quote, m.chunk_id::text "
        "FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
        "WHERE c.source_id = %s",
        (source_id,),
    ).fetchall()
    mention_items = []
    for mention_id, entity_type, surface, quote, chunk_id in all_mentions:
        mention_items.append(
            (
                ordinal_by_chunk.get(str(chunk_id), 0),
                _quote_position(text_by_chunk.get(str(chunk_id), ""), str(quote)),
                EvidenceItem(
                    key="",
                    ref_id=str(mention_id),
                    kind="mention",
                    payload={
                        "kind": "mention",
                        "type": str(entity_type),
                        "name": str(surface),
                        "quote": str(quote),
                    },
                ),
            )
        )
    for _at, _pos, item in sorted(mention_items, key=lambda entry: entry[:2]):
        item.key = f"m{len(evidence) + 1}"
        evidence.append(item)

    return SourceContext(
        source_id=source_id,
        title=title,
        outline=outline,
        entities=entities,
        evidence=evidence,
        flow_bearing=flow_bearing,
        diagram=diagram,
    )


# --------------------------------------------------------------- validation


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _resolve_entity(
    raw: dict[str, Any],
    field_name: str,
    entity_by_key: dict[str, EntityInfo],
    drops: dict[str, int],
) -> str | None:
    """One entity field: an invented key is counted and never written."""
    key = _text(raw.get(field_name))
    if not key:
        return None
    info = entity_by_key.get(key)
    if info is None:
        drops["unknown_entity"] += 1
        return None
    return info.entity_id


def validate_steps(
    payload: dict[str, Any],
    entity_by_key: dict[str, EntityInfo],
    evidence_by_key: dict[str, EvidenceItem],
) -> tuple[list[FlowStepDraft], dict[str, int]]:
    """Keep only steps grounded in existing relations or mentions (plan E2).

    A step whose ``evidence`` holds no key that resolves is dropped and counted
    under ``ungrounded_step`` — never kept on trust and never silently lost.
    An entity key the model invented is counted under ``unknown_entity`` and
    the field is left empty (the invented id is never written). An unknown
    evidence key on an otherwise grounded step is counted under
    ``unknown_evidence`` and only that citation is dropped.
    """
    drops = dict.fromkeys(DROP_REASONS, 0)
    steps: list[FlowStepDraft] = []
    raw_steps = payload.get("steps") or []
    if not isinstance(raw_steps, list):
        raw_steps = []
    for position, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            drops["ungrounded_step"] += 1
            continue
        model_ordinal = raw.get("ordinal")
        try:
            model_ordinal = int(model_ordinal)
        except (TypeError, ValueError):
            model_ordinal = position + 1
        evidence_ids: list[str] = []
        for key in raw.get("evidence") or []:
            item = evidence_by_key.get(str(key).strip())
            if item is None:
                drops["unknown_evidence"] += 1
                continue
            evidence_ids.append(item.ref_id)
        if not evidence_ids:
            drops["ungrounded_step"] += 1
            continue

        branch_of = raw.get("branch_of")
        try:
            branch_of = int(branch_of) if branch_of else None
        except (TypeError, ValueError):
            branch_of = None
        steps.append(
            FlowStepDraft(
                ordinal=0,
                model_ordinal=model_ordinal,
                step_entity_id=_resolve_entity(raw, "step_key", entity_by_key, drops),
                performer_entity_id=_resolve_entity(
                    raw, "performer_key", entity_by_key, drops
                ),
                system_entity_id=_resolve_entity(raw, "system_key", entity_by_key, drops),
                input=_text(raw.get("input")),
                output=_text(raw.get("output")),
                decision=_text(raw.get("decision")),
                branch_of=branch_of,
                typical_duration=_text(raw.get("typical_duration")),
                evidence_ids=list(dict.fromkeys(evidence_ids)),
            )
        )
    steps.sort(key=lambda step: step.model_ordinal)
    by_model = {step.model_ordinal: index + 1 for index, step in enumerate(steps)}
    for index, step in enumerate(steps):
        step.ordinal = index + 1
        if step.branch_of is not None and step.branch_of > 0:
            step.branch_of = by_model.get(step.branch_of)
        else:
            step.branch_of = None
    return steps, drops


# ----------------------------------------------------------- model + merge


def _call_model(context: SourceContext, settings: Settings) -> dict[str, Any]:
    entities_json = json.dumps(
        [
            {
                "key": item.key,
                "type": item.entity_type,
                "name": item.name,
                "quotes": item.quotes,
            }
            for item in context.entities
        ],
        ensure_ascii=False,
    )
    evidence_json = json.dumps(
        [dict(item.payload, key=item.key) for item in context.evidence],
        ensure_ascii=False,
    )
    prompt = build_prompt(context.title, context.outline, entities_json, evidence_json)
    body = _post_chat([{"role": "user", "content": prompt}], settings)
    return parse_process_json(message_content(body))


def _attribute_process(
    payload: dict[str, Any], context: SourceContext, conn: Any
) -> str | None:
    """The Process entity this flow belongs to (never invented).

    1. a cited ``process_key`` that resolves to a Process entity;
    2. the source's single Process entity;
    3. a normalised-title match against the corpus's Process entities
       (canonical name, alias or mention surface; containment either way).
    """
    key = _text(payload.get("process_key"))
    info = context.entity_by_key.get(key)
    if info is not None and info.entity_type == PROCESS_TYPE:
        return info.entity_id
    processes = [item for item in context.entities if item.entity_type == PROCESS_TYPE]
    if len(processes) == 1:
        return processes[0].entity_id
    title = normalize_name(_text(payload.get("title")) or context.title, PROCESS_TYPE)
    if not title:
        return None
    rows = conn.execute(
        "SELECT DISTINCT e.id::text, e.canonical_name FROM cmap.entity e "
        "WHERE e.entity_type = %s",
        (PROCESS_TYPE,),
    ).fetchall()
    for entity_id, name in rows:
        names = [str(name)]
        names.extend(
            alias
            for (alias,) in conn.execute(
                "SELECT normalized_name FROM cmap.entity_alias WHERE entity_id = %s",
                (entity_id,),
            ).fetchall()
        )
        names.extend(
            surface
            for (surface,) in conn.execute(
                "SELECT surface_name FROM cmap.mention WHERE entity_id = %s",
                (entity_id,),
            ).fetchall()
        )
        for candidate in names:
            normalized = normalize_name(str(candidate), PROCESS_TYPE)
            if normalized and (title == normalized or title in normalized or normalized in title):
                return entity_id
    return None


@dataclass
class MergeConflict:
    """One cross-source disagreement destined for ``cmap.contradiction``."""

    relation_a: str
    relation_b: str
    summary: str


def _first_evidence(step: Any) -> str | None:
    ids = getattr(step, "evidence_ids", None)
    if ids is None:
        ids = step.get("evidence_relation_ids") or []
    return str(ids[0]) if ids else None


def _entity_names(
    conn: Any, existing: list[dict[str, Any]], new: list[FlowStepDraft]
) -> dict[str, str]:
    """Canonical names of every step entity the merge touches (summaries)."""
    ids = {item.step_entity_id for item in new if item.step_entity_id}
    ids.update(str(row.get("step_entity_id") or "") for row in existing)
    ids.discard("")
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT id::text, canonical_name FROM cmap.entity WHERE id = ANY(%s::uuid[])",
        (sorted(ids),),
    ).fetchall()
    return {str(entity_id): str(name) for entity_id, name in rows}


def _merge_steps(
    existing: list[dict[str, Any]],
    new: list[FlowStepDraft],
    names: dict[str, str] | None = None,
) -> tuple[list[FlowStepDraft], list[MergeConflict]]:
    """Merge one source's steps into the flow already on disk.

    Steps are matched by their Step entity. A different relative order of two
    shared steps, or a different performer/system for one shared step, is a
    disagreement between sources: it becomes a ``MergeConflict`` (recorded as
    a D3 contradiction) and the stored side keeps its values. Unmatched steps
    are placed after the nearest shared predecessor (before the nearest shared
    successor, else at the end), so the merged order honours both sources.
    """
    labels = names or {}

    def _label(entity_id: str | None) -> str:
        return labels.get(entity_id or "", entity_id or "")

    conflicts: list[MergeConflict] = []
    matched: dict[str, tuple[dict[str, Any], FlowStepDraft]] = {}
    for draft in new:
        if draft.step_entity_id is None:
            continue
        for row in existing:
            if str(row.get("step_entity_id") or "") == draft.step_entity_id:
                matched[draft.step_entity_id] = (row, draft)
                break
    # Order disagreements between shared steps.
    shared = [(row, draft) for row, draft in matched.values()]
    for i in range(len(shared)):
        for j in range(i + 1, len(shared)):
            row_a, draft_a = shared[i]
            row_b, draft_b = shared[j]
            existing_order = int(row_a["ordinal"]) < int(row_b["ordinal"])
            new_order = draft_a.model_ordinal < draft_b.model_ordinal
            if existing_order == new_order:
                continue
            first = (row_a, draft_a) if existing_order else (row_b, draft_b)
            second = (row_b, draft_b) if existing_order else (row_a, draft_a)
            relation_a = _first_evidence(first[0])
            relation_b = _first_evidence(second[1])
            if relation_a and relation_b:
                conflicts.append(
                    MergeConflict(
                        relation_a=relation_a,
                        relation_b=relation_b,
                        summary=(
                            "Sources disagree on step order: "
                            f"'{_label(second[1].step_entity_id)}' follows "
                            f"'{_label(first[1].step_entity_id)}' in one account "
                            "and precedes it in another."
                        ),
                    )
                )
    # Performer / system disagreements on a shared step.
    for row, draft in matched.values():
        for field_name, label in (
            ("performer_entity_id", "performer"),
            ("system_entity_id", "system"),
        ):
            stored = str(row.get(field_name) or "")
            incoming = getattr(draft, field_name) or ""
            if stored and incoming and stored != incoming:
                relation_a = _first_evidence(row)
                relation_b = _first_evidence(draft)
                if relation_a and relation_b:
                    conflicts.append(
                        MergeConflict(
                            relation_a=relation_a,
                            relation_b=relation_b,
                            summary=(
                                f"Sources disagree on the {label} of step "
                                f"'{_label(draft.step_entity_id)}'."
                            ),
                        )
                    )
    # Placement: keep the stored order, anchor new steps between shared ones.
    merged: list[FlowStepDraft] = [
        FlowStepDraft(
            ordinal=index + 1,
            model_ordinal=int(row["ordinal"]),
            step_entity_id=str(row["step_entity_id"]) if row.get("step_entity_id") else None,
            performer_entity_id=(
                str(row["performer_entity_id"]) if row.get("performer_entity_id") else None
            ),
            system_entity_id=(
                str(row["system_entity_id"]) if row.get("system_entity_id") else None
            ),
            input=str(row.get("input") or ""),
            output=str(row.get("output") or ""),
            decision=str(row.get("decision") or ""),
            branch_of=int(row["branch_of"]) if row.get("branch_of") else None,
            typical_duration=str(row.get("typical_duration") or ""),
            evidence_ids=[str(value) for value in row.get("evidence_relation_ids") or []],
        )
        for index, row in enumerate(sorted(existing, key=lambda item: int(item["ordinal"])))
    ]
    for _row, draft in matched.values():
        target = next((item for item in merged if item.step_entity_id == draft.step_entity_id), None)
        if target is not None:
            target.evidence_ids = list(dict.fromkeys([*target.evidence_ids, *draft.evidence_ids]))
    for draft in new:
        if draft.step_entity_id is not None and draft.step_entity_id in matched:
            continue
        insert_at = len(merged)
        # Anchor: nearest shared predecessor in the new source's order.
        anchor = None
        for other in new:
            if other is draft:
                break
            if other.step_entity_id is not None and other.step_entity_id in matched:
                anchor = other.step_entity_id
        if anchor is not None:
            for index, item in enumerate(merged):
                if item.step_entity_id == anchor:
                    insert_at = index + 1
                    break
        else:
            successor = None
            for other in new:
                if other is draft:
                    continue
                if other.model_ordinal > draft.model_ordinal and (
                    other.step_entity_id is not None and other.step_entity_id in matched
                ):
                    successor = other.step_entity_id
                    break
            if successor is not None:
                for index, item in enumerate(merged):
                    if item.step_entity_id == successor:
                        insert_at = index
                        break
        merged.insert(insert_at, draft)
    for index, item in enumerate(merged):
        item.ordinal = index + 1
    return merged, conflicts


def _record_conflicts(conn: Any, conflicts: list[MergeConflict]) -> int:
    """Write merge disagreements as D3 contradictions (idempotent).

    D3 seam: ``cmap.contradiction`` is D3's table (sql/032 shape, provisioned
    by sql/033 until D3 lands). ``kind`` uses D3's vocabulary: a cross-source
    flow disagreement is a true contradiction. An identical (or mirrored) pair
    is never recorded twice.
    """
    written = 0
    for conflict in conflicts:
        existing = conn.execute(
            "SELECT 1 FROM cmap.contradiction WHERE kind = %s AND "
            "((relation_a = %s AND relation_b = %s) OR (relation_a = %s AND relation_b = %s)) "
            "LIMIT 1",
            (
                FLOW_KIND_LABEL,
                conflict.relation_a,
                conflict.relation_b,
                conflict.relation_b,
                conflict.relation_a,
            ),
        ).fetchone()
        if existing is not None:
            continue
        conn.execute(
            "INSERT INTO cmap.contradiction "
            "(relation_a, relation_b, kind, summary, status) VALUES (%s, %s, %s, %s, 'open')",
            (
                conflict.relation_a,
                conflict.relation_b,
                FLOW_KIND_LABEL,
                conflict.summary,
            ),
        )
        written += 1
    return written


def _function_for(conn: Any, process_entity_id: str, source_id: str) -> str | None:
    """The strongest function of the process entity, else of the source."""
    for sql, params in (
        (
            "SELECT function_id::text FROM cmap.entity_function "
            "WHERE entity_id = %s ORDER BY weight DESC LIMIT 1",
            (process_entity_id,),
        ),
        (
            "SELECT function_id::text FROM cmap.source_function "
            "WHERE source_id = %s ORDER BY weight DESC LIMIT 1",
            (source_id,),
        ),
    ):
        row = conn.execute(sql, params).fetchone()
        if row is not None and row[0]:
            return str(row[0])
    return None


def _write_flow(
    conn: Any,
    process_entity_id: str,
    source_id: str,
    payload: dict[str, Any],
    steps: list[FlowStepDraft],
) -> tuple[int, int]:
    """Store one source's steps on the process's single flow; return counts.

    The first source creates the flow; later sources merge into it and any
    disagreement is returned as conflicts for the D3 contradiction store.
    Re-running a source replaces its own contribution first, so the write
    stays idempotent under a prompt change.
    """
    row = conn.execute(
        "SELECT id::text, title, trigger, outcome, version, sources "
        "FROM cmap.process_flow WHERE process_entity_id = %s",
        (process_entity_id,),
    ).fetchone()
    title = _text(payload.get("title")) or _text(payload.get("title_en")) or "Process flow"
    trigger = _text(payload.get("trigger"))
    outcome = _text(payload.get("outcome"))
    if row is None:
        flow_id = str(
            conn.execute(
                "INSERT INTO cmap.process_flow "
                "(process_entity_id, function_id, title, trigger, outcome, version, sources) "
                "VALUES (%s, %s, %s, %s, %s, 1, %s::uuid[]) RETURNING id",
                (
                    process_entity_id,
                    _function_for(conn, process_entity_id, source_id),
                    title,
                    trigger,
                    outcome,
                    [source_id],
                ),
            ).fetchone()[0]
        )
        for step in steps:
            _insert_step(conn, flow_id, step)
        return 1, 0

    flow_id = str(row[0])
    # Replace this source's own contribution before merging fresh steps.
    conn.execute(
        "DELETE FROM cmap.flow_step WHERE flow_id = %s AND "
        "evidence_relation_ids != '{}' AND evidence_relation_ids <@ ("
        "  SELECT COALESCE(array_agg(x.id), '{}') FROM ("
        "    SELECT r.id FROM cmap.relation r "
        "      JOIN cmap.chunk c ON c.id = r.chunk_id WHERE c.source_id = %s"
        "    UNION ALL"
        "    SELECT m.id FROM cmap.mention m "
        "      JOIN cmap.chunk c ON c.id = m.chunk_id WHERE c.source_id = %s"
        "  ) x)",
        (flow_id, source_id, source_id),
    )
    existing = [
        {
            "ordinal": int(item[0]),
            "step_entity_id": str(item[1]) if item[1] else None,
            "performer_entity_id": str(item[2]) if item[2] else None,
            "system_entity_id": str(item[3]) if item[3] else None,
            "input": str(item[4] or ""),
            "output": str(item[5] or ""),
            "decision": str(item[6] or ""),
            "branch_of": int(item[7]) if item[7] else None,
            "typical_duration": str(item[8] or ""),
            "evidence_relation_ids": [str(value) for value in item[9] or []],
        }
        for item in conn.execute(
            "SELECT ordinal, step_entity_id, performer_entity_id, system_entity_id, "
            "input, output, decision, branch_of, typical_duration, evidence_relation_ids "
            "FROM cmap.flow_step WHERE flow_id = %s ORDER BY ordinal",
            (flow_id,),
        ).fetchall()
    ]
    merged, conflicts = _merge_steps(existing, steps, _entity_names(conn, existing, steps))
    written_conflicts = _record_conflicts(conn, conflicts)
    conn.execute("DELETE FROM cmap.flow_step WHERE flow_id = %s", (flow_id,))
    for step in merged:
        _insert_step(conn, flow_id, step)
    sources = [str(value) for value in row[5] or []]
    if source_id not in sources:
        sources.append(source_id)
    conn.execute(
        "UPDATE cmap.process_flow SET title = COALESCE(NULLIF(title, ''), %s), "
        "trigger = COALESCE(NULLIF(trigger, ''), %s), "
        "outcome = COALESCE(NULLIF(outcome, ''), %s), "
        "version = version + 1, sources = %s::uuid[] WHERE id = %s",
        (title, trigger, outcome, sources, flow_id),
    )
    return 1, written_conflicts


def _insert_step(conn: Any, flow_id: str, step: FlowStepDraft) -> None:
    conn.execute(
        "INSERT INTO cmap.flow_step "
        "(flow_id, ordinal, step_entity_id, performer_entity_id, system_entity_id, "
        "input, output, decision, branch_of, typical_duration, evidence_relation_ids) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid[])",
        (
            flow_id,
            step.ordinal,
            step.step_entity_id,
            step.performer_entity_id,
            step.system_entity_id,
            step.input,
            step.output,
            step.decision,
            step.branch_of,
            step.typical_duration,
            step.evidence_ids,
        ),
    )


# -------------------------------------------------------------------- notes


def _record_process_notes(conn: Any, source_id: str, marker: dict[str, Any]) -> None:
    """Store the pass marker and its drop counts under ``read_notes``.

    The plan E1 read_notes drop-reason pattern, namespaced under
    ``process_pass``: E1 owns the top-level ``drop_reasons`` key and rewrites
    its own counters, so this pass keeps its own.
    """
    row = conn.execute(
        "SELECT read_notes FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    notes = dict(row[0] or {}) if row else {}
    notes["process_pass"] = marker
    conn.execute(
        "UPDATE cmap.source SET read_notes = %s WHERE id = %s",
        (Json(notes), source_id),
    )


def _record_usage(job_id: Any, usage: dict[str, int]) -> None:
    """Log the job's model usage into ``cmap.job.payload.usage`` (plan §11)."""
    if job_id is None or not usage:
        return
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) "
            "WHERE id = %s",
            (Json(usage), job_id),
        )
        conn.commit()


# --------------------------------------------------------------------- runs


def _pending_source_ids(conn: Any, prompt_hash: str, source_id: str | None) -> list[str]:
    """Flow-bearing sources whose marker is missing or from another prompt."""
    filter_sql = "AND s.id = %s" if source_id else ""
    params: tuple[Any, ...] = (prompt_hash, source_id) if source_id else (prompt_hash,)
    rows = conn.execute(
        "SELECT s.id::text FROM cmap.source s "
        "WHERE (s.read_notes->'process_pass'->>'prompt_hash' IS DISTINCT FROM %s) "
        "AND (EXISTS (SELECT 1 FROM cmap.chunk c WHERE c.source_id = s.id "
        "      AND (c.passage_kind = 'process' OR c.locator->>'visual' = 'true'))) "
        f"{filter_sql} ORDER BY s.created_at",
        params,
    ).fetchall()
    return [str(row[0]) for row in rows]


def run_process_pass(
    settings: Settings | None = None, source_id: str | None = None
) -> dict[str, int]:
    """Run the whole-document pass over every pending flow-bearing source."""
    cfg = settings if settings is not None else get_settings()
    if stage_model(cfg, "process") is None:
        raise ProcessPassError("no model on the process seat (BRAIN_FRONTIER_MODEL)")
    prompt_hash = process_pass_prompt_hash()
    stats = {
        "sources": 0,
        "flows": 0,
        "steps": 0,
        "dropped": 0,
        "conflicts": 0,
        "skipped": 0,
    }
    with get_pool().connection() as conn:
        targets = _pending_source_ids(conn, prompt_hash, source_id)
        conn.commit()
    for target in targets:
        with get_pool().connection() as conn:
            context = _load_context(conn, target)
            if not context.flow_bearing:
                conn.commit()
                continue
            payload = _call_model(context, cfg)
            steps, drops = validate_steps(
                payload, context.entity_by_key, context.evidence_by_key
            )
            process_entity_id = _attribute_process(payload, context, conn)
            if process_entity_id is None:
                _record_process_notes(
                    conn,
                    target,
                    {
                        "prompt_hash": prompt_hash,
                        "status": "skipped",
                        "reason": "no_process_entity",
                        "steps": 0,
                        "drop_reasons": drops,
                    },
                )
                conn.commit()
                stats["skipped"] += 1
                stats["dropped"] += sum(drops.values())
                logger.warning(
                    "process_pass source=%s skipped: no Process entity (drops=%s)",
                    target,
                    drops,
                )
                continue
            flows, conflicts = _write_flow(conn, process_entity_id, target, payload, steps)
            _record_process_notes(
                conn,
                target,
                {
                    "prompt_hash": prompt_hash,
                    "status": "done",
                    "process_entity_id": process_entity_id,
                    "steps": len(steps),
                    "drop_reasons": drops,
                },
            )
            conn.commit()
            stats["sources"] += 1
            stats["flows"] += flows
            stats["steps"] += len(steps)
            stats["conflicts"] += conflicts
            stats["dropped"] += sum(drops.values())
            logger.info(
                "process_pass source=%s process=%s steps=%d dropped=%d conflicts=%d drops=%s",
                target,
                process_entity_id,
                len(steps),
                sum(drops.values()),
                conflicts,
                drops,
            )
    return stats


def handle_process_pass(job: dict[str, Any]) -> None:
    """Job ``process_pass``: one source (``source_id``) or the whole sweep."""
    payload = job.get("payload") or {}
    source_id = str(payload.get("source_id") or "") or None
    stats = run_process_pass(source_id=source_id)
    job_id = job.get("id")
    if job_id is not None:
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET payload = jsonb_set(payload, '{stats}', %s::jsonb) WHERE id = %s",
                (Json(stats), job_id),
            )
            conn.commit()
    logger.info("process_pass job=%s stats=%s", job_id, stats)
