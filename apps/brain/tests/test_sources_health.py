"""Pipeline health endpoint ``GET /sources/health`` (repair plan B4).

The admin panel on ``/map/sources`` reads this one endpoint: sources by read
state, failed and retrying jobs with their error text, passages whose
extraction failed (repair A2), the last successful graph build, and the
New York day's recorded model usage.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def test_sources_health_requires_admin(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    assert client.get("/sources/health").status_code == 401
    assert client.get("/sources/health", headers=user_headers).status_code == 403


def test_sources_health_reports_zeroes_when_empty(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    body = client.get("/sources/health", headers=admin_headers).json()
    assert body["sources_by_state"] == {
        "queued": 0,
        "reading": 0,
        "extracting": 0,
        "read": 0,
        "partial": 0,
        "failed": 0,
    }
    assert body["jobs"] == {"failed": [], "retrying": []}
    assert body["failed_extractions"] == []
    assert body["last_build"] is None
    assert body["spend_today"]["tokens"] == 0
    assert body["spend_today"]["calls"] == 0


def test_health_surfaces_failed_and_retrying_job_errors(
    client: TestClient,
    admin_headers: dict[str, str],
    db: Any,
) -> None:
    """A seeded failed job appears with its error text, and so does a retry."""
    db.execute(
        "INSERT INTO cmap.job (kind, payload, state, attempts, error) VALUES "
        "('read_source', '{\"source_id\": \"11111111-1111-4111-8111-111111111111\"}'::jsonb, "
        "'failed', 3, 'provider returned 503 on read_source')"
    )
    db.execute(
        "INSERT INTO cmap.job (kind, payload, state, attempts, error, run_after) VALUES "
        "('classify_extract', '{}'::jsonb, 'queued', 1, 'provider returned 429', "
        "now() + interval '5 minutes')"
    )
    db.commit()

    body = client.get("/sources/health", headers=admin_headers).json()
    failed = body["jobs"]["failed"]
    assert [(job["kind"], job["error"], job["attempts"]) for job in failed] == [
        ("read_source", "provider returned 503 on read_source", 3)
    ]
    retrying = body["jobs"]["retrying"]
    assert [(job["kind"], job["error"], job["attempts"]) for job in retrying] == [
        ("classify_extract", "provider returned 429", 1)
    ]
    assert retrying[0]["run_after"] is not None


def test_health_reports_states_failed_extractions_build_and_spend(
    client: TestClient,
    admin_headers: dict[str, str],
    db: Any,
) -> None:
    source_id = "22222222-2222-4222-8222-222222222222"
    db.execute(
        "INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes, read_state) "
        "VALUES (%s, 'text', 'Health fixture', 'cmap/x/health.txt', 'abc123', 10, 'partial')",
        (source_id,),
    )
    db.execute(
        "INSERT INTO cmap.chunk (id, source_id, ordinal, locator, text, token_count) VALUES "
        "('33333333-3333-4333-8333-333333333333', %s, 1, '{\"page\": 3}', 'poison', 5)",
        (source_id,),
    )
    db.execute(
        "INSERT INTO cmap.extraction (chunk_id, stage, prompt_hash, model, payload, error) "
        "VALUES ('33333333-3333-4333-8333-333333333333', 'flat', 'failed', '-', '{}'::jsonb, "
        "'provider returned 502')"
    )
    db.execute(
        "INSERT INTO cmap.graph_version (version, node_count, edge_count) VALUES (7, 4, 9)"
    )
    db.execute(
        "INSERT INTO cmap.community (level, entity_ids, graph_version) VALUES (0, '{}', 7)"
    )
    db.execute(
        "INSERT INTO cmap.job (kind, payload, state, attempts) VALUES "
        "('project', '{\"usage\": {\"frontier_tokens\": 100, \"frontier_calls\": 2, "
        "\"nodes\": 4}}'::jsonb, 'done', 1)"
    )
    db.commit()

    body = client.get("/sources/health", headers=admin_headers).json()
    assert body["sources_by_state"]["partial"] == 1
    assert body["sources_by_state"]["read"] == 0

    extractions = body["failed_extractions"]
    assert [(item["source_title"], item["ordinal"], item["error"]) for item in extractions] == [
        ("Health fixture", 1, "provider returned 502")
    ]
    assert extractions[0]["chunk_id"] == "33333333-3333-4333-8333-333333333333"
    assert extractions[0]["stage"] == "flat"

    assert body["last_build"] == {
        "version": 7,
        "projected_at": body["last_build"]["projected_at"],
        "node_count": 4,
        "edge_count": 9,
        "map_version": 7,
    }
    assert body["last_build"]["projected_at"] is not None

    spend = body["spend_today"]
    day = db.execute(
        "SELECT (now() AT TIME ZONE 'America/New_York')::date::text"
    ).fetchone()[0]
    assert spend["day"] == day
    assert spend["timezone"] == "America/New_York"
    assert spend["tokens"] == 100
    assert spend["calls"] == 2
    assert spend["usage"]["frontier_tokens"] == 100
    assert spend["usage"]["nodes"] == 4
