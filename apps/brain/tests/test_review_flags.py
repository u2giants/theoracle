"""Admin review flags for the Map review gate (issue #255).

The endpoints are exercised the way the ``/map`` surfaces and the review page
call them through the proxy: create with a note, list open flags, resolve.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _seed_items(db: Any) -> dict[str, str]:
    """One entity, one community and a relation target pair to flag."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name) "
            "VALUES ('Person', 'Jessica Vale'), ('Role', 'Licensing Manager') "
            "RETURNING id"
        )
        entity_id, other_id = (str(row[0]) for row in cur.fetchall())
        cur.execute(
            "INSERT INTO cmap.community (level, title, entity_ids, graph_version) "
            "VALUES (1, 'Licensing approval', %s::uuid[], 1) RETURNING id",
            ([entity_id, other_id],),
        )
        community_id = str(cur.fetchone()[0])
        db.commit()
    return {
        "entity_id": entity_id,
        "other_id": other_id,
        "community_id": community_id,
        "relation_id": f"{entity_id}:{other_id}:PERFORMS",
    }


def test_flags_need_the_token(client: TestClient) -> None:
    assert client.get("/flags").status_code == 401
    assert client.post("/flags", json={"item_type": "entity"}).status_code == 401


def test_flags_are_admin_only(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    assert client.get("/flags", headers=user_headers).status_code == 403
    assert (
        client.post(
            "/flags",
            headers=user_headers,
            json={"item_type": "entity", "item_id": "x"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/flags/00000000-0000-4000-8000-000000000000/resolve",
            headers=user_headers,
        ).status_code
        == 403
    )


def test_flag_entity_relation_and_community(
    client: TestClient, admin_headers: dict[str, str], db: Any
) -> None:
    items = _seed_items(db)
    created = []
    for item_type, key, note in (
        ("entity", items["entity_id"], "This person is not on the licensing team"),
        ("relation", items["relation_id"], "She does not perform this step"),
        ("community", items["community_id"], "This area is misgrouped"),
    ):
        response = client.post(
            "/flags",
            headers=admin_headers,
            json={"item_type": item_type, "item_id": key, "note": note},
        )
        assert response.status_code == 200
        flag = response.json()["flag"]
        assert flag["item_type"] == item_type
        assert flag["note"] == note
        assert flag["resolved_at"] is None
        created.append(flag)

    body = client.get("/flags", headers=admin_headers).json()["flags"]
    assert len(body) == 3
    labels = {flag["item_type"]: flag["label"] for flag in body}
    assert labels["entity"] == "Jessica Vale"
    assert labels["community"] == "Licensing approval"
    assert "PERFORMS" in labels["relation"]
    assert "Jessica Vale" in labels["relation"]
    assert "Licensing Manager" in labels["relation"]

    only_entity = client.get(
        "/flags",
        headers=admin_headers,
        params={"item_type": "entity", "item_id": items["entity_id"]},
    ).json()["flags"]
    assert [flag["id"] for flag in only_entity] == [created[0]["id"]]


def test_note_is_optional_and_re_flag_refreshes_it(
    client: TestClient, admin_headers: dict[str, str], db: Any
) -> None:
    items = _seed_items(db)
    first = client.post(
        "/flags",
        headers=admin_headers,
        json={"item_type": "entity", "item_id": items["entity_id"]},
    ).json()["flag"]
    assert first["note"] is None
    second = client.post(
        "/flags",
        headers=admin_headers,
        json={
            "item_type": "entity",
            "item_id": items["entity_id"],
            "note": "Wrong department",
        },
    ).json()["flag"]
    assert second["id"] == first["id"]
    assert second["note"] == "Wrong department"
    body = client.get("/flags", headers=admin_headers).json()["flags"]
    assert len(body) == 1


def test_resolve_flag(
    client: TestClient, admin_headers: dict[str, str], db: Any
) -> None:
    items = _seed_items(db)
    flag = client.post(
        "/flags",
        headers=admin_headers,
        json={"item_type": "relation", "item_id": items["relation_id"], "note": "No"},
    ).json()["flag"]
    resolved = client.post(
        f"/flags/{flag['id']}/resolve", headers=admin_headers
    ).json()["flag"]
    assert resolved["resolved_at"] is not None
    assert client.get("/flags", headers=admin_headers).json()["flags"] == []
    history = client.get(
        "/flags", headers=admin_headers, params={"include_resolved": True}
    ).json()["flags"]
    assert [item["id"] for item in history] == [flag["id"]]

    again = client.post(
        f"/flags/{flag['id']}/resolve", headers=admin_headers
    ).json()["flag"]
    assert again["resolved_at"] == resolved["resolved_at"]

    missing = client.post(
        "/flags/00000000-0000-4000-8000-000000000000/resolve", headers=admin_headers
    )
    assert missing.status_code == 404


def test_bad_item_type_or_id_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    for payload in (
        {"item_type": "source", "item_id": "x"},
        {"item_type": "entity", "item_id": "not-a-uuid"},
        {"item_type": "relation", "item_id": "missing-colons"},
        {"item_type": "relation", "item_id": "not-a-uuid:not-a-uuid:PERFORMS"},
    ):
        response = client.post("/flags", headers=admin_headers, json=payload)
        assert response.status_code == 400, payload
    assert (
        client.get("/flags", headers=admin_headers, params={"item_type": "source"}).status_code
        == 400
    )
