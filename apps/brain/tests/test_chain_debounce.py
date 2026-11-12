"""Debounce of the resolve→project→function_assign→communities chain (issue #415).

Several sources ingested within a short window must produce one ``resolve``
and one ``communities`` run. The Map still updates within the stated bound:
the chain starts ``DEBOUNCE_SECONDS`` after the last source's relations
complete, ``MAX_DELAY_SECONDS`` from the first source of the batch at the
latest, and the Map reflects the burst after that hold plus one chain run.
No test calls a real model.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import fake_embeddings, fake_relations, fake_scaledown

from brain import function_assign as fa_mod
from brain.config import get_settings
from brain.extract import relations as relations_mod
from brain.extract.relations import _enqueue_resolve
from brain.migrate import migrate
from brain.resolve import resolve as resolve_mod
from brain.worker import claim_next_job, finish_job, run_handler

JESSICA = "Marco: Jessica is the only licensing manager we have."


def _response(**relation: Any) -> dict[str, Any]:
    base = {
        "from": "m1",
        "to": "m2",
        "type": "PERFORMS",
        "description": "Jessica holds the licensing manager role.",
        "stance": "report",
        "confidence": 0.9,
        "quote": "Jessica is the only licensing manager we have.",
    }
    base.update(relation)
    return {"relations": [base], "new_mentions": []}


class ChainFake:
    """Replay judge, describe and community-report prompts."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(
        self, messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del settings, max_tokens
        prompt = str(messages[-1]["content"])
        self.prompts.append(prompt)
        if "CANDIDATES:" in prompt:
            answer: dict[str, Any] = {"same_as": None, "confidence": 0.9, "reason": "test"}
        elif "TYPE: " in prompt:
            answer = {"canonical_name": "", "description": "Described."}
        else:
            answer = {
                "title": "Burst chain",
                "summary": "One chain run for the burst.",
                "findings": [],
                "open_questions": [],
            }
        return {
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"total_tokens": 50},
        }


@pytest.fixture()
def pipeline_env(monkeypatch: pytest.MonkeyPatch):
    """ScaleDown on for the flat stage; deterministic embeddings and names."""
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)

    def _names(
        names: list[str], settings: Any, usage: dict[str, int]
    ) -> list[list[float]]:
        del settings, usage
        out = []
        for index, _name in enumerate(names):
            vector = [0.0] * 1024
            vector[index % 1024] = 1.0
            out.append(vector)
        return out

    monkeypatch.setattr(resolve_mod, "embed_names", _names)
    yield
    get_settings.cache_clear()


def _drain(monkeypatch: pytest.MonkeyPatch, kinds: tuple[str, ...]) -> list[str]:
    """Run claim→handle→finish over the queue; stop on a job outside ``kinds``."""
    ran: list[str] = []
    while (job := claim_next_job()) is not None:
        if job["kind"] not in kinds:
            break
        error: str | None = None
        try:
            run_handler(job)
        except Exception as exc:  # the worker records failures the same way
            error = str(exc)
        finish_job(job["id"], error)
        assert error is None, error
        ran.append(job["kind"])
    return ran


def test_burst_queues_one_held_resolve(db: Any) -> None:
    """Three sources finishing relations close together share one held job."""
    for _ in range(3):
        _enqueue_resolve()
    held = db.execute(
        "SELECT count(*), bool_and(run_after > now()), "
        "bool_and(run_after <= now() + make_interval(secs => %s)) "
        "FROM cmap.job WHERE kind = 'resolve' AND state = 'queued'",
        (relations_mod.DEBOUNCE_SECONDS,),
    ).fetchone()
    assert held == (1, True, True)
    assert claim_next_job() is None


def test_new_source_pushes_the_hold(db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A source arriving inside the window restarts the quiet countdown."""
    monkeypatch.setattr(relations_mod, "DEBOUNCE_SECONDS", 600.0)
    _enqueue_resolve()
    db.execute("UPDATE cmap.job SET run_after = now() + interval '60 seconds'")
    db.commit()
    _enqueue_resolve()
    remaining = db.execute(
        "SELECT extract(epoch FROM run_after - now()) FROM cmap.job"
    ).fetchone()[0]
    assert float(remaining) > 300
    assert db.execute("SELECT count(*) FROM cmap.job").fetchone()[0] == 1


def test_hold_is_capped_so_the_map_always_updates(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hold never outlives MAX_DELAY_SECONDS from the first source."""
    monkeypatch.setattr(relations_mod, "DEBOUNCE_SECONDS", 600.0)
    monkeypatch.setattr(relations_mod, "MAX_DELAY_SECONDS", 900.0)
    _enqueue_resolve()
    db.execute(
        "UPDATE cmap.job SET created_at = now() - interval '20 minutes', "
        "run_after = now() + interval '60 seconds'"
    )
    db.commit()
    _enqueue_resolve()
    capped = db.execute(
        "SELECT run_after <= now(), run_after <= created_at + make_interval(secs => %s) "
        "FROM cmap.job",
        (relations_mod.MAX_DELAY_SECONDS,),
    ).fetchone()
    assert capped == (True, True)
    assert claim_next_job() is not None


def test_due_hold_is_never_pushed_back(db: Any) -> None:
    """A job whose hold has expired (or a manual rebuild) runs on time."""
    _enqueue_resolve()
    db.execute("UPDATE cmap.job SET run_after = now() - interval '1 second'")
    db.commit()
    _enqueue_resolve()
    row = db.execute(
        "SELECT count(*), bool_and(run_after <= now()) FROM cmap.job WHERE kind = 'resolve'"
    ).fetchone()
    assert row == (1, True)


def test_manual_rebuild_wakes_the_hold(
    client: Any, admin_headers: dict[str, str], db: Any
) -> None:
    """/map/rebuild coalesces with the hold but makes it due immediately."""
    _enqueue_resolve()
    body = client.post("/map/rebuild", headers=admin_headers).json()
    assert body["queued"] is False
    row = db.execute(
        "SELECT count(*), bool_and(run_after <= now()) FROM cmap.job WHERE kind = 'resolve'"
    ).fetchone()
    assert row == (1, True)


def test_burst_of_sources_runs_the_chain_once(
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
    client: Any,
    admin_headers: dict[str, str],
    pipeline_env: Any,
) -> None:
    """Done-when: several sources ingested close together produce one resolve
    and one communities run, and the Map updates within the stated bound."""
    migrate()  # the C1 function vocabulary the assignment job classifies against
    fake_scaledown(monkeypatch, "transcript.json")
    rel = fake_relations(monkeypatch)
    rel.override = _response()
    chain = ChainFake()
    monkeypatch.setattr(resolve_mod, "_post_chat", chain)
    monkeypatch.setattr(fa_mod, "_post_chat", chain)

    for title in ["burst one", "burst two", "burst three"]:
        response = client.post(
            "/sources/transcript",
            headers=admin_headers,
            json={"text": f"{JESSICA} ({title})", "title": title},
        )
        assert response.status_code == 200, response.text

    per_source = _drain(monkeypatch, ("read_source", "classify_extract", "relations"))
    assert per_source.count("relations") == 3

    burst = db.execute(
        "SELECT count(*), bool_and(run_after > now()), "
        "bool_and(run_after <= now() + make_interval(secs => %s)) "
        "FROM cmap.job WHERE kind = 'resolve' AND state = 'queued'",
        (relations_mod.DEBOUNCE_SECONDS,),
    ).fetchone()
    assert burst == (1, True, True)
    assert claim_next_job() is None

    db.execute("UPDATE cmap.job SET run_after = now() WHERE kind = 'resolve'")
    db.commit()

    chain_kinds = _drain(
        monkeypatch, ("resolve", "project", "function_assign", "communities")
    )
    assert chain_kinds[0] == "resolve" and chain_kinds[-1] == "communities"
    assert sorted(chain_kinds[1:-1]) == ["function_assign", "project"]
    done = db.execute(
        "SELECT kind, state FROM cmap.job "
        "WHERE kind IN ('resolve', 'project', 'function_assign', 'communities')"
    ).fetchall()
    assert sorted(done) == [
        ("communities", "done"),
        ("function_assign", "done"),
        ("project", "done"),
        ("resolve", "done"),
    ]
    assert db.execute("SELECT count(*) FROM cmap.graph_version").fetchone()[0] >= 1
    assert db.execute("SELECT count(*) FROM cmap.community").fetchone()[0] >= 1


def test_stalled_chain_is_healed(db: Any) -> None:
    """Repair A2: work left behind is picked up without another upload."""
    from test_flat import _seed_text
    from test_project import _mention

    from brain.chain import maybe_queue_ensure_chain, run_ensure_chain

    def _jobs() -> list[tuple[str, str | None]]:
        db.commit()
        return [
            (str(kind), source)
            for kind, source in db.execute(
                "SELECT kind, payload->>'source_id' FROM cmap.job "
                "WHERE state = 'queued' ORDER BY kind, 2"
            ).fetchall()
        ]

    # 1. A source stuck in 'extracting' with no job at all is re-queued; one
    #    whose last job failed for good is marked failed with the reason; one
    #    with a job still waiting is left alone.
    lost = _seed_text(db, "The buyer waits for sign-off.", "lost")
    dead = _seed_text(db, "The licensor signs the artwork.", "dead")
    busy = _seed_text(db, "The factory ships the order.", "busy")
    never_read = _seed_text(db, "The vendor quotes the price.", "never-read")
    db.execute(
        "UPDATE cmap.source SET read_state = 'extracting' WHERE id = ANY(%s::uuid[])",
        ([lost, dead, busy],),
    )
    db.execute(
        "UPDATE cmap.source SET read_state = 'queued', created_at = now() - interval '1 hour' "
        "WHERE id = %s",
        (never_read,),
    )
    db.execute(
        "INSERT INTO cmap.job (kind, payload, state, attempts, error, finished_at) "
        "VALUES ('relations', jsonb_build_object('source_id', %s::text), 'failed', 3, "
        "'model unavailable', now())",
        (dead,),
    )
    db.execute(
        "INSERT INTO cmap.job (kind, payload, state) "
        "VALUES ('classify_extract', jsonb_build_object('source_id', %s::text), 'running')",
        (busy,),
    )
    db.commit()
    stats = run_ensure_chain()
    assert stats["classify_extract"] == 1 and stats["marked_failed"] == 1
    assert stats["read_source"] == 1
    assert _jobs() == [("classify_extract", lost), ("read_source", never_read)]
    db.commit()
    assert db.execute(
        "SELECT read_state, read_error FROM cmap.source WHERE id = %s", (dead,)
    ).fetchone() == ("failed", "model unavailable")
    # Running it again queues nothing twice.
    assert not any(run_ensure_chain().values())

    # 2. Unresolved mentions with no resolve job.
    db.execute("DELETE FROM cmap.job")
    db.execute("UPDATE cmap.source SET read_state = 'read'")
    _mention(db, lost, "Role", "Buyer", None)
    db.commit()
    assert run_ensure_chain()["resolve"] == 1
    assert _jobs() == [("resolve", None)]

    # 3. A finished resolve with no projection after it, then a finished
    #    projection with no summary build after it.
    db.execute("DELETE FROM cmap.job")
    db.execute("DELETE FROM cmap.mention")
    db.execute(
        "INSERT INTO cmap.job (kind, payload, state, started_at, finished_at) "
        "VALUES ('resolve', '{}', 'done', now() - interval '2 minutes', now() - interval '1 minute')"
    )
    db.commit()
    assert run_ensure_chain()["project"] == 1
    db.execute(
        "UPDATE cmap.job SET state = 'done', started_at = now(), finished_at = now() "
        "WHERE kind = 'project'"
    )
    db.commit()
    assert run_ensure_chain()["function_assign"] == 1
    db.execute(
        "UPDATE cmap.job SET state = 'done', started_at = now(), finished_at = now() "
        "WHERE kind = 'function_assign'"
    )
    db.commit()
    assert run_ensure_chain()["communities"] == 1
    db.execute(
        "UPDATE cmap.job SET state = 'done', started_at = now(), finished_at = now() "
        "WHERE kind = 'communities'"
    )
    db.commit()
    assert not any(run_ensure_chain().values()), "a healthy chain is left alone"

    # 4. The worker queues the healing job at most once an hour.
    assert maybe_queue_ensure_chain() is True
    assert maybe_queue_ensure_chain() is False
