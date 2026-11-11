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


def test_failed_job_retried_with_backoff(db: Any) -> None:
    """Repair A2: a job that raises is retried twice, later each time, before
    it is marked failed; its error text is kept throughout."""
    from brain.worker import claim_next_job, finish_job

    db.execute("DELETE FROM cmap.job")
    job_id = db.execute(
        "INSERT INTO cmap.job (kind, payload) VALUES ('relations', '{}') RETURNING id"
    ).fetchone()[0]
    db.commit()

    def _row() -> tuple[str, int, float, str | None]:
        db.commit()
        row = db.execute(
            "SELECT state, attempts, extract(epoch FROM run_after - now()), error "
            "FROM cmap.job WHERE id = %s",
            (job_id,),
        ).fetchone()
        return str(row[0]), int(row[1]), float(row[2]), row[3]

    waits = []
    for attempt in (1, 2):
        job = claim_next_job()
        assert job is not None and job["id"] == job_id and job["attempts"] == attempt
        assert finish_job(job_id, f"boom {attempt}") == "queued"
        state, attempts, wait, error = _row()
        assert (state, attempts, error) == ("queued", attempt, f"boom {attempt}")
        waits.append(wait)
        assert claim_next_job() is None, "not claimable until its wait is over"
        db.execute("UPDATE cmap.job SET run_after = now() WHERE id = %s", (job_id,))
        db.commit()
    assert 290 < waits[0] <= 300
    assert 1190 < waits[1] <= 1200

    job = claim_next_job()
    assert job is not None and job["attempts"] == 3
    assert finish_job(job_id, "boom 3") == "failed"
    state, attempts, _wait, error = _row()
    assert (state, attempts, error) == ("failed", 3, "boom 3")
    assert claim_next_job() is None


def test_successful_retry_clears_the_error(db: Any) -> None:
    from brain.worker import claim_next_job, finish_job

    db.execute("DELETE FROM cmap.job")
    job_id = db.execute(
        "INSERT INTO cmap.job (kind, payload) VALUES ('project', '{}') RETURNING id"
    ).fetchone()[0]
    db.commit()
    claim_next_job()
    finish_job(job_id, "transient")
    db.execute("UPDATE cmap.job SET run_after = now() WHERE id = %s", (job_id,))
    db.commit()
    claim_next_job()
    assert finish_job(job_id, None) == "done"
    db.commit()
    assert db.execute(
        "SELECT state, error FROM cmap.job WHERE id = %s", (job_id,)
    ).fetchone() == ("done", None)


def test_result_write_is_retried(db: Any, monkeypatch: Any) -> None:
    """Repair A7: a failed result write is tried again, not dropped."""
    from brain import worker

    db.execute("DELETE FROM cmap.job")
    job_id = db.execute(
        "INSERT INTO cmap.job (kind, payload, state, attempts) "
        "VALUES ('project', '{}', 'running', 1) RETURNING id"
    ).fetchone()[0]
    db.commit()
    real = worker.finish_job
    calls = {"n": 0}

    def _flaky(job: Any, error: str | None) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connection reset")
        return real(job, error)

    monkeypatch.setattr(worker, "finish_job", _flaky)
    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)
    worker.record_result(job_id, None)
    db.commit()
    assert calls["n"] == 2
    assert db.execute("SELECT state FROM cmap.job WHERE id = %s", (job_id,)).fetchone()[0] == "done"
