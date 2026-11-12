"""Whole-document process pass (repair plan E2).

The gate runs the frozen fixture corpus through the real pipeline (flat →
relations → resolve, every model call replayed), then the process pass on
recorded-shaped responses. No test calls a real model. The grounding contract
is what these tests guard: every stored step cites an existing relation or
mention, an ungrounded step is dropped and logged, cross-source merge records
its disagreements as D3 contradictions, and a flowchart image yields a flow
whose order follows the diagram.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from conftest import (
    fake_embeddings,
    fake_relations,
    fake_scaledown,
    fake_vision,
)
from psycopg.types.json import Json
from test_flat import PDF_FIXTURE, TRANSCRIPT_FIXTURE, _seed_fixture
from test_resolve import _fake as _fake_resolve

from brain.config import get_settings
from brain.extract.flat import handle_classify_extract
from brain.extract.normalize import normalize_name
from brain.extract.relations import handle_relations
from brain.process_pass import handle_process_pass
from brain.resolve.resolve import run_resolve

FLOWCHART_FIXTURE = "licensing-approval-flowchart.png"

# The procedure fixture's steps, in execution order (test_flat).
PROCEDURE_ORDER = [
    "Design submits the concept package",
    "The Licensing Manager reviews the package",
    "The Licensing Manager submits the package to the licensor",
    "the Licensing Manager records the sign-off",
    "Design releases the artwork to QA and to the buyer",
    "The Buyer may create the purchase order",
]

# The flowchart fixture's diagram order (vision output): the decision at
# "Licensor approval?" branches to the resubmit loop (plan E2).
FLOWCHART_ORDER = [
    "Submit concept package",
    "Compliance review",
    "Licensor approval?",
    "Record sign-off (Jessica)",
    "Create PO",
]
FLOWCHART_BRANCH = "Fix package and resubmit"
FLOWCHART_DECISION_ORDINAL = 3


class FakeProcessPass:
    """Replay builder-composed process-pass responses over the prompt seam.

    The builder sees the ENTITIES and EVIDENCE inventories the prompt carried
    (keyed ``e…`` / ``r…`` / ``m…``) and returns the flow payload, so a
    response can only cite keys that really exist — or prove they get dropped.
    """

    def __init__(self, builder: Callable[[list[dict], list[dict], str], dict]) -> None:
        self.builder = builder
        self.prompts: list[str] = []

    @staticmethod
    def _inventory(prompt: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        entities: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for chunk in prompt.split("<<<\n")[1:]:
            body = chunk.split("\n>>>", 1)[0]
            try:
                parsed = json.loads(body)
            except ValueError:
                continue
            if not isinstance(parsed, list):
                continue
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "")
                if key.startswith("e"):
                    entities.append(item)
                elif key:
                    evidence.append(item)
        return entities, evidence

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        self.prompts.append(prompt)
        entities, evidence = self._inventory(prompt)
        payload = self.builder(entities, evidence, prompt)
        return {
            "choices": [{"message": {"content": json.dumps(payload)}}],
            "usage": {"total_tokens": 20},
        }


def fake_process_pass(
    monkeypatch: pytest.MonkeyPatch,
    builder: Callable[[list[dict], list[dict], str], dict],
) -> FakeProcessPass:
    """Replay builder-composed responses through the process-pass HTTP seam."""
    from brain import process_pass as process_pass_mod

    fake = FakeProcessPass(builder)
    monkeypatch.setattr(process_pass_mod, "_post_chat", fake)
    return fake


def _norm(name: str, entity_type: str = "Step") -> str:
    return normalize_name(str(name), entity_type)


def _pick(entities: list[dict[str, Any]], expected: str) -> dict[str, Any]:
    """The inventory entity whose name matches ``expected`` after normalisation.

    Exact matches win over containment, so a Role "Licensing Manager" never
    shadows the Step "The Licensing Manager reviews the package".
    """
    wanted = _norm(expected)
    for item in entities:
        if _norm(str(item.get("name") or "")) == wanted:
            return item
    for item in entities:
        name = _norm(str(item.get("name") or ""))
        if wanted in name or name in wanted:
            return item
    raise AssertionError(f"no inventory entity matches {expected!r} in {entities!r}")


def _grounded_step(
    entity: dict[str, Any],
    evidence: list[dict[str, Any]],
    ordinal: int,
    **extra: Any,
) -> dict[str, Any]:
    step = {
        "ordinal": ordinal,
        "step_key": entity["key"],
        "performer_key": "",
        "system_key": "",
        "input": "",
        "output": "",
        "decision": "",
        "branch_of": 0,
        "typical_duration": "",
        "evidence": [evidence[0]["key"]] if evidence else [],
    }
    step.update(extra)
    return step


# ---------------------------------------------------------------- pipeline


def _fixture_pipeline(
    monkeypatch: pytest.MonkeyPatch, db: Any, fixtures: tuple[str, ...]
) -> dict[str, str]:
    """Flat + relations + resolve over the frozen fixtures, model calls replayed."""
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    fake_scaledown(monkeypatch, "transcript.json", "pdf.json", "flowchart.json")
    fake_relations(monkeypatch)
    fake_vision(monkeypatch, "vision_flowchart.json")
    available = {
        "transcript": (TRANSCRIPT_FIXTURE, "transcript"),
        "pdf": (PDF_FIXTURE, "pdf"),
        "flowchart": (FLOWCHART_FIXTURE, "image"),
    }
    ids = {
        name: _seed_fixture(db, available[name][0], available[name][1])
        for name in fixtures
    }
    for source_id in ids.values():
        handle_classify_extract({"payload": {"source_id": source_id}})
        handle_relations({"payload": {"source_id": source_id}})
    _fake_resolve(monkeypatch)
    run_resolve()
    return ids


def _flow_rows(db: Any) -> list[tuple[int, str | None, str | None]]:
    rows = db.execute(
        "SELECT fs.ordinal, e.canonical_name, fs.branch_of "
        "FROM cmap.flow_step fs "
        "JOIN cmap.process_flow pf ON pf.id = fs.flow_id "
        "LEFT JOIN cmap.entity e ON e.id = fs.step_entity_id "
        "ORDER BY fs.ordinal",
        (),
    ).fetchall()
    return [(int(ordinal), name, branch_of) for ordinal, name, branch_of in rows]


def _assert_evidence_grounded(db: Any) -> None:
    """Every step's citations resolve to a real relation or mention (locked)."""
    rows = db.execute("SELECT evidence_relation_ids FROM cmap.flow_step", ()).fetchall()
    assert rows, "the flow has steps"
    for (evidence_ids,) in rows:
        assert evidence_ids, "every step cites evidence"
        for ref_id in evidence_ids:
            found = db.execute(
                "SELECT 1 FROM cmap.relation WHERE id = %s "
                "UNION ALL SELECT 1 FROM cmap.mention WHERE id = %s",
                (str(ref_id), str(ref_id)),
            ).fetchone()
            assert found is not None, f"evidence {ref_id} is not a relation or mention"


# ------------------------------------------------------------- direct seeds


def _seed_flow_source(
    db: Any,
    tag: str,
    process_name: str,
    step_names: list[str],
    entity_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Direct-seed one flow-bearing source with entities and one relation.

    ``entity_ids`` reuses existing entities (the cross-source case: the same
    Process and Step entities mentioned in several sources). Returns the
    source id, the entity id per name and the seeded relation ids.
    """
    text = f"{process_name} procedure. " + ". ".join(step_names) + "."
    row = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes) "
        "VALUES ('text', %s, %s, %s, %s) RETURNING id",
        (f"flows {tag}", f"test/flows-{tag}.txt", f"flows-{tag}-{len(step_names)}", len(text)),
    ).fetchone()
    source_id = str(row[0])
    chunk_id = str(
        db.execute(
            "INSERT INTO cmap.chunk "
            "(source_id, ordinal, locator, text, token_count, passage_kind) "
            "VALUES (%s, 0, %s, %s, %s, 'process') RETURNING id",
            (source_id, Json({"page": 1}), text, 10),
        ).fetchone()[0]
    )
    ids = dict(entity_ids or {})
    names = [process_name, *step_names]
    for name in names:
        if name in ids:
            continue
        entity_type = "Process" if name == process_name else "Step"
        ids[name] = str(
            db.execute(
                "INSERT INTO cmap.entity (entity_type, canonical_name) "
                "VALUES (%s, %s) RETURNING id",
                (entity_type, name),
            ).fetchone()[0]
        )
    mention_ids: dict[str, str] = {}
    for name in names:
        entity_type = "Process" if name == process_name else "Step"
        mention_ids[name] = str(
            db.execute(
                "INSERT INTO cmap.mention "
                "(chunk_id, entity_type, surface_name, normalized_name, quote, entity_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    chunk_id,
                    entity_type,
                    name,
                    _norm(name, entity_type),
                    text,
                    ids[name],
                ),
            ).fetchone()[0]
        )
    relation_ids = []
    if len(step_names) >= 2:
        relation_ids.append(
            str(
                db.execute(
                    "INSERT INTO cmap.relation "
                    "(chunk_id, from_mention_id, to_mention_id, rel_type, description, "
                    "stance, confidence, quote) "
                    "VALUES (%s, %s, %s, 'PRECEDES', %s, 'policy', 0.9, %s) RETURNING id",
                    (
                        chunk_id,
                        mention_ids[step_names[0]],
                        mention_ids[step_names[1]],
                        f"{step_names[0]} comes before {step_names[1]} in {tag}.",
                        text,
                    ),
                ).fetchone()[0]
            )
        )
    else:
        relation_ids.append(
            str(
                db.execute(
                    "INSERT INTO cmap.relation "
                    "(chunk_id, from_mention_id, to_mention_id, rel_type, description, "
                    "stance, confidence, quote) "
                    "VALUES (%s, %s, %s, 'PART_OF', %s, 'policy', 0.9, %s) RETURNING id",
                    (
                        chunk_id,
                        mention_ids[step_names[0]],
                        mention_ids[process_name],
                        f"{step_names[0]} is part of {process_name}.",
                        text,
                    ),
                ).fetchone()[0]
            )
        )
    db.commit()
    return {"source_id": source_id, "entity_ids": ids, "relation_ids": relation_ids}


# ------------------------------------------------------------- gate tests


def test_fixture_approval_flow_ordered(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Gate: the fixture procedure becomes one ordered, fully grounded flow.

    The model reply lists the steps with explicit ordinals but shuffled; the
    stored order must follow the ordinals — Design submits … → Buyer creates
    the purchase order — and every step must cite a real relation or mention.
    """
    ids = _fixture_pipeline(monkeypatch, db, ("transcript", "pdf", "flowchart"))

    def builder(
        entities: list[dict], evidence: list[dict], prompt: str
    ) -> dict[str, Any]:
        del prompt
        steps = [
            _grounded_step(_pick(entities, expected), evidence, ordinal)
            for ordinal, expected in enumerate(PROCEDURE_ORDER, start=1)
        ]
        return {
            "title": "Licensing approval flow",
            "trigger": "Design submits a concept package",
            "outcome": "The Buyer creates the purchase order",
            "process_key": "",
            "steps": list(reversed(steps)),
        }

    fake = fake_process_pass(monkeypatch, builder)
    handle_process_pass({"payload": {"source_id": ids["pdf"]}})
    assert len(fake.prompts) == 1

    rows = _flow_rows(db)
    stored = [_norm(str(name)) for _ordinal, name, _branch in rows]
    assert stored == [_norm(name) for name in PROCEDURE_ORDER]
    assert [ordinal for ordinal, _name, _branch in rows] == [1, 2, 3, 4, 5, 6]
    _assert_evidence_grounded(db)
    flow = db.execute(
        "SELECT title, trigger, outcome, sources FROM cmap.process_flow", ()
    ).fetchone()
    assert flow is not None
    assert str(flow[0]) == "Licensing approval flow"
    assert str(flow[1]) == "Design submits a concept package"
    assert len(flow[3]) == 1 and str(flow[3][0]) == ids["pdf"]


def test_ungrounded_step_dropped(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    """Gate: a step with no citable evidence is dropped and logged — never kept."""
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    seeded = _seed_flow_source(db, "ungrounded", "Artwork approval", ["Review artwork"])

    def builder(
        entities: list[dict], evidence: list[dict], prompt: str
    ) -> dict[str, Any]:
        del prompt
        process_key = _pick(entities, "Artwork approval")["key"]
        step = _pick(entities, "Review artwork")
        return {
            "title": "Artwork approval",
            "trigger": "artwork arrives",
            "outcome": "artwork approved",
            "process_key": process_key,
            "steps": [
                _grounded_step(step, evidence, 1),
                dict(_grounded_step(step, evidence, 2), evidence=["r404", "m404"]),
            ],
        }

    fake = fake_process_pass(monkeypatch, builder)
    handle_process_pass({"payload": {"source_id": seeded["source_id"]}})
    assert len(fake.prompts) == 1

    rows = _flow_rows(db)
    assert len(rows) == 1, "the ungrounded step is dropped, the grounded one kept"
    _assert_evidence_grounded(db)
    notes = db.execute(
        "SELECT read_notes FROM cmap.source WHERE id = %s", (seeded["source_id"],)
    ).fetchone()[0]
    assert notes["process_pass"]["drop_reasons"] == {
        "ungrounded_step": 1,
        "unknown_evidence": 2,
        "unknown_entity": 0,
    }
    assert notes["process_pass"]["steps"] == 1

    # Idempotent: the same prompt never runs the source again.
    handle_process_pass({"payload": {"source_id": seeded["source_id"]}})
    assert len(fake.prompts) == 1
    assert len(_flow_rows(db)) == 1


def test_two_sources_merged_with_conflict_recorded(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Gate: two sources' flows for one process merge; order clash → D3 contradiction."""
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    process_name = "Sample review"
    step_names = ["Approve artwork", "Release artwork"]
    first = _seed_flow_source(db, "merge-a", process_name, step_names)
    second = _seed_flow_source(
        db,
        "merge-b",
        process_name,
        step_names,
        entity_ids=first["entity_ids"],
    )

    def builder_for(order: list[str]) -> Callable[[list[dict], list[dict], str], dict]:
        def builder(
            entities: list[dict], evidence: list[dict], prompt: str
        ) -> dict[str, Any]:
            del prompt
            return {
                "title": process_name,
                "trigger": "a sample arrives",
                "outcome": "the sample is released",
                "process_key": _pick(entities, process_name)["key"],
                "steps": [
                    _grounded_step(_pick(entities, name), evidence, ordinal)
                    for ordinal, name in enumerate(order, start=1)
                ],
            }

        return builder

    fake_process_pass(monkeypatch, builder_for(["Approve artwork", "Release artwork"]))
    handle_process_pass({"payload": {"source_id": first["source_id"]}})
    fake_process_pass(monkeypatch, builder_for(["Release artwork", "Approve artwork"]))
    handle_process_pass({"payload": {"source_id": second["source_id"]}})

    flow = db.execute(
        "SELECT id, sources, version FROM cmap.process_flow", ()
    ).fetchone()
    assert flow is not None, "both sources land on one flow"
    assert sorted(str(value) for value in flow[1]) == sorted(
        [first["source_id"], second["source_id"]]
    )
    assert int(flow[2]) >= 2, "the merge bumps the flow version"

    rows = _flow_rows(db)
    assert [_norm(str(name)) for _o, name, _b in rows] == [
        _norm(name) for name in step_names
    ], "the merged order keeps the stored account; the clash is recorded"

    conflicts = db.execute(
        "SELECT kind, summary, status FROM cmap.contradiction", ()
    ).fetchall()
    assert conflicts, "the order disagreement is recorded as a D3 contradiction"
    kind, summary, status = conflicts[0]
    assert str(kind) == "true_contradiction"
    assert str(status) == "open"
    assert "step order" in str(summary)
    assert "Approve artwork" in str(summary) or "Release artwork" in str(summary)


def test_flowchart_image_yields_flow(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    """Gate: a flowchart image source yields a flow ordered like the diagram."""
    ids = _fixture_pipeline(monkeypatch, db, ("flowchart",))

    def builder(
        entities: list[dict], evidence: list[dict], prompt: str
    ) -> dict[str, Any]:
        del prompt
        steps = [
            _grounded_step(
                _pick(entities, expected),
                evidence,
                ordinal,
                **(
                    {"decision": "Does the licensor approve the package?"}
                    if expected == FLOWCHART_ORDER[2]
                    else {}
                ),
            )
            for ordinal, expected in enumerate(FLOWCHART_ORDER, start=1)
        ]
        branch = _grounded_step(
            _pick(entities, FLOWCHART_BRANCH),
            evidence,
            len(steps) + 1,
            branch_of=FLOWCHART_DECISION_ORDINAL,
            decision="",
        )
        return {
            "title": "Licensing approval flow",
            "trigger": "a concept package is submitted",
            "outcome": "a purchase order is created",
            "process_key": _pick(entities, "Licensing approval flow")["key"],
            "steps": steps + [branch],
        }

    fake = fake_process_pass(monkeypatch, builder)
    handle_process_pass({"payload": {"source_id": ids["flowchart"]}})
    assert len(fake.prompts) == 1

    rows = _flow_rows(db)
    assert [_norm(str(name)) for _o, name, _b in rows] == [
        _norm(name) for name in [*FLOWCHART_ORDER, FLOWCHART_BRANCH]
    ], "the flow follows the diagram's edge order, branch last"
    assert rows[-1][2] == FLOWCHART_DECISION_ORDINAL, (
        "the resubmit loop is a branch of the decision step"
    )
    _assert_evidence_grounded(db)
    marker = db.execute(
        "SELECT read_notes FROM cmap.source WHERE id = %s", (ids["flowchart"],)
    ).fetchone()[0]["process_pass"]
    assert marker["status"] == "done"
    assert marker["drop_reasons"]["ungrounded_step"] == 0
