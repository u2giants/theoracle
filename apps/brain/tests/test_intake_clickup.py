"""Step 1.2 gate: the ClickUp collector against recorded SYNTHETIC responses.

Every name, id, email and value below is invented. Responses come from an
httpx MockTransport, so no test reaches ClickUp. Only the database test needs
Postgres (the shared conftest applies migrations); the rest run without it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import psycopg
import pytest

from brain.intake import clickup, sizing

SINCE = datetime(2026, 10, 1, tzinfo=UTC)
PEOPLE = [("pm.one@example.test", "Pat Example")]
TEAM = {
    "id": "T1",
    "members": [
        {
            "user": {
                "id": 101,
                "email": "pm.one@example.test",
                "username": "Pat Example",
            }
        },
        {"user": {"id": 202, "email": "other@example.test", "username": "Ola Other"}},
    ],
}


def make_task(tid: str, assignees: tuple[int, ...] = (101,), **extra: Any) -> dict:
    base: dict[str, Any] = {
        "id": tid,
        "name": f"Synthetic task {tid}",
        "list": {"name": "Synthetic list"},
        "status": {"status": "open"},
        "assignees": [{"id": a, "username": f"user {a}"} for a in assignees],
        "watchers": [],
        "creator": {"id": 202, "username": "Ola Other"},
        "due_date": None,
        "dependencies": [],
        "text_content": "",
        "date_created": "1790000000000",
    }
    base.update(extra)
    return base


def make_client(
    pages: dict[int, list[dict]],
    comments: dict[str, list[dict]] | None = None,
    throttle: int = 0,
) -> tuple[httpx.Client, list[httpx.Request]]:
    """Fake ClickUp: one team, task pages, comments; the first ``throttle`` task calls get 429."""
    seen: list[httpx.Request] = []
    state = {"throttle": throttle}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/api/v2/team":
            return httpx.Response(200, json={"teams": [TEAM]})
        if path == "/api/v2/team/T1/task":
            if state["throttle"]:
                state["throttle"] -= 1
                return httpx.Response(429, headers={"Retry-After": "2"}, json={})
            page = int(request.url.params["page"])
            return httpx.Response(200, json={"tasks": pages.get(page, [])})
        if path.startswith("/api/v2/task/") and path.endswith("/comment"):
            tid = path.split("/")[4]
            return httpx.Response(200, json={"comments": (comments or {}).get(tid, [])})
        return httpx.Response(404, json={"err": "unexpected synthetic path"})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


# --- header rendering -------------------------------------------------------


def test_header_fields_copied_exactly_one_per_line():
    task = make_task(
        "t1",
        assignees=(101, 202),
        name="  Spaced  Name ",
        list={"name": "Ünïcode — list"},
        status={"status": "In Progress"},
        due_date="1790086400000",
        dependencies=[{"task_id": "11", "depends_on": "12"}],
    )
    task["assignees"] = [
        {"id": 101, "username": "Pat Example"},
        {"id": 202, "username": "Ola Other"},
    ]
    assert clickup.header_text(task) == (
        "Task name:   Spaced  Name \n"
        "List: Ünïcode — list\n"
        "Status: In Progress\n"
        "Assignee: Pat Example, Ola Other\n"
        "Due date: 1790086400000\n"
        "Dependencies: 11 depends on 12"
    )


def test_header_line_breaks_escaped_so_each_field_stays_one_line():
    task = make_task("t2", name="Line one\nClickUp: spoof\r\nend")
    lines = clickup.header_text(task).split("\n")
    assert len(lines) == 6
    assert lines[0] == "Task name: Line one\\nClickUp: spoof\\r\\nend"


def test_header_missing_fields_render_empty_values():
    task = make_task("t3", assignees=(), list=None, status=None, due_date=None)
    task["name"] = None
    assert clickup.header_text(task).split("\n") == [
        "Task name: ",
        "List: ",
        "Status: ",
        "Assignee: ",
        "Due date: ",
        "Dependencies: ",
    ]


# --- items ------------------------------------------------------------------


def test_items_header_description_and_comments_with_author_and_time():
    task = make_task("t4", text_content="Synthetic description")
    comments = [
        {
            "id": "c1",
            "comment_text": "Synthetic comment",
            "date": "1790000600000",
            "user": {"id": 101},
        }
    ]
    items = clickup.task_items(task, comments)
    assert [i["external_id"] for i in items] == [
        "task:t4:header",
        "task:t4:description",
        "comment:c1",
    ]
    assert items[0]["author_ref"] == "ClickUp"
    assert items[0]["sent_at"] == datetime.fromtimestamp(1790000000, UTC)
    assert items[1]["body_text"] == "Synthetic description"
    assert items[1]["author_ref"] == "202"
    assert items[2]["author_ref"] == "101"
    assert items[2]["sent_at"] == datetime.fromtimestamp(1790000600, UTC)
    assert all(i["thread_key"] == "t4" for i in items)


def test_empty_description_adds_no_item():
    items = clickup.task_items(make_task("t5", text_content="  \n"), [])
    assert [i["external_id"] for i in items] == ["task:t5:header"]


def test_malformed_timestamp_becomes_none_not_an_error():
    assert clickup._ms_to_dt("not-a-number") is None
    assert clickup._ms_to_dt(None) is None


# --- paging, filtering, rate limits -----------------------------------------


def test_paging_reads_every_page_until_a_short_page():
    page0 = [make_task(f"p{i}") for i in range(100)]
    page1 = [make_task(f"q{i}") for i in range(3)]
    client, seen = make_client({0: page0, 1: page1})
    with client:
        got = [t["id"] for t, _ in clickup.collect(client, PEOPLE, SINCE)]
    assert len(got) == 103
    task_calls = [r for r in seen if r.url.path == "/api/v2/team/T1/task"]
    assert [int(r.url.params["page"]) for r in task_calls] == [0, 1]
    assert task_calls[0].url.params["include_closed"] == "true"
    assert task_calls[0].url.params["subtasks"] == "true"
    assert "date_updated_gt" in task_calls[0].url.params


def test_only_tasks_involving_the_person_and_each_task_once():
    pages = {
        0: [
            make_task("t1", assignees=(101,)),
            make_task("t2", assignees=(202,)),
            make_task("t3", assignees=(202,)),
        ],
        1: [make_task("t1", assignees=(101,))],
    }
    client, _ = make_client(pages)
    with client:
        got = [t["id"] for t, _ in clickup.collect(client, PEOPLE, SINCE)]
    assert got == ["t1"]


def test_creator_counts_as_involved():
    pages = {0: [make_task("t9", assignees=(202,), creator={"id": 101})]}
    client, _ = make_client(pages)
    with client:
        got = [t["id"] for t, _ in clickup.collect(client, PEOPLE, SINCE)]
    assert got == ["t9"]


def test_rate_limit_429_backs_off_on_retry_after(monkeypatch: pytest.MonkeyPatch):
    sleeps: list[float] = []
    monkeypatch.setattr(sizing.time, "sleep", sleeps.append)
    client, _ = make_client({0: [make_task("t1")]}, throttle=1)
    with client:
        got = [t["id"] for t, _ in clickup.collect(client, PEOPLE, SINCE)]
    assert got == ["t1"]
    assert sleeps == [2.0]


def test_dry_run_counts_without_a_connection():
    pages = {
        0: [
            make_task("t1", text_content="Synthetic description"),
            make_task("t2"),
        ]
    }
    comments = {
        "t1": [
            {
                "id": "c1",
                "comment_text": "Synthetic",
                "date": "1790000600000",
                "user": {"id": 101},
            }
        ]
    }
    client, _ = make_client(pages, comments)
    with client:
        counts = clickup.run(client, PEOPLE, SINCE)
    # t1: header, description, one comment; t2: header only.
    assert (counts.tasks, counts.items) == (2, 4)


# --- database ---------------------------------------------------------------


def test_upsert_is_idempotent_and_updates_changed_comments(db: psycopg.Connection):
    db.execute("DELETE FROM cmap.intake_item WHERE origin = 'clickup'")
    db.execute("DELETE FROM cmap.intake_thread WHERE origin = 'clickup'")
    db.commit()
    pages = {0: [make_task("t1", text_content="Synthetic description")]}
    comments = {
        "t1": [
            {
                "id": "c1",
                "comment_text": "first",
                "date": "1790000600000",
                "user": {"id": 101},
            }
        ]
    }

    client, _ = make_client(pages, comments)
    with client:
        clickup.run(client, PEOPLE, SINCE, conn=db)
    db.commit()
    first = db.execute(
        "SELECT count(*) FROM cmap.intake_item WHERE origin='clickup'"
    ).fetchone()[0]
    threads = db.execute(
        "SELECT item_count, title FROM cmap.intake_thread WHERE origin='clickup' AND thread_key='t1'"
    ).fetchall()
    assert first == 3
    assert threads == [(3, "Synthetic task t1")]

    comments["t1"][0]["comment_text"] = "edited"
    client, _ = make_client(pages, comments)
    with client:
        clickup.run(client, PEOPLE, SINCE, conn=db)
    db.commit()
    assert (
        db.execute(
            "SELECT count(*) FROM cmap.intake_item WHERE origin='clickup'"
        ).fetchone()[0]
        == first
    )
    assert db.execute(
        "SELECT body_text FROM cmap.intake_item WHERE origin='clickup' AND external_id='comment:c1'"
    ).fetchone() == ("edited",)
    assert (
        db.execute(
            "SELECT count(*) FROM cmap.intake_thread WHERE origin='clickup' AND thread_key='t1'"
        ).fetchone()[0]
        == 1
    )
