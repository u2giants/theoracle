"""Offline bootstrap ordering; database effects are mocked, never executed."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest

import init_local_stores as bootstrap


def run_bootstrap(monkeypatch, *, fail=None):
    events = []

    class Connection:
        def execute(self, statement):
            events.append(statement)
            if fail and fail in statement:
                raise PermissionError("reviewed unreachable processing owner required")

    @contextmanager
    def connect(url):
        events.append("connect")
        yield Connection()

    @contextmanager
    def saver(url):
        events.append("checkpoint")
        yield type("Saver", (), {"setup": lambda self: events.append("setup")})()

    monkeypatch.setenv("ORACLE2_TEST_ADMIN_URL", "postgresql://invented@127.0.0.1:55432/oracle2")
    with patch.object(bootstrap.psycopg, "connect", connect), patch.object(
        bootstrap.PostgresSaver, "from_conn_string", saver
    ):
        if fail:
            with pytest.raises(PermissionError, match="reviewed unreachable"):
                bootstrap.main()
        else:
            bootstrap.main()
    return events


def test_canonical_prerequisites_precede_checkpoints(monkeypatch):
    events = run_bootstrap(monkeypatch)
    expected = [
        (bootstrap.ROOT / "services/oracle-brain/sql" / name).read_text()
        for name in bootstrap.SYNTHETIC_MIGRATIONS
    ]
    assert events[:len(expected) + 1] == ["connect", *expected]
    assert events[len(expected) + 1:len(expected) + 3] == ["checkpoint", "setup"]
    assert events[-3:] == [
        f"GRANT SELECT,INSERT,UPDATE,DELETE ON public.{name} TO oracle2_checkpoint"
        for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
    ]
    assert bootstrap.SYNTHETIC_MIGRATIONS[-4:] == (
        "011_hosting_source_processing_permissions.sql",
        "012_processing_compiler_capabilities.sql",
        "013_processing_purpose_permissions.sql",
        "014_replacement_source_custody.sql",
    )


def test_owner_refusal_stops_bootstrap_before_checkpoint_setup(monkeypatch):
    events = run_bootstrap(monkeypatch, fail="reviewed unreachable processing owner required")
    assert "checkpoint" not in events
    assert not any("GRANT SELECT,INSERT,UPDATE,DELETE ON public." in x for x in events)


@pytest.mark.parametrize("url", ["", "postgresql://invented@outside.example/oracle2"])
def test_non_loopback_rejected_before_any_database_access(monkeypatch, url):
    monkeypatch.setenv("ORACLE2_TEST_ADMIN_URL", url)
    with patch.object(bootstrap.psycopg, "connect") as connect, patch.object(
        bootstrap.PostgresSaver, "from_conn_string"
    ) as saver:
        with pytest.raises(PermissionError, match="isolated loopback"):
            bootstrap.main()
        connect.assert_not_called()
        saver.assert_not_called()
