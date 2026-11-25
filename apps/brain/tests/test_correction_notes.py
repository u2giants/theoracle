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
