"""A restart must not leave the job it killed stuck in 'running' forever."""

from __future__ import annotations

from typing import Any

from brain.worker import boot_time, requeue_orphans


def test_jobs_running_before_boot_are_requeued(db: Any) -> None:
    db.execute("DELETE FROM cmap.job")
    old = db.execute(
        "INSERT INTO cmap.job (kind, payload, state, started_at) "
        "VALUES ('communities', '{}', 'running', now() - interval '1 hour') RETURNING id"
    ).fetchone()[0]
    db.commit()
    booted = boot_time()
    mine = db.execute(
        "INSERT INTO cmap.job (kind, payload, state, started_at) "
        "VALUES ('relations', '{}', 'running', now() + interval '1 second') RETURNING id"
    ).fetchone()[0]
    db.commit()

    assert requeue_orphans(booted) == 1
    states = dict(db.execute("SELECT id, state FROM cmap.job").fetchall())
    assert states[old] == "queued"
    assert states[mine] == "running"
