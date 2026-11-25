"""Tests for employee correction notes and per-employee submission permissions."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

ADMIN_ID = "00000000-0000-4000-8000-0000000000a1"
EMPLOYEE_ID = "00000000-0000-4000-8000-0000000000b1"
SECOND_EMPLOYEE_ID = "00000000-0000-4000-8000-000000000e01"
SECOND_AUTH_ID = "00000000-0000-4000-8000-000000000e02"
SECOND_IDENTITY_ID = "00000000-0000-4000-8000-000000000e03"
SECOND_HEADERS = {"x-brain-token": "brain-test-token", "x-user-id": SECOND_AUTH_ID}


def _seed_second_employee(db: Any) -> None:
    db.execute(
        "INSERT INTO public.employees (id, email, name, role, is_admin) "
        "VALUES (%s, 'second-corr@test.invalid', 'Second Employee', 'Licensing', false) "
        "ON CONFLICT (id) DO NOTHING",
        (SECOND_EMPLOYEE_ID,),
    )
    db.execute(
        "INSERT INTO public.employee_identities (id, employee_id, auth_user_id) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (id) DO NOTHING",
        (SECOND_IDENTITY_ID, SECOND_EMPLOYEE_ID, SECOND_AUTH_ID),
    )
    db.commit()


def test_unauthorized_employee_is_blocked_from_correction_notes(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    access = client.get("/corrections/access", headers=user_headers)
    assert access.status_code == 200
    assert access.json() == {"can_correct": False, "is_admin": False}

    assert client.get("/corrections/notes", headers=user_headers).status_code == 403
    assert (
        client.post(
            "/corrections/notes",
            headers=user_headers,
            json={"what_is_wrong": "Bad", "correction_text": "Fix"},
        ).status_code
        == 403
    )
    assert client.get("/corrections/permissions", headers=user_headers).status_code == 403
    assert (
        client.put(
            f"/corrections/permissions/{EMPLOYEE_ID}",
            headers=user_headers,
            json={"can_correct": True},
        ).status_code
        == 403
    )


def test_admin_grants_access_reviewer_submits_and_sees_only_own_notes(
    client: TestClient,
    db: Any,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
) -> None:
    _seed_second_employee(db)
    fn_id = str(uuid4())
    db.execute(
        "INSERT INTO cmap.function (id, key, name, description, sort, active) "
        "VALUES (%s, 'licensing', 'Licensing', 'Licensing area', 1, true)",
        (fn_id,),
    )
    db.commit()

    # Grant permission to both non-admin employees.
    assert (
        client.put(
            f"/corrections/permissions/{EMPLOYEE_ID}",
            headers=admin_headers,
            json={"can_correct": True},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/corrections/permissions/{SECOND_EMPLOYEE_ID}",
            headers=admin_headers,
            json={"can_correct": True},
        ).status_code
        == 200
    )

    access = client.get("/corrections/access", headers=user_headers)
    assert access.status_code == 200
    assert access.json() == {"can_correct": True, "is_admin": False}

    # Blank validation returns 400.
    bad = client.post(
        "/corrections/notes",
        headers=user_headers,
        json={"what_is_wrong": "   ", "correction_text": "Real text"},
    )
    assert bad.status_code == 400

    # Both employees create notes.
    r1 = client.post(
        "/corrections/notes",
        headers=user_headers,
        json={
            "function_id": fn_id,
            "page_ref": "/map/function/licensing",
            "what_is_wrong": "Wrong owner for factory audit",
            "correction_text": "Compliance handles factory audit approvals.",
        },
    )
    assert r1.status_code == 200
    note1 = r1.json()["note"]
    assert note1["employee_id"] == EMPLOYEE_ID
    assert note1["employee_name"] == "Test Employee"
    assert note1["function_name"] == "Licensing"
    assert note1["status"] == "open"

    r2 = client.post(
        "/corrections/notes",
        headers=SECOND_HEADERS,
        json={
            "what_is_wrong": "Second note",
            "correction_text": "Second correction detail.",
        },
    )
    assert r2.status_code == 200
    note2 = r2.json()["note"]

    # Each non-admin sees only their own note; admin sees both.
    list1 = client.get("/corrections/notes", headers=user_headers).json()["notes"]
    assert [n["id"] for n in list1] == [note1["id"]]

    list_admin = client.get("/corrections/notes", headers=admin_headers).json()["notes"]
    assert {n["id"] for n in list_admin} >= {note1["id"], note2["id"]}

    # Non-admin still cannot apply or dismiss.
    assert (
        client.post(
            f"/corrections/notes/{note1['id']}/apply",
            headers=user_headers,
            json={},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/corrections/notes/{note1['id']}/dismiss",
            headers=user_headers,
            json={},
        ).status_code
        == 403
    )


def test_admin_apply_creates_full_text_source_and_dismiss_marks_dismissed(
    client: TestClient,
    db: Any,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
) -> None:
    client.put(
        f"/corrections/permissions/{EMPLOYEE_ID}",
        headers=admin_headers,
        json={"can_correct": True},
    )
    n_apply = client.post(
        "/corrections/notes",
        headers=user_headers,
        json={
            "what_is_wrong": "Sample cutoff wrong",
            "correction_text": "PPS approval always precedes factory bulk run.",
        },
    ).json()["note"]
    n_dismiss = client.post(
        "/corrections/notes",
        headers=user_headers,
        json={
            "what_is_wrong": "Duplicate typo note",
            "correction_text": "Already covered elsewhere.",
        },
    ).json()["note"]

    applied = client.post(
        f"/corrections/notes/{n_apply['id']}/apply",
        headers=admin_headers,
        json={"review_note": "Verified with Licensing"},
    )
    assert applied.status_code == 200
    body = applied.json()
    source_id = body["source_id"]
    assert source_id
    assert body["note"]["status"] == "applied"
    assert body["note"]["review_note"] == "Verified with Licensing"

    src_row = db.execute(
        "SELECT kind, ingest_tier, map_eligible, title FROM cmap.source WHERE id = %s::uuid",
        (source_id,),
    ).fetchone()
    assert src_row[0] == "text"
    assert src_row[1] == "full"
    assert src_row[2] is True
    assert "Sample cutoff wrong" in src_row[3]

    job_row = db.execute(
        "SELECT kind, state FROM cmap.job WHERE payload->>'source_id' = %s",
        (source_id,),
    ).fetchone()
    assert job_row == ("read_source", "queued")

    dismissed = client.post(
        f"/corrections/notes/{n_dismiss['id']}/dismiss",
        headers=admin_headers,
        json={"review_note": "Duplicate"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["note"]["status"] == "dismissed"
    assert dismissed.json()["note"]["source_id"] is None


def test_correction_note_queues_ai_triage_and_supports_practice_apply(
    client: TestClient,
    db: Any,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
    monkeypatch: Any,
) -> None:
    from brain import correction_triage

    client.put(
        f"/corrections/permissions/{EMPLOYEE_ID}",
        headers=admin_headers,
        json={"can_correct": True},
    )
    fn_id = str(uuid4())
    db.execute(
        "INSERT INTO cmap.function (id, key, name, description, sort, active) "
        "VALUES (%s, 'licensing', 'Licensing', 'Licensing area', 1, true)",
        (fn_id,),
    )
    db.commit()

    created = client.post(
        "/corrections/notes",
        headers=user_headers,
        json={
            "function_id": fn_id,
            "what_is_wrong": "Factory audits are assigned to Licensing",
            "correction_text": "Day-to-day teams sometimes email Licensing, but Compliance handles FAMA.",
        },
    )
    assert created.status_code == 200
    note = created.json()["note"]
    assert note["ai_triaged_at"] is None

    triage_job = db.execute(
        "SELECT kind, state FROM cmap.job WHERE payload->>'note_id' = %s",
        (note["id"],),
    ).fetchone()
    assert triage_job == ("triage_correction_note", "queued")

    def fake_chat_json(payload: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        assert payload["messages"]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"summary": "Licensing is mistakenly listed for factory audits; Compliance owns FAMA.", '
                            '"suggested_action": "apply_observed_practice", '
                            '"reason": "Describes what teams do day-to-day versus Compliance ownership."}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(correction_triage, "post_chat_json_body", fake_chat_json)
    correction_triage.handle_triage_correction_note({"payload": {"note_id": note["id"]}})

    notes_after = client.get("/corrections/notes", headers=admin_headers).json()["notes"]
    matched = next(n for n in notes_after if n["id"] == note["id"])
    assert matched["ai_summary"].startswith("Licensing is mistakenly listed")
    assert matched["ai_suggested_action"] == "apply_observed_practice"
    assert "day-to-day" in matched["ai_reason"]
    assert matched["ai_triaged_at"] is not None

    # Non-admin cannot manually trigger triage; admin can.
    assert (
        client.post(f"/corrections/notes/{note['id']}/triage", headers=user_headers).status_code
        == 403
    )
    retriaged = client.post(f"/corrections/notes/{note['id']}/triage", headers=admin_headers)
    assert retriaged.status_code == 200
    assert retriaged.json()["note"]["ai_suggested_action"] == "apply_observed_practice"

    # Applying as observed_practice saves source_role='observed_practice', authority_tier='authoritative'.
    applied = client.post(
        f"/corrections/notes/{note['id']}/apply",
        headers=admin_headers,
        json={"source_role": "observed_practice"},
    )
    assert applied.status_code == 200
    src_row = db.execute(
        "SELECT source_role, authority_tier FROM cmap.source WHERE id = %s::uuid",
        (applied.json()["source_id"],),
    ).fetchone()
    assert src_row == ("observed_practice", "authoritative")
