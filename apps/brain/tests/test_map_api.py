"""Company Map read endpoints over the projected fixture map (plan step 10).

The map is built by ``tests/map_seed.py`` from the frozen fixtures with every
model call replayed; the endpoints are exercised the way the ``/map`` pages
call them through the proxy.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from map_seed import LICENSING_TITLE, seed_map


@pytest.fixture()
def seeded(db: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return seed_map(db, monkeypatch)


def test_company_and_community_cards(
    seeded: dict[str, Any], client: TestClient, user_headers: dict[str, str]
) -> None:
    company = client.get("/map/company", headers=user_headers).json()["company"]
    assert company["title"] == "Company overview"
    assert company["summary"]
    assert 0 < len(company["issues"]) <= 10
    assert all(issue["sources"] for issue in company["issues"])
    cards = client.get("/communities?level=1", headers=user_headers).json()["communities"]
    licensing = [card for card in cards if card["id"] == seeded["licensing_community_id"]]
    assert licensing and licensing[0]["title"] == LICENSING_TITLE
    assert licensing[0]["finding_count"] >= 1
    assert licensing[0]["summary"]


def test_community_detail_has_findings_and_graph(
    seeded: dict[str, Any], client: TestClient, user_headers: dict[str, str]
) -> None:
    body = client.get(
        f"/communities/{seeded['licensing_community_id']}", headers=user_headers
    ).json()
    assert body["title"] == LICENSING_TITLE
    stances = {finding["stance"] for finding in body["findings"]}
    assert stances <= {"policy", "practice", "report", "inference"}
    chips = {source["id"] for finding in body["findings"] for source in finding["sources"]}
    assert chips
    node_ids = {node["id"] for node in body["graph"]["nodes"]}
    assert seeded["jessica_id"] in node_ids
    assert body["graph"]["edges"]
    for edge in body["graph"]["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids
        assert edge["weight"] >= 1
    assert body["graph"]["truncated"] is False


def test_entity_neighbours_quote_the_transcript(
    seeded: dict[str, Any], client: TestClient, user_headers: dict[str, str]
) -> None:
    body = client.get(f"/entities/{seeded['jessica_id']}", headers=user_headers).json()
    assert body["canonical_name"] == seeded["jessica_name"]
    assert body["type"] == "Person"
    assert body["aliases"]
    assert seeded["transcript_id"] in {source["id"] for source in body["sources"]}
    quotes = [
        quote
        for group in body["neighbours"].values()
        for neighbour in group
        for quote in neighbour["quotes"]
    ]
    assert any(quote["source_id"] == seeded["transcript_id"] for quote in quotes)
    chunks = client.get(
        f"/sources/{seeded['transcript_id']}/chunks", headers=user_headers
    ).json()
    texts = {chunk["id"]: chunk["text"] for chunk in chunks["chunks"]}
    for quote in quotes:
        if quote["source_id"] == seeded["transcript_id"]:
            assert quote["quote"] in texts[quote["chunk_id"]]


def test_source_chunks_in_order(
    seeded: dict[str, Any], client: TestClient, user_headers: dict[str, str]
) -> None:
    body = client.get(f"/sources/{seeded['pdf_id']}/chunks", headers=user_headers).json()
    assert body["source"]["kind"] == "pdf"
    ordinals = [chunk["ordinal"] for chunk in body["chunks"]]
    assert ordinals == sorted(ordinals) and ordinals
    assert all(chunk["locator"] is not None for chunk in body["chunks"])


def test_search_finds_entity_source_and_community(
    seeded: dict[str, Any], client: TestClient, user_headers: dict[str, str]
) -> None:
    body = client.get("/search?q=jessica", headers=user_headers).json()
    assert seeded["jessica_id"] in {item["id"] for item in body["entities"]}
    body = client.get("/search?q=teams-approval", headers=user_headers).json()
    assert seeded["transcript_id"] in {item["id"] for item in body["sources"]}
    body = client.get("/search?q=licensing", headers=user_headers).json()
    assert seeded["licensing_community_id"] in {item["id"] for item in body["communities"]}


def test_unknown_ids_are_404(client: TestClient, user_headers: dict[str, str]) -> None:
    for path in (
        "/communities/not-a-uuid",
        "/entities/00000000-0000-4000-8000-000000000000",
        "/sources/00000000-0000-4000-8000-000000000000/chunks",
    ):
        assert client.get(path, headers=user_headers).status_code == 404


def test_reads_need_the_token(client: TestClient) -> None:
    assert client.get("/map/company").status_code == 401


def test_rebuild_is_admin_only_and_queues_resolve_once(
    client: TestClient,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
    db: Any,
) -> None:
    assert client.post("/map/rebuild", headers=user_headers).status_code == 403
    first = client.post("/map/rebuild", headers=admin_headers).json()
    second = client.post("/map/rebuild", headers=admin_headers).json()
    assert first["queued"] is True
    assert second["queued"] is False
    kinds = [row[0] for row in db.execute("SELECT kind FROM cmap.job").fetchall()]
    assert kinds == ["resolve"]
