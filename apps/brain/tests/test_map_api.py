"""Company Map read endpoints over the projected fixture map (plan step 10).

The map is built by ``tests/map_seed.py`` from the frozen fixtures with every
model call replayed; the endpoints are exercised the way the ``/map`` pages
call them through the proxy.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from map_seed import (
    CONTRADICTION_SUMMARY,
    INTERVIEW_OPEN,
    LICENSING_TITLE,
    seed_contradictions,
    seed_map,
)


@pytest.fixture()
def seeded(db: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return seed_map(db, monkeypatch)


@pytest.fixture()
def seeded_with_issues(db: Any, seeded: dict[str, Any]) -> dict[str, Any]:
    """The map plus the D3 rows the card issues compose from: one open
    conflict over entities assigned to licensing (the browser seed's set) and
    one gap row carrying the function name in ``department``."""
    seed_contradictions(db)
    db.execute(
        "INSERT INTO cmap.open_question (question, why, entity_ids, state, department) "
        "VALUES (%s, 'Sources disagree: fixture', '{}', 'open', %s)",
        (INTERVIEW_OPEN, LICENSING_TITLE),
    )
    db.commit()
    return seeded


def test_company_and_community_cards(
    seeded: dict[str, Any], client: TestClient, user_headers: dict[str, str]
) -> None:
    company = client.get("/map/company", headers=user_headers).json()["company"]
    assert company["title"] == "Company overview"
    assert company["summary"]
    assert 0 < len(company["issues"]) <= 10
    assert all(issue["sources"] for issue in company["issues"])
    cards = client.get("/communities?level=1", headers=user_headers).json()[
        "communities"
    ]
    licensing = [
        card for card in cards if card["id"] == seeded["licensing_community_id"]
    ]
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
    chips = {
        source["id"] for finding in body["findings"] for source in finding["sources"]
    }
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
    body = client.get(
        f"/sources/{seeded['pdf_id']}/chunks", headers=user_headers
    ).json()
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
    assert seeded["licensing_community_id"] in {
        item["id"] for item in body["communities"]
    }


def test_unknown_ids_are_404(client: TestClient, user_headers: dict[str, str]) -> None:
    for path in (
        "/communities/not-a-uuid",
        "/entities/00000000-0000-4000-8000-000000000000",
        "/sources/00000000-0000-4000-8000-000000000000/chunks",
        "/map/functions/not-a-function",
    ):
        assert client.get(path, headers=user_headers).status_code == 404


def test_reads_need_the_token(client: TestClient) -> None:
    assert client.get("/map/company").status_code == 401
    assert client.get("/map/functions").status_code == 401
    assert client.get("/map/functions/licensing").status_code == 401


def test_function_cards_carry_counts_and_top_issues(
    seeded_with_issues: dict[str, Any], client: TestClient, user_headers: dict[str, str]
) -> None:
    """Repair C5: the map page's centre column is one card per function with
    counts and the open issues known today (D3 conflicts and gaps — no F6
    coverage score yet)."""
    seeded = seeded_with_issues
    body = client.get("/map/functions", headers=user_headers).json()
    cards = [card for card in body["functions"] if card["key"] == "licensing"]
    assert len(cards) == 1
    card = cards[0]
    assert card["name"] == LICENSING_TITLE
    # C3: the level-1 report row id is the function id, so the card links to
    # the same stable id the community page uses.
    assert card["report_id"] == seeded["licensing_function_id"]
    assert card["report_id"] == seeded["licensing_community_id"]
    assert card["summary"]
    assert card["source_count"] == 3  # transcript, pdf and flowchart all assigned
    assert card["process_count"] >= 1
    assert card["person_count"] >= 1  # Jessica
    assert card["entity_count"] >= card["process_count"] + card["person_count"]
    assert card["open_contradictions"] == 1
    assert card["open_gaps"] == 1
    assert any(
        issue["kind"] == "contradiction" and issue["text"] == CONTRADICTION_SUMMARY
        for issue in card["top_issues"]
    )
    assert any(
        issue["kind"] == "gap" and issue["text"] == INTERVIEW_OPEN
        for issue in card["top_issues"]
    )


def test_function_detail_composes_the_function_page(
    seeded_with_issues: dict[str, Any], client: TestClient, user_headers: dict[str, str]
) -> None:
    """Repair C5: one function's page — its report, its processes linking to
    their sources (E5 flow pages are not landed), its sub-topics, its people,
    its open gaps and the open conflicts touching it."""
    seeded = seeded_with_issues
    body = client.get("/map/functions/licensing", headers=user_headers).json()
    assert body["function"]["key"] == "licensing"
    assert body["function"]["id"] == seeded["licensing_function_id"]
    assert body["report"]["title"] == LICENSING_TITLE
    assert body["report"]["findings"]
    assert body["report"]["summary"]
    processes = {item["name"]: item for item in body["processes"]}
    assert seeded["licensing_process_name"] in processes
    process = processes[seeded["licensing_process_name"]]
    assert seeded["transcript_id"] in {source["id"] for source in process["sources"]}
    assert any(item["id"] == seeded["jessica_id"] for item in body["people"])
    assert INTERVIEW_OPEN in {gap["question"] for gap in body["gaps"]}
    conflicts = [
        row for row in body["contradictions"] if row["summary"] == CONTRADICTION_SUMMARY
    ]
    assert conflicts and conflicts[0]["status"] == "open"
    assert {conflicts[0]["source_a_title"], conflicts[0]["source_b_title"]} == {
        "Ownership memo",
        "Team standup notes",
    }
    # The id form resolves too, and a retired-looking ref is a 404.
    by_id = client.get(
        f"/map/functions/{seeded['licensing_function_id']}", headers=user_headers
    )
    assert by_id.status_code == 200
    assert by_id.json()["function"]["key"] == "licensing"


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
