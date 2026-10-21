"""Offline bootstrap ordering; database effects are mocked, never executed."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest

VALID_URL = "postgresql://invented:invented-only@127.0.0.1:55432/oracle2?sslmode=verify-full&sslrootcert=%2Finvented%2Fca.pem"



def run_bootstrap(monkeypatch, *, fail=None):
    import pytest
    import init_local_stores as bootstrap

    events = []

    class Connection:
        def execute(self, statement):
            events.append(statement)
            if fail and fail in statement:
                raise PermissionError("reviewed unreachable processing owner required")

    @contextmanager
    def connect(url):
        assert url == VALID_URL
        events.append("connect")
        yield Connection()

    @contextmanager
    def saver(url):
        assert url == VALID_URL
        events.append("checkpoint")
        yield type("Saver", (), {"setup": lambda self: events.append("setup")})()

    monkeypatch.setenv("ORACLE2_TEST_ADMIN_URL", VALID_URL)
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
    import init_local_stores as bootstrap

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


def assert_non_loopback_rejected(monkeypatch, url):
    import pytest
    import init_local_stores as bootstrap

    monkeypatch.setenv("ORACLE2_TEST_ADMIN_URL", url)
    with patch.object(bootstrap.psycopg, "connect") as connect, patch.object(
        bootstrap.PostgresSaver, "from_conn_string"
    ) as saver:
        with pytest.raises(PermissionError, match="isolated loopback"):
            bootstrap.main()
        connect.assert_not_called()
        saver.assert_not_called()


def test_missing_target_rejected_before_any_database_access(monkeypatch):
    assert_non_loopback_rejected(monkeypatch, "")


def test_remote_target_rejected_before_any_database_access(monkeypatch):
    assert_non_loopback_rejected(monkeypatch, "postgresql://invented@outside.example/oracle2")


@pytest.mark.parametrize("suffix", [
    "&hostaddr=203.0.113.1", "&host=outside.example", "&port=5432",
    "&service=invented", "&options=-csearch_path=public", "&user=other",
    "&dbname=other", "&sslmode=disable", "&sslrootcert=%2Fother.pem",
    "&sslmode=verify-full", "&sslrootcert=%2Finvented%2Fca.pem",
])
def test_query_override_rejected_without_any_connection(monkeypatch, suffix):
    assert_non_loopback_rejected(monkeypatch, VALID_URL + suffix)


@pytest.mark.parametrize("url", [
    VALID_URL.replace("sslmode=verify-full", "sslmode=require"),
    VALID_URL.replace("%2Finvented%2Fca.pem", ""),
    VALID_URL.replace("127.0.0.1", "127.0.0.1,outside.example"),
    VALID_URL.replace("127.0.0.1", "%2Fvar%2Frun%2Fpostgresql"),
    VALID_URL.replace(":55432", ""),
])
def test_ambiguous_or_unqualified_target_rejected(monkeypatch, url):
    import init_local_stores as bootstrap
    monkeypatch.setenv("ORACLE2_TEST_ADMIN_URL", url)
    with patch.object(bootstrap.psycopg, "connect") as connect, patch.object(
        bootstrap.PostgresSaver, "from_conn_string"
    ) as saver:
        with pytest.raises(PermissionError):
            bootstrap.main()
        connect.assert_not_called()
        saver.assert_not_called()


@pytest.mark.parametrize("key", ["PGHOSTADDR", "PGSERVICE", "PGOPTIONS", "PGSERVICEFILE", "PGSYSCONFDIR", "PGHOST", "PGPORT", "PGDATABASE", "PGSSLMODE", "PGSSLROOTCERT"])
def test_libpq_environment_cannot_redirect_bootstrap(monkeypatch, key):
    import init_local_stores as bootstrap
    monkeypatch.setenv("ORACLE2_TEST_ADMIN_URL", VALID_URL)
    monkeypatch.setenv(key, "invented-override")
    with patch.object(bootstrap.psycopg, "connect") as connect, patch.object(
        bootstrap.PostgresSaver, "from_conn_string"
    ) as saver:
        with pytest.raises(PermissionError, match="environment overrides forbidden"):
            bootstrap.main()
        connect.assert_not_called()
        saver.assert_not_called()
