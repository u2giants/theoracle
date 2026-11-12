"""Repair plan C1 gate: the curated business-function list (``cmap.function``).

The seed lands the 13 owner-proposal functions, clustered from Department
evidence (see ``sql/022_functions.sql``); the admin API renames, adds, merges
and retires them and nothing else — no approval queues, no permissions beyond
login + admin. Re-running the migration never duplicates or clobbers rows.
"""

from __future__ import annotations

from typing import Any

import pytest

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
