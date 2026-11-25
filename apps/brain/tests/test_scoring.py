"""Tests for source authority, ideal-vs-practice scoring, retrieval and APIs."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from brain.answer.answer import _assemble_context, _select_chunks
from brain.config import get_settings
from brain.embed import vector_literal
from brain.graph.communities import edge_rank
from brain.graph.project import _load_edges
from brain.scoring import (
    AUTHORITATIVE_MULTIPLIER,
    RECENCY_FLOOR,
    STANDARD_MULTIPLIER,
    UNKNOWN_DATE_FACTOR,
    authority_multiplier,
    effective_stance,
    format_source_tag,
    recency_multiplier,
    source_weight,
)


def test_scoring_multipliers_stances_and_tags() -> None:
    today = date(2026, 11, 25)
    assert authority_multiplier("authoritative") == AUTHORITATIVE_MULTIPLIER
    assert authority_multiplier("standard") == STANDARD_MULTIPLIER
    assert authority_multiplier(None) == STANDARD_MULTIPLIER

    assert recency_multiplier(today, today=today) == 1.0
    assert abs(recency_multiplier(today - timedelta(days=180), today=today) - 0.5) < 1e-6
    assert recency_multiplier(today - timedelta(days=2000), today=today) == RECENCY_FLOOR
    assert recency_multiplier(None, today=today) == UNKNOWN_DATE_FACTOR

    assert effective_stance("report", "ideal_policy") == "policy"
    assert effective_stance("practice", "ideal_policy") == "policy"
    assert effective_stance("inference", "ideal_policy") == "inference"
    assert effective_stance("practice", "observed_practice") == "practice"

    auth_w = source_weight("authoritative", today, confidence=1.0, today=today)
    std_w = source_weight("standard", today, confidence=1.0, today=today)
    assert auth_w == AUTHORITATIVE_MULTIPLIER * 1.0
    assert std_w == STANDARD_MULTIPLIER * 1.0

    tag = format_source_tag("ideal_policy", "authoritative", today)
    assert tag == "[IDEAL POLICY — AUTHORITATIVE — 2026-11-25]"
    assert format_source_tag("observed_practice", "standard", None) == "[OBSERVED PRACTICE]"


def test_edge_rank_prefers_score_over_raw_count() -> None:
    authoritative_edge = {"rel_type": "HANDS_OFF_TO", "weight": 1, "score": 8.0}
    email_edge = {"rel_type": "HANDS_OFF_TO", "weight": 4, "score": 3.0}
    assert edge_rank(authoritative_edge) > edge_rank(email_edge)

    assert edge_rank({"rel_type": "OWNS", "weight": 3}) == (3.0, 1.0)
    assert edge_rank({"rel_type": "HANDS_OFF_TO", "weight": 3}) == (6.0, 2.0)


def test_assemble_context_reserves_budget_for_evidence() -> None:
    heavy = ["word " * 120 for _ in range(12)]
    quotes = ['{"chunk_id":"c1","quote":"Exact ideal quote"}']
    passages = ["[IDEAL POLICY — AUTHORITATIVE] Jessica explained PPS happens before bulk."]
    rendered, _total, _kept = _assemble_context(
        [
            ("function_reports", heavy, "\n".join),
            ("company", [], "\n".join),
            ("flow", heavy, "\n".join),
            ("graph", [], "\n".join),
            ("quotes", quotes, lambda items: "[" + ",".join(items) + "]"),
            ("passages", passages, "\n\n".join),
        ],
        ceiling=400,
        group_cap=({"function_reports", "company", "flow", "graph"}, int(400 * 0.65)),
    )
    assert "Exact ideal quote" in rendered["quotes"]
    assert "Jessica explained PPS happens before bulk." in rendered["passages"]


def test_transcript_authority_patch_and_correction_defaults(
    client: TestClient,
    db: Any,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
) -> None:
    resp = client.post(
        "/sources/transcript",
        headers=admin_headers,
        json={
            "title": "Jessica Licensing Process",
            "text": "Jessica: Design sends artwork to Licensing before PPS.",
            "source_role": "ideal_policy",
            "authority_tier": "authoritative",
            "effective_date": "2026-11-24",
        },
    )
    assert resp.status_code == 200
    src = resp.json()
    assert src["source_role"] == "ideal_policy"
    assert src["authority_tier"] == "authoritative"

    bad = client.post(
        "/sources/transcript",
        headers=admin_headers,
        json={"text": "hello", "source_role": "bogus"},
    )
    assert bad.status_code == 400

    # Standard source promoted via PATCH /sources/{id}/authority
    plain_resp = client.post(
        "/sources/transcript",
        headers=admin_headers,
        json={"title": "Routine Teams chat", "text": "Albert: Check PO status."},
    )
    assert plain_resp.status_code == 200
    plain_id = plain_resp.json()["id"]
    assert plain_resp.json()["source_role"] == "observed_practice"
    assert plain_resp.json()["authority_tier"] == "standard"

    chunk_id = str(uuid4())
    e1, e2 = str(uuid4()), str(uuid4())
    m1, m2 = str(uuid4()), str(uuid4())
    db.execute(
        "INSERT INTO cmap.chunk (id, source_id, ordinal, locator, text, token_count) "
        "VALUES (%s, %s, 1, '{}', 'Albert: Check PO status.', 5)",
        (chunk_id, plain_id),
    )
    for eid, name in ((e1, "Albert"), (e2, "Licensing")):
        db.execute(
            "INSERT INTO cmap.entity (id, entity_type, canonical_name) VALUES (%s, 'Person', %s)",
            (eid, name),
        )
    db.execute(
        "INSERT INTO cmap.mention (id, chunk_id, entity_type, surface_name, normalized_name, quote, entity_id) "
        "VALUES (%s, %s, 'Person', 'Albert', 'albert', 'Albert: Check PO status.', %s), "
        "(%s, %s, 'Artifact', 'PO status', 'po status', 'Albert: Check PO status.', %s)",
        (m1, chunk_id, e1, m2, chunk_id, e2),
    )
    rel_id = str(uuid4())
    db.execute(
        "INSERT INTO cmap.relation (id, chunk_id, from_mention_id, to_mention_id, rel_type, description, stance, confidence, quote) "
        "VALUES (%s, %s, %s, %s, 'OWNS', 'checks PO status', 'report', 0.9, 'Albert: Check PO status.')",
        (rel_id, chunk_id, m1, m2),
    )
    db.commit()

    # Non-admin blocked
    assert (
        client.patch(
            f"/sources/{plain_id}/authority",
            headers=user_headers,
            json={"source_role": "ideal_policy", "authority_tier": "authoritative"},
        ).status_code
        == 403
    )
    patch = client.patch(
        f"/sources/{plain_id}/authority",
        headers=admin_headers,
        json={"source_role": "ideal_policy", "authority_tier": "authoritative"},
    )
    assert patch.status_code == 200
    body = patch.json()
    assert body["source"]["source_role"] == "ideal_policy"
    assert body["source"]["authority_tier"] == "authoritative"
    assert body["relations_promoted"] == 1
    assert body["project_queued"] is True

    stance = db.execute("SELECT stance FROM cmap.relation WHERE id = %s", (rel_id,)).fetchone()[0]
    assert stance == "policy"

    # Admin-applied corrections automatically land as authoritative ideal_policy
    client.put(
        "/corrections/permissions/00000000-0000-4000-8000-0000000000b1",
        headers=admin_headers,
        json={"can_correct": True},
    )
    note = client.post(
        "/corrections/notes",
        headers=user_headers,
        json={"what_is_wrong": "Old step", "correction_text": "Design signs off first."},
    ).json()["note"]
    applied = client.post(
        f"/corrections/notes/{note['id']}/apply",
        headers=admin_headers,
        json={},
    ).json()
    src_row = db.execute(
        "SELECT source_role, authority_tier FROM cmap.source WHERE id = %s::uuid",
        (applied["source_id"],),
    ).fetchone()
    assert src_row == ("ideal_policy", "authoritative")


def test_project_load_edges_and_select_chunks_authority(db: Any) -> None:
    auth_src = str(uuid4())
    email_src = str(uuid4())
    for sid, title, role, tier in (
        (auth_src, "Jessica Ideal", "ideal_policy", "authoritative"),
        (email_src, "Daily Email", "observed_practice", "standard"),
    ):
        db.execute(
            "INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes, source_role, authority_tier, effective_date) "
            "VALUES (%s, 'transcript', %s, %s, %s, 10, %s, %s, CURRENT_DATE)",
            (sid, title, f"cmap/{sid}.txt", sid, role, tier),
        )
    e1, e2 = str(uuid4()), str(uuid4())
    db.execute(
        "INSERT INTO cmap.entity (id, entity_type, canonical_name) VALUES (%s, 'Role', 'Designer'), (%s, 'Role', 'Licensing')",
        (e1, e2),
    )
    dims = get_settings().brain_embed_dims
    vec = vector_literal([0.1] * dims)
    c_auth, c_email = str(uuid4()), str(uuid4())
    db.execute(
        "INSERT INTO cmap.chunk (id, source_id, ordinal, locator, text, token_count, embedding) VALUES "
        "(%s, %s, 1, '{}', 'Ideal workflow text', 5, %s::vector), "
        "(%s, %s, 1, '{}', 'Observed email workaround', 5, %s::vector)",
        (c_auth, auth_src, vec, c_email, email_src, vec),
    )
    m_a1, m_a2, m_e1, m_e2 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    db.execute(
        "INSERT INTO cmap.mention (id, chunk_id, entity_type, surface_name, normalized_name, quote, entity_id) VALUES "
        "(%s, %s, 'Role', 'Designer', 'designer', 'Ideal workflow text', %s), "
        "(%s, %s, 'Role', 'Licensing', 'licensing', 'Ideal workflow text', %s), "
        "(%s, %s, 'Role', 'Designer', 'designer', 'Observed email workaround', %s), "
        "(%s, %s, 'Role', 'Licensing', 'licensing', 'Observed email workaround', %s)",
        (m_a1, c_auth, e1, m_a2, c_auth, e2, m_e1, c_email, e1, m_e2, c_email, e2),
    )
    db.execute(
        "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, rel_type, description, stance, confidence, quote) VALUES "
        "(%s, %s, %s, 'HANDS_OFF_TO', 'Ideal licensing handoff', 'report', 0.9, 'Ideal workflow text'), "
        "(%s, %s, %s, 'HANDS_OFF_TO', 'Email workaround handoff', 'practice', 0.9, 'Observed email workaround')",
        (c_auth, m_a1, m_a2, c_email, m_e1, m_e2),
    )
    db.commit()

    edges = _load_edges(db)
    assert len(edges) == 1
    edge = edges[0]
    assert edge["weight"] == 2
    assert edge["authority_sources"] == 1
    assert set(edge["source_roles"]) == {"ideal_policy", "observed_practice"}
    assert edge["score"] > 7.0
    assert edge["descriptions"][0] == "Ideal licensing handoff"

    chunks = _select_chunks([0.1] * dims, [])
    assert len(chunks) == 2
    assert chunks[0]["id"] == c_auth
    assert chunks[0]["authority_tier"] == "authoritative"
    assert chunks[0]["source_role"] == "ideal_policy"
    assert chunks[0]["text"] == "Ideal workflow text"
