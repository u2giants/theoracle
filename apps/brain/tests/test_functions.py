"""Repair plan C1 gate: the curated business-function list (``cmap.function``).

The seed lands the 13 owner-proposal functions, clustered from Department
evidence (see ``sql/022_functions.sql``); the admin API renames, adds, merges
and retires them and nothing else — no approval queues, no permissions beyond
login + admin. Re-running the migration never duplicates or clobbers rows.

Repair C2 gates (assignment) live at the bottom of this file: a hand-off
entity in two functions, admin rows surviving a re-run, and the department
hint as a prior rather than an override.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from psycopg.types.json import Json

from brain.config import get_settings
from brain.function_assign import backfill_eval_functions, handle_function_assign
from brain.migrate import migrate

SEEDED = [
    ("sales-customer-accounts", "Sales & Customer Accounts"),
    ("licensing", "Licensing"),
    ("product-design-development", "Product Design & Development"),
    ("sourcing-vendor-management", "Sourcing & Vendor Management"),
    ("sampling", "Sampling"),
    ("production-quality", "Production & Quality"),
    ("logistics-shipping", "Logistics & Shipping"),
    ("compliance-testing", "Compliance & Testing"),
    ("finance-accounting", "Finance & Accounting"),
    ("it-systems", "IT & Systems"),
    ("hr-administration", "HR & Administration"),
    ("china-office-operations", "China Office Operations"),
    ("executive-company-wide", "Executive/Company-wide"),
]


def _list(client: Any, headers: dict[str, str]) -> list[dict[str, Any]]:
    return client.get("/functions", headers=headers).json()["functions"]


def _by_key(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next(row for row in rows if row["key"] == key)


@pytest.fixture()
def seeded(client: Any, admin_headers: dict[str, str]) -> list[dict[str, Any]]:
    """Land the C1 seed (the migration re-runs it) after the per-test truncate."""
    migrate()
    return _list(client, admin_headers)


def test_seed_and_edit_roundtrip(
    seeded: list[dict[str, Any]],
    client: Any,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
) -> None:
    """The 13 seeded functions land; rename, add, merge and retire round-trip
    through the API; re-migration is idempotent and preserves owner edits."""
    assert [(row["key"], row["name"]) for row in seeded] == SEEDED

    sampling = _by_key(seeded, "sampling")
    denied = client.put(
        f"/functions/{sampling['id']}",
        json={"name": "Sampling & Fit"},
        headers=user_headers,
    )
    assert denied.status_code == 403

    renamed = client.put(
        f"/functions/{sampling['id']}",
        json={"name": "Sampling & Fit"},
        headers=admin_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Sampling & Fit"
    assert renamed.json()["key"] == "sampling"  # the key stays stable

    added = client.post(
        "/functions",
        json={
            "key": "purchasing-quotes",
            "name": "Purchasing Quotes",
            "description": "Quote follow-up with suppliers.",
            "aliases": ["Purchasing"],
        },
        headers=admin_headers,
    )
    assert added.status_code == 200
    assert added.json()["sort"] == 140
    assert client.post(
        "/functions",
        json={"key": "purchasing-quotes", "name": "Dup"},
        headers=admin_headers,
    ).status_code == 409

    merged = client.post(
        f"/functions/{added.json()['id']}/merge",
        json={"into": "sourcing-vendor-management"},
        headers=admin_headers,
    )
    assert merged.status_code == 200
    body = merged.json()
    assert body["merged"]["active"] is False
    assert body["merged"]["parent_id"] == body["into"]["id"]
    assert "Purchasing Quotes" in body["into"]["aliases"]
    assert "Purchasing" in body["into"]["aliases"]

    retired = client.post(
        f"/functions/{sampling['id']}/retire", headers=admin_headers
    )
    assert retired.status_code == 200
    assert retired.json()["active"] is False

    rows = _list(client, admin_headers)
    assert _by_key(rows, "sampling")["active"] is False
    assert _by_key(rows, "sampling")["name"] == "Sampling & Fit"
    assert _by_key(rows, "purchasing-quotes")["active"] is False
    assert "Purchasing Quotes" in _by_key(rows, "sourcing-vendor-management")["aliases"]

    # Idempotent re-migration: no duplicate keys, and the owner's edits survive.
    migrate()
    migrate()
    rows = _list(client, admin_headers)
    assert len(rows) == len(SEEDED) + 1
    assert _by_key(rows, "sampling")["name"] == "Sampling & Fit"
    assert _by_key(rows, "sampling")["active"] is False
    assert _by_key(rows, "purchasing-quotes")["active"] is False


def test_reseed_is_idempotent(seeded: list[dict[str, Any]], db: Any) -> None:
    """Re-running the migration twice keeps exactly the seeded 13 rows."""
    del seeded
    migrate()
    migrate()
    rows = db.execute("SELECT key FROM cmap.function ORDER BY sort").fetchall()
    assert [row[0] for row in rows] == [key for key, _ in SEEDED]


def test_functions_require_token_and_admin(
    client: Any, user_headers: dict[str, str]
) -> None:
    """The vocabulary is readable by any employee; every mutation is
    login + admin (401 without the token, 403 for non-admins)."""
    migrate()
    assert client.get("/functions").status_code == 401
    assert (
        client.get("/functions", headers={"x-brain-token": "wrong"}).status_code == 401
    )
    assert client.get("/functions", headers=user_headers).status_code == 200

    for call in (
        lambda headers: client.post(
            "/functions", json={"key": "x", "name": "X"}, headers=headers
        ),
        lambda headers: client.put(
            "/functions/00000000-0000-4000-8000-000000000001",
            json={"name": "X"},
            headers=headers,
        ),
        lambda headers: client.post(
            "/functions/00000000-0000-4000-8000-000000000001/merge",
            json={"into": "sampling"},
            headers=headers,
        ),
        lambda headers: client.post(
            "/functions/00000000-0000-4000-8000-000000000001/retire",
            headers=headers,
        ),
    ):
        assert call({}).status_code == 401
        assert call({"x-brain-token": "wrong"}).status_code == 401
        assert call(user_headers).status_code == 403


def test_seed_aliases_match_department_evidence(
    seeded: list[dict[str, Any]],
) -> None:
    """Aliases carry the Department names the seed was clustered from
    (cmap_s8_base mention names, fixture entities, department_hint values)."""
    evidence = {
        "sales-customer-accounts": {"Sales Team", "Sales", "sales"},
        "licensing": {"Licensing Team", "Licensed Team", "license team"},
        "product-design-development": {
            "Creative",
            "creative team",
            "Technical Design",
            "design team",
        },
        "sourcing-vendor-management": {"Sourcing", "采购部"},
        "sampling": {"Sample Room"},
        "production-quality": {"Production Team", "production"},
        "china-office-operations": {"China team", "Sales China team"},
        "executive-company-wide": {"POP Creations", "New York office"},
    }
    for key, names in evidence.items():
        assert names <= set(_by_key(seeded, key)["aliases"]), key
    # No employee names in the seeded vocabulary.
    for row in seeded:
        assert "Jessica" not in row["aliases"]
        assert row["description"]


# ------------------------------------------------------------- C2 assignment


@pytest.fixture()
def assign_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flat seat must name a model for the assignment job to run."""
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_classifier(
    monkeypatch: pytest.MonkeyPatch, responses: dict[str, dict[str, Any]]
) -> None:
    """Replay function classification, matched on the passage text."""
    from brain import function_assign as fa_mod

    def _post_chat(
        messages: list[dict[str, Any]],
        settings: Any,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        del settings, max_tokens
        prompt = str(messages[-1]["content"])
        passage = prompt.split("PASSAGE:\n<<<\n", 1)[-1].split("\n>>>", 1)[0]
        payload: dict[str, Any] = {"functions": []}
        for match, answer in responses.items():
            if match in passage:
                payload = answer
                break
        return {
            "choices": [{"message": {"content": json.dumps(payload)}}],
            "usage": {"total_tokens": 10},
        }

    monkeypatch.setattr(fa_mod, "_post_chat", _post_chat)


def _seed_source(
    db: Any, title: str = "Handoff notes", department_hint: str | None = None
) -> str:
    row = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, "
        "department_hint) VALUES ('text', %s, %s, %s, 10, %s) RETURNING id::text",
        (title, f"cmap/test/{title}", f"sha-{title}", department_hint),
    ).fetchone()
    db.commit()
    return str(row[0])


def _seed_chunk(
    db: Any,
    source_id: str,
    text: str,
    ordinal: int = 0,
    locator: dict[str, Any] | None = None,
) -> str:
    row = db.execute(
        "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
        "VALUES (%s, %s, %s, %s, 5) RETURNING id::text",
        (source_id, ordinal, Json(locator or {}), text),
    ).fetchone()
    db.commit()
    return str(row[0])


def _seed_entity(db: Any, name: str = "Sample approval") -> str:
    row = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name) "
        "VALUES ('Step', %s) RETURNING id::text",
        (name,),
    ).fetchone()
    db.commit()
    return str(row[0])


def _seed_mention(db: Any, chunk_id: str, entity_id: str, name: str = "Sample approval") -> None:
    db.execute(
        "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
        "normalized_name, quote, entity_id) "
        "VALUES (%s, 'Step', %s, %s, 'the quoted hand-off step', %s)",
        (chunk_id, name, name.lower(), entity_id),
    )
    db.commit()


def _function_rows(
    db: Any, table: str, column: str, item_id: str
) -> dict[str, tuple[float, str]]:
    rows = db.execute(
        f"SELECT f.key, x.weight, x.origin FROM cmap.{table} x "
        f"JOIN cmap.function f ON f.id = x.function_id "
        f"WHERE x.{column} = %s ORDER BY f.key",
        (item_id,),
    ).fetchall()
    return {str(key): (float(weight), str(origin)) for key, weight, origin in rows}


def test_handoff_entity_in_two_functions(
    db: Any, monkeypatch: pytest.MonkeyPatch, assign_env: None
) -> None:
    """A hand-off step mentioned in two functions' passages carries both."""
    del assign_env
    migrate()
    source = _seed_source(db)
    chunk_a = _seed_chunk(db, source, "The licensing team signs off the package.", 0)
    chunk_b = _seed_chunk(db, source, "The sample room reviews the physical sample.", 1)
    entity = _seed_entity(db)
    _seed_mention(db, chunk_a, entity)
    _seed_mention(db, chunk_b, entity)
    _fake_classifier(
        monkeypatch,
        {
            "licensing team signs off": {
                "functions": [{"key": "licensing", "weight": 0.9}]
            },
            "sample room reviews": {
                "functions": [{"key": "sampling", "weight": 0.8}]
            },
        },
    )
    handle_function_assign({})
    rows = _function_rows(db, "entity_function", "entity_id", entity)
    assert set(rows) == {"licensing", "sampling"}
    assert rows["licensing"] == (pytest.approx(0.9), "auto")
    assert rows["sampling"] == (pytest.approx(0.8), "auto")
    source_rows = _function_rows(db, "source_function", "source_id", source)
    assert set(source_rows) == {"licensing", "sampling"}


def test_admin_assignment_survives_rerun(
    db: Any,
    monkeypatch: pytest.MonkeyPatch,
    assign_env: None,
    client: Any,
    admin_headers: dict[str, str],
) -> None:
    """origin='admin' rows set on the source and entity pages are never
    overwritten by a re-run; only the auto rows are recomputed."""
    del assign_env
    migrate()
    source = _seed_source(db, "Spec")
    chunk_a = _seed_chunk(db, source, "Design rework on the specification.", 0)
    entity = _seed_entity(db, "Spec rework")
    _seed_mention(db, chunk_a, entity, "Spec rework")
    _fake_classifier(
        monkeypatch,
        {
            "Design rework": {
                "functions": [{"key": "product-design-development", "weight": 0.7}]
            },
            "Production run": {
                "functions": [{"key": "production-quality", "weight": 0.6}]
            },
        },
    )
    handle_function_assign({})
    for path, entries in (
        (
            f"/sources/{source}/functions",
            [
                {"key": "licensing", "weight": 0.9},
                {"key": "product-design-development", "weight": 0.4},
            ],
        ),
        (f"/entities/{entity}/functions", [{"key": "licensing", "weight": 0.8}]),
    ):
        response = client.put(path, json={"functions": entries}, headers=admin_headers)
        assert response.status_code == 200, response.text

    # A new passage lands; the re-run recomputes the auto rows only.
    _seed_chunk(db, source, "Production run at the factory.", 1)
    handle_function_assign({})

    source_rows = _function_rows(db, "source_function", "source_id", source)
    assert source_rows["licensing"] == (pytest.approx(0.9), "admin")
    assert source_rows["product-design-development"] == (pytest.approx(0.4), "admin")
    assert source_rows["production-quality"] == (pytest.approx(0.6), "auto")
    entity_rows = _function_rows(db, "entity_function", "entity_id", entity)
    assert entity_rows["licensing"] == (pytest.approx(0.8), "admin")
    assert entity_rows["product-design-development"] == (pytest.approx(0.7), "auto")
    chunk_rows = _function_rows(db, "chunk_function", "chunk_id", chunk_a)
    assert chunk_rows["product-design-development"] == (pytest.approx(0.7), "auto")


def test_hint_is_prior_not_override(
    db: Any, monkeypatch: pytest.MonkeyPatch, assign_env: None
) -> None:
    """department_hint and the speaker's profile department are strong priors:
    they add and lift, but never remove or cap the passage's own evidence."""
    del assign_env
    migrate()
    db.execute(
        "INSERT INTO public.employees (id, email, name, role) "
        "VALUES ('00000000-0000-4000-8000-0000000000c1', 'ada@test.invalid', 'Ada', '') "
        "ON CONFLICT (id) DO NOTHING"
    )
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department) "
        "VALUES ('00000000-0000-4000-8000-0000000000c1', 'Sample Room') "
        "ON CONFLICT (employee_id) DO NOTHING"
    )
    db.commit()
    source = _seed_source(db, "Mixed notes", department_hint="Licensing")
    chunk_a = _seed_chunk(db, source, "The sample room reviews the physical sample.", 0)
    chunk_b = _seed_chunk(
        db,
        source,
        "Ada hands the file back.",
        1,
        locator={"turn": 2, "speaker": "Ada"},
    )
    _fake_classifier(
        monkeypatch,
        {
            "sample room reviews": {
                "functions": [{"key": "sampling", "weight": 0.9}]
            },
            "hands the file back": {"functions": []},
        },
    )
    handle_function_assign({})
    row_a = _function_rows(db, "chunk_function", "chunk_id", chunk_a)
    # The evidence wins: the sampling passage keeps its function at its weight,
    # and the Licensing hint joins below it as a prior.
    assert row_a["sampling"] == (pytest.approx(0.9), "auto")
    assert row_a["licensing"] == (pytest.approx(0.5), "auto")
    assert row_a["sampling"][0] > row_a["licensing"][0]
    row_b = _function_rows(db, "chunk_function", "chunk_id", chunk_b)
    # The model found nothing here; the two priors supply the functions.
    assert row_b["sampling"] == (pytest.approx(0.5), "auto")
    assert row_b["licensing"] == (pytest.approx(0.5), "auto")
    source_rows = _function_rows(db, "source_function", "source_id", source)
    assert set(source_rows) == {"licensing", "sampling"}


def test_eval_question_functions_backfilled(db: Any) -> None:
    """eval_question.function is pre-filled from the B1 question metadata,
    idempotently, and an admin's later edit is never clobbered."""
    migrate()
    data = json.loads(
        (Path(__file__).resolve().parents[1] / "eval" / "questions.b1.json").read_text(
            encoding="utf-8"
        )
    )
    item = next(q for q in data["questions"] if q.get("functions"))
    db.execute(
        "INSERT INTO cmap.eval_question (question, expected_points, "
        "expected_source_titles, author) VALUES (%s, ARRAY['a','b','c'], "
        "ARRAY[]::text[], 'seed')",
        (item["question"],),
    )
    db.commit()
    assert backfill_eval_functions(db) == 1
    db.commit()
    row = db.execute(
        "SELECT function FROM cmap.eval_question WHERE question = %s",
        (item["question"],),
    ).fetchone()
    assert list(row[0]) == item["functions"]
    assert backfill_eval_functions(db) == 0  # idempotent
    db.commit()
    db.execute(
        "UPDATE cmap.eval_question SET function = ARRAY['Edited'] WHERE question = %s",
        (item["question"],),
    )
    db.commit()
    assert backfill_eval_functions(db) == 0
    db.commit()
    row = db.execute(
        "SELECT function FROM cmap.eval_question WHERE question = %s",
        (item["question"],),
    ).fetchone()
    assert list(row[0]) == ["Edited"]
