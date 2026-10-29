"""Entity resolution (plan step 6).

The fixture test runs the real flat stage on the transcript fixture (recorded
ScaleDown), adds a second source standing in for the flowchart and the
procedure with the other spellings the step names, then resolves. Embeddings
are set per test so each cosine is known; the frontier judge and describer are
replayed fakes. No test calls a real model.
"""

from __future__ import annotations

import json
import math
import random
from typing import Any

import pytest
from conftest import fake_embeddings, fake_scaledown
from test_flat import TRANSCRIPT_FIXTURE, _seed_fixture, _seed_text

from brain.config import get_settings
from brain.embed import vector_literal
from brain.extract.flat import handle_classify_extract
from brain.extract.normalize import normalize_name
from brain.resolve import resolve as resolve_mod
from brain.resolve.resolve import handle_resolve, run_resolve


@pytest.fixture()
def frontier_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _dims() -> int:
    return get_settings().brain_embed_dims


def _unit(seed: str) -> list[float]:
    rng = random.Random(seed)
    vector = [rng.gauss(0.0, 1.0) for _ in range(_dims())]
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


def _at_cosine(base: list[float], cosine: float, seed: str) -> list[float]:
    """A unit vector with exactly ``cosine`` to unit vector ``base``."""
    other = _unit(seed)
    dot = sum(a * b for a, b in zip(base, other, strict=True))
    ortho = [o - dot * b for o, b in zip(other, base, strict=True)]
    norm = math.sqrt(sum(value * value for value in ortho))
    sine = math.sqrt(1.0 - cosine * cosine)
    return [cosine * b + sine * o / norm for b, o in zip(base, ortho, strict=True)]


def _mention(
    db: Any,
    source_id: str,
    entity_type: str,
    surface: str,
    vector: list[float] | None,
    quote: str | None = None,
) -> str:
    chunk_id = db.execute(
        "SELECT id FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal LIMIT 1",
        (source_id,),
    ).fetchone()[0]
    row = db.execute(
        "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, normalized_name, "
        "quote, embedding) VALUES (%s, %s, %s, %s, %s, %s::vector) RETURNING id",
        (
            chunk_id,
            entity_type,
            surface,
            normalize_name(surface, entity_type),
            quote or f"{surface} was mentioned.",
            vector_literal(vector) if vector is not None else None,
        ),
    ).fetchone()
    db.commit()
    return str(row[0])


def _entity_of(db: Any, mention_id: str) -> str:
    return str(
        db.execute(
            "SELECT entity_id FROM cmap.mention WHERE id = %s", (mention_id,)
        ).fetchone()[0]
    )


class FakeFrontier:
    """Judge answers from ``same`` (mention name → candidate name substring);
    describer answers from ``names`` (entity type → canonical name)."""

    def __init__(
        self, same: dict[str, str] | None = None, names: dict[str, str] | None = None
    ) -> None:
        self.same = same or {}
        self.names = names or {}
        self.judge_prompts: list[dict[str, Any]] = []
        self.describe_prompts: list[str] = []

    @staticmethod
    def _block(prompt: str, label: str) -> Any:
        return json.loads(prompt.split(f"{label}:\n<<<\n", 1)[1].split("\n>>>", 1)[0])

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        if "CANDIDATES:" in prompt:
            mention = self._block(prompt, "MENTION")
            candidates = self._block(prompt, "CANDIDATES")
            self.judge_prompts.append({"mention": mention, "candidates": candidates})
            target = self.same.get(mention["name"])
            pick = None
            for candidate in candidates:
                if (
                    target
                    and target.casefold() in candidate["canonical_name"].casefold()
                ):
                    pick = candidate["id"]
            answer = {"same_as": pick, "confidence": 0.9, "reason": "test"}
        else:
            self.describe_prompts.append(prompt)
            entity_type = prompt.split("TYPE: ", 1)[1].split("\n", 1)[0]
            answer = {
                "canonical_name": self.names.get(entity_type, ""),
                "description": "Described.",
            }
        return {
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"total_tokens": 50},
        }


def _fake(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> FakeFrontier:
    fake = FakeFrontier(**kwargs)
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    return fake


def test_fixtures_join_jessica_and_the_approval_process(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env
) -> None:
    """Done-when: one Person Jessica across ≥2 sources; one licensing-approval Process."""
    fake_embeddings(monkeypatch)
    fake_scaledown(monkeypatch, "transcript.json")
    transcript = _seed_fixture(db, TRANSCRIPT_FIXTURE, "transcript")
    handle_classify_extract({"payload": {"source_id": transcript}})
    # Give every flat mention its own direction, then place the named spellings.
    for (mention_id,) in db.execute("SELECT id FROM cmap.mention").fetchall():
        db.execute(
            "UPDATE cmap.mention SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_unit(str(mention_id))), mention_id),
        )
    db.commit()
    approval = _unit("licensing approval")
    db.execute(
        "UPDATE cmap.mention SET embedding = %s::vector "
        "WHERE entity_type = 'Process' AND normalized_name = 'licensor signoff'",
        (vector_literal(approval),),
    )
    db.commit()

    flowchart = _seed_text(
        db,
        'FLOWCHART. n4 "Record sign-off (Jessica)". Licensing approval is recorded by J. '
        "Jessica Smith owns the licensing manager's sign-off.",
        "flowchart",
    )
    _mention(db, flowchart, "Person", "Jessica Smith", _unit("jessica smith"))
    _mention(db, flowchart, "Person", "J.", _unit("j initial"))
    _mention(
        db, flowchart, "Role", "the licensing manager's sign-off", _unit("role signoff")
    )
    process = _mention(
        db,
        flowchart,
        "Process",
        "licensing approval",
        _at_cosine(approval, 0.86, "near"),
    )
    fake = _fake(
        monkeypatch,
        same={
            "licensing approval": "licensor sign-off",
            "the licensor sign-off": "licensing approval",
        },
        names={"Person": "Jessica Smith (Licensing Manager)"},
    )

    stats = run_resolve()

    people = db.execute(
        "SELECT canonical_name, source_count FROM cmap.entity "
        "WHERE entity_type = 'Person' AND canonical_name ILIKE 'jessica%%'"
    ).fetchall()
    assert people == [("Jessica Smith (Licensing Manager)", 2)]
    jessica = db.execute(
        "SELECT DISTINCT entity_id FROM cmap.mention WHERE entity_type = 'Person' "
        "AND normalized_name IN ('jessica', 'j', 'jessica smith')"
    ).fetchall()
    assert len(jessica) == 1
    role = db.execute(
        "SELECT entity_type FROM cmap.mention WHERE surface_name = 'the licensing manager''s sign-off'"
    ).fetchone()
    assert role[0] == "Role"
    sign_off = db.execute(
        "SELECT entity_id FROM cmap.mention WHERE entity_type = 'Process' "
        "AND normalized_name = 'licensor signoff'"
    ).fetchone()[0]
    assert str(sign_off) == _entity_of(db, process)
    assert stats.get("judge_calls", 0) >= 1
    assert all("Jessica" not in item["mention"]["name"] for item in fake.judge_prompts)
    assert (
        db.execute(
            "SELECT count(*) FROM cmap.mention WHERE entity_id IS NULL"
        ).fetchone()[0]
        == 0
    )


def test_first_name_unique_match(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env
) -> None:
    fake = _fake(monkeypatch)
    source = _seed_text(db, "Jessica Smith approves. Jessica files it.", "first-unique")
    full = _mention(db, source, "Person", "Jessica Smith", _unit("a"))
    short = _mention(db, source, "Person", "Jessica", _unit("b"))
    run_resolve()
    assert _entity_of(db, full) == _entity_of(db, short)
    assert fake.judge_prompts == []


def test_first_name_ambiguous_goes_to_judge(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env
) -> None:
    fake = _fake(monkeypatch, same={"Jessica": "Wong"})
    source = _seed_text(
        db, "Jessica Smith and Jessica Wong. Jessica replied.", "first-ambiguous"
    )
    _mention(db, source, "Person", "Jessica Smith", _unit("smith"))
    wong = _mention(db, source, "Person", "Jessica Wong", _unit("wong"))
    short = _mention(db, source, "Person", "Jessica", _unit("short"))
    run_resolve()
    assert len(fake.judge_prompts) == 1
    names = sorted(
        item["canonical_name"] for item in fake.judge_prompts[0]["candidates"]
    )
    assert names == ["Jessica Smith", "Jessica Wong"]
    assert _entity_of(db, short) == _entity_of(db, wong)


def test_embedding_threshold(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env
) -> None:
    """≥0.92 assigns without the judge; [0.80, 0.92) asks it; below 0.80 is new."""
    fake = _fake(monkeypatch)
    source = _seed_text(
        db, "Artwork Log, the art log, the artwork tracker, the PO system.", "embed"
    )
    base = _unit("artwork log")
    log = _mention(db, source, "System", "Artwork Log Sheet", base)
    close = _mention(db, source, "System", "art log", _at_cosine(base, 0.95, "close"))
    band = _mention(db, source, "System", "tracker", _at_cosine(base, 0.85, "band"))
    far = _mention(db, source, "System", "PO", _at_cosine(base, 0.30, "far"))
    run_resolve()
    assert _entity_of(db, close) == _entity_of(db, log)
    assert [item["mention"]["name"] for item in fake.judge_prompts] == ["tracker"]
    assert _entity_of(db, band) != _entity_of(db, log)
    assert _entity_of(db, far) != _entity_of(db, log)
    names = {
        row[0]
        for row in db.execute("SELECT canonical_name FROM cmap.entity").fetchall()
    }
    assert "Artwork Log Sheet" in names and "Tracker" in names


def test_judge_no_means_new_entity(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env
) -> None:
    fake = _fake(monkeypatch)
    source = _seed_text(db, "Sample room review and sample room booking.", "judge-no")
    base = _unit("sample room")
    review = _mention(db, source, "Process", "sample room review", base)
    booking = _mention(
        db, source, "Process", "room booking", _at_cosine(base, 0.88, "booking")
    )
    run_resolve()
    assert len(fake.judge_prompts) == 1
    assert _entity_of(db, review) != _entity_of(db, booking)
    decided = db.execute(
        "SELECT decided_same FROM cmap.resolve_decision WHERE mention_id = %s",
        (booking,),
    ).fetchall()
    assert decided == [(False,)]


def test_second_pass_does_not_reask(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env
) -> None:
    fake = _fake(monkeypatch)
    source = _seed_text(db, "Sample room review and sample room booking.", "reask")
    base = _unit("sample room 2")
    _mention(db, source, "Process", "sample room review", base)
    booking = _mention(
        db, source, "Process", "room booking", _at_cosine(base, 0.88, "booking2")
    )
    run_resolve()
    created = _entity_of(db, booking)
    db.execute("UPDATE cmap.mention SET entity_id = NULL WHERE id = %s", (booking,))
    db.execute("DELETE FROM cmap.entity WHERE id = %s", (created,))
    db.commit()
    handle_resolve({"payload": {}})
    assert len(fake.judge_prompts) == 1
    assert _entity_of(db, booking) != "None"


def test_describe_runs_once_per_count(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env
) -> None:
    fake = _fake(monkeypatch, names={"System": "Artwork Log"})
    fake_embeddings(monkeypatch)
    source = _seed_text(db, "artwork log three times", "describe")
    for index in range(3):
        _mention(
            db, source, "System", "artwork log", _unit("x"), quote=f"quote {index}"
        )
    run_resolve()
    run_resolve()
    assert len(fake.describe_prompts) == 1
    row = db.execute(
        "SELECT canonical_name, mention_count, source_count, embedding FROM cmap.entity"
    ).fetchone()
    assert row[:3] == ("Artwork Log", 3, 1)
    refreshed = 0.001 * len("Artwork Log — Described.")
    assert float(str(row[3]).strip("[]").split(",")[0]) == pytest.approx(refreshed)


def test_cap_hit_then_rerun_describes_remaining(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env
) -> None:
    """A describe pass cut off by the frontier cap resumes on the next run."""
    fake = _fake(
        monkeypatch, names={"System": "Artwork Log", "Process": "Sample Room"}
    )
    fake_embeddings(monkeypatch)
    source = _seed_text(db, "artwork log and sample room", "cap-resume")
    for index in range(3):
        _mention(db, source, "System", "artwork log", _unit("x"), quote=f"a {index}")
        _mention(db, source, "Process", "sample room", _unit("y"), quote=f"b {index}")
    monkeypatch.setenv("BRAIN_MAX_FRONTIER_CALLS_PER_JOB", "1")
    get_settings.cache_clear()
    with pytest.raises(resolve_mod.FrontierCapReached):
        run_resolve()
    described = db.execute(
        "SELECT count(*) FROM cmap.entity WHERE described_at_count = mention_count"
    ).fetchone()[0]
    assert described == 1
    monkeypatch.setenv("BRAIN_MAX_FRONTIER_CALLS_PER_JOB", "10")
    get_settings.cache_clear()
    stats = run_resolve()
    assert stats["described"] == 1
    assert len(fake.describe_prompts) == 2
    rows = db.execute(
        "SELECT canonical_name, described_at_count FROM cmap.entity ORDER BY canonical_name"
    ).fetchall()
    assert rows == [("Artwork Log", 3), ("Sample Room", 3)]


def test_frontier_tolerates_trailing_comma_and_fence(
    monkeypatch: pytest.MonkeyPatch, frontier_env
) -> None:
    """Live smoke finding: describe answers may fence the JSON and add commas."""

    def _post_chat(messages: list, settings: Any) -> dict[str, Any]:
        del messages, settings
        return {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{\n  "canonical_name": "Thursday",\n'
                        '  "description": "A day.",\n}\n```'
                    }
                }
            ],
            "usage": {"total_tokens": 5},
        }

    monkeypatch.setattr(resolve_mod, "_post_chat", _post_chat)
    frontier = resolve_mod._Frontier(get_settings())
    assert frontier.ask("prompt") == {
        "canonical_name": "Thursday",
        "description": "A day.",
    }


def test_frontier_salvages_truncated_describe_fields(
    monkeypatch: pytest.MonkeyPatch, frontier_env
) -> None:
    """Live smoke finding: describe answers can be cut off at max_tokens."""

    def _post_chat(messages: list, settings: Any) -> dict[str, Any]:
        del messages, settings
        return {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{\n  "canonical_name": "Ilona",\n'
                        '  "description": "Ilona discusses the approval'
                    }
                }
            ],
            "usage": {"total_tokens": 5},
        }

    monkeypatch.setattr(resolve_mod, "_post_chat", _post_chat)
    frontier = resolve_mod._Frontier(get_settings())
    assert frontier.ask("prompt") == {"canonical_name": "Ilona"}
