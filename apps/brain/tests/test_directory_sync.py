"""DesignFlow directory sync rules (DECISIONS.md
D-dflow-directory-source-of-truth).

The shared ``api.oracle_user_directory`` view does not exist in the test
database, so rows are injected into ``apply_directory`` directly and applied to
the stand-in ``public.employees`` / ``public.employee_directory_roles`` tables.
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.config import Settings, get_settings
from brain.directory_sync import (
    apply_directory,
    maybe_queue_directory_sync,
    run_directory_sync,
)


@pytest.fixture(autouse=True)
def _clean_directory_rows(db: Any) -> None:
    """Drop rows this module creates — the test database persists across runs."""
    pattern = "%@example.invalid"
    db.execute(
        "DELETE FROM public.employee_directory_roles WHERE employee_id IN "
        "(SELECT id FROM public.employees WHERE email LIKE %s)",
        (pattern,),
    )
    db.execute(
        "DELETE FROM cmap.employee_flags WHERE employee_id IN "
        "(SELECT id FROM public.employees WHERE email LIKE %s)",
        (pattern,),
    )
    db.execute("DELETE FROM public.employees WHERE email LIKE %s", (pattern,))
    db.commit()


def _row(email: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "user_id": 7,
        "email": email,
        "name": "Ada",
        "lastname": "Lovelace",
        "status": "active",
        "level": None,
        "office_location": None,
        "roles": [],
    }
    row.update(overrides)
    return row


def _employee(db: Any, email: str, **fields: Any) -> str:
    """Insert a stand-in employee row and return its id."""
    name = fields.pop("name", "Existing Person")
    role = fields.pop("role", "Boss")
    is_admin = fields.pop("is_admin", False)
    disabled_at = fields.pop("disabled_at", None)
    assert not fields, f"unexpected fields: {sorted(fields)}"
    row = db.execute(
        "INSERT INTO public.employees (id, email, name, role, is_admin, disabled_at) "
        "VALUES (gen_random_uuid(), %s, %s, %s, %s, %s) RETURNING id::text",
        (email, name, role, is_admin, disabled_at),
    ).fetchone()
    db.commit()
    return str(row[0])


def _roles(db: Any, employee_id: str) -> list[str]:
    return sorted(
        str(r[0])
        for r in db.execute(
            "SELECT role_name FROM public.employee_directory_roles WHERE employee_id = %s",
            (employee_id,),
        ).fetchall()
    )


def test_creates_employee_with_display_name_and_roles(db: Any) -> None:
    apply_directory(db, [_row("ada@example.invalid", roles=["Designer", "Admin"])])
    db.commit()
    row = db.execute(
        "SELECT name, role, disabled_at FROM public.employees WHERE email = %s",
        ("ada@example.invalid",),
    ).fetchone()
    assert row == ("Ada Lovelace", "", None)
    employee_id = str(
        db.execute(
            "SELECT id::text FROM public.employees WHERE email = %s",
            ("ada@example.invalid",),
        ).fetchone()[0]
    )
    assert _roles(db, employee_id) == ["Admin", "Designer"]


def test_skips_rows_with_empty_email(db: Any) -> None:
    counts = apply_directory(
        db, [_row("  "), _row("", name="No Email"), _row("ok@example.invalid")]
    )
    db.commit()
    assert counts == {"created": 1, "updated": 0, "skipped": 2}
    assert (
        db.execute(
            "SELECT name FROM public.employees WHERE email = %s",
            ("ok@example.invalid",),
        ).fetchone()[0]
        == "Ada Lovelace"
    )
    assert (
        db.execute(
            "SELECT count(*) FROM public.employees WHERE btrim(email) = ''"
        ).fetchone()[0]
        == 0
    )


def test_display_name_falls_back_to_existing_name(db: Any) -> None:
    employee_id = _employee(db, "keep@example.invalid", name="Keep Me")
    apply_directory(db, [_row("keep@example.invalid", name="", lastname="")])
    db.commit()
    name = db.execute(
        "SELECT name FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()[0]
    assert name == "Keep Me"


def test_display_name_falls_back_to_email_local_part(db: Any) -> None:
    apply_directory(db, [_row("local@example.invalid", name="", lastname="")])
    db.commit()
    name = db.execute(
        "SELECT name FROM public.employees WHERE email = %s",
        ("local@example.invalid",),
    ).fetchone()[0]
    assert name == "local"
    employee_id = _employee(db, "blank@example.invalid", name="")
    apply_directory(db, [_row("blank@example.invalid", name="", lastname="")])
    db.commit()
    name = db.execute(
        "SELECT name FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()[0]
    assert name == "blank"


def test_update_renames_when_directory_has_a_name(db: Any) -> None:
    employee_id = _employee(db, "rename@example.invalid", name="Old Name")
    apply_directory(
        db,
        [_row("  Rename@Example.Invalid  ", name="New", lastname="Name", roles=["PM"])],
    )
    db.commit()
    row = db.execute(
        "SELECT name FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()
    assert row == ("New Name",)
    assert _roles(db, employee_id) == ["PM"]


def test_active_status_clears_disabled_at(db: Any) -> None:
    employee_id = _employee(db, "active@example.invalid", disabled_at="2026-01-01T00:00:00")
    apply_directory(db, [_row("active@example.invalid", status="  ACTIVE ")])
    db.commit()
    disabled = db.execute(
        "SELECT disabled_at FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()[0]
    assert disabled is None


def test_inactive_status_sets_disabled_at_only_once(db: Any) -> None:
    employee_id = _employee(db, "gone@example.invalid")
    apply_directory(db, [_row("gone@example.invalid", status="Former")])
    db.commit()
    first = db.execute(
        "SELECT disabled_at FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()[0]
    assert first is not None
    apply_directory(db, [_row("gone@example.invalid", status="Terminated")])
    db.commit()
    second = db.execute(
        "SELECT disabled_at FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()[0]
    assert second == first


def test_new_employee_with_inactive_status_starts_disabled(db: Any) -> None:
    apply_directory(db, [_row("offboarded@example.invalid", status="inactive")])
    db.commit()
    disabled = db.execute(
        "SELECT disabled_at FROM public.employees WHERE email = %s",
        ("offboarded@example.invalid",),
    ).fetchone()[0]
    assert disabled is not None


def test_empty_status_leaves_disabled_at_alone(db: Any) -> None:
    employee_id = _employee(db, "quiet@example.invalid", disabled_at="2026-01-01T00:00:00")
    apply_directory(db, [_row("quiet@example.invalid", status=None)])
    db.commit()
    disabled = db.execute(
        "SELECT disabled_at FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()[0]
    assert disabled is not None
    apply_directory(db, [_row("quiet@example.invalid", status="")])
    db.commit()
    still = db.execute(
        "SELECT disabled_at FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()[0]
    assert still == disabled


def test_roles_are_replaced_not_appended(db: Any) -> None:
    employee_id = _employee(db, "roles@example.invalid")
    db.execute(
        "INSERT INTO public.employee_directory_roles (employee_id, role_name) "
        "VALUES (%s, 'Stale Role')",
        (employee_id,),
    )
    db.commit()
    apply_directory(
        db,
        [
            _row(
                "roles@example.invalid",
                roles=["Designer", "", "  ", "Designer", "Admin"],
            )
        ],
    )
    db.commit()
    assert _roles(db, employee_id) == ["Admin", "Designer"]
    apply_directory(db, [_row("roles@example.invalid", roles=None)])
    db.commit()
    assert _roles(db, employee_id) == []


def test_never_deletes_employees_missing_from_the_directory(db: Any) -> None:
    employee_id = _employee(db, "absent@example.invalid")
    apply_directory(db, [_row("someone.else@example.invalid")])
    db.commit()
    row = db.execute(
        "SELECT id::text FROM public.employees WHERE id = %s", (employee_id,)
    ).fetchone()
    assert row is not None


def test_never_touches_oracle_only_fields(db: Any) -> None:
    employee_id = _employee(db, "untouched@example.invalid", role="Boss", is_admin=True)
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department, job_title, "
        "profile_answer, profile_asked_at) VALUES (%s, 'Design', 'Designer', "
        "'Designer in Design', now())",
        (employee_id,),
    )
    db.commit()
    apply_directory(
        db,
        [_row("untouched@example.invalid", status="Former", roles=["Designer", "Admin"])],
    )
    db.commit()
    row = db.execute(
        "SELECT name, role, is_admin, disabled_at FROM public.employees WHERE id = %s",
        (employee_id,),
    ).fetchone()
    assert row[1:3] == ("Boss", True)
    assert row[3] is not None
    flags = db.execute(
        "SELECT department, job_title, profile_answer FROM cmap.employee_flags "
        "WHERE employee_id = %s",
        (employee_id,),
    ).fetchone()
    assert flags == ("Design", "Designer", "Designer in Design")


def test_sync_is_a_noop_without_the_flag_or_url() -> None:
    disabled = run_directory_sync(Settings(dflow_directory_sync_enabled=False))
    assert disabled["enabled"] is False
    no_url = run_directory_sync(
        Settings(dflow_directory_sync_enabled=True, dflow_directory_database_url=None)
    )
    assert no_url["enabled"] is False


def test_maybe_queue_dedupes_on_the_last_finished_job(db: Any) -> None:
    cfg = Settings(
        dflow_directory_sync_enabled=True,
        dflow_directory_database_url="postgresql://unused.invalid/db",
    )
    assert maybe_queue_directory_sync(cfg) is True
    assert maybe_queue_directory_sync(cfg) is False
    db.execute(
        "UPDATE cmap.job SET state = 'done', finished_at = now() WHERE kind = 'directory_sync'"
    )
    db.commit()
    assert maybe_queue_directory_sync(cfg) is False
    db.execute(
        "UPDATE cmap.job SET finished_at = now() - interval '16 minutes' "
        "WHERE kind = 'directory_sync'"
    )
    db.commit()
    assert maybe_queue_directory_sync(cfg) is True


def test_maybe_queue_stays_quiet_when_unconfigured(db: Any) -> None:
    cfg = Settings()
    assert cfg.dflow_directory_sync_enabled is False
    assert maybe_queue_directory_sync(cfg) is False
    assert db.execute("SELECT count(*) FROM cmap.job").fetchone()[0] == 0
    assert get_settings().dflow_directory_database_url is None
