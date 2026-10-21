"""Offline bootstrap ordering; database effects are mocked, never executed."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest
import json
import hashlib
import sys

VALID_URL = "postgresql://invented:invented-only@127.0.0.1:55432/oracle2?sslmode=verify-full&sslrootcert=%2Finvented%2Fca.pem"



@pytest.fixture(autouse=True)
def owned_fixture_context(monkeypatch, tmp_path):
    import init_local_stores as bootstrap
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"invented-ca-only")
    proof = tmp_path / "qualification.json"
    proof.write_text(json.dumps(dict(container_id="a" * 64, synthetic_only=True,
        tls_verify_full=True, plaintext_refused=True, wrong_password_refused=True,
        ca_sha256=hashlib.sha256(ca.read_bytes()).hexdigest())))
    monkeypatch.setattr(sys.modules[__name__], "VALID_URL",
        "postgresql://oracle2_admin:oracle2_local_admin_only@127.0.0.1:55432/oracle2?sslmode=verify-full&sslrootcert=" + str(ca).replace("/", "%2F"))
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "oracle2-ci-invented")
    monkeypatch.setenv("ORACLE2_SYNTHETIC_POSTGRES_CONTAINER", "a" * 64)
    monkeypatch.setenv("ORACLE2_TEST_TLS_QUALIFICATION", str(proof))
    details = dict(Id="a" * 64, Config=dict(Labels={
        "com.docker.compose.project": "oracle2-ci-invented",
        "com.docker.compose.service": "postgres"}))
    monkeypatch.setattr(bootstrap, "owned_postgres_fixture", lambda container, url: details)
    return details, proof, ca


def run_bootstrap(monkeypatch, *, fail=None):
    import pytest
    import init_local_stores as bootstrap

    events = []

    class Connection:
        closed = False
        autocommit = True
        def execute(self, statement):
            events.append(statement)
            if fail and fail in statement:
                raise PermissionError("reviewed unreachable processing owner required")

    @contextmanager
    def connect(url, **kwargs):
        assert url == VALID_URL
        events.append("connect")
        yield Connection()

    def saver(connection):
        assert isinstance(connection, Connection)
        events.append("checkpoint")
        return type("Saver", (), {"setup": lambda self: events.append("setup")})()

    monkeypatch.setenv("ORACLE2_TEST_ADMIN_URL", VALID_URL)
    with patch.object(bootstrap.psycopg, "connect", connect), patch.object(
        bootstrap, "PostgresSaver", saver
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
    assert events[len(expected) + 1:len(expected) + 4] == ["connect", "checkpoint", "setup"]
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
    VALID_URL.split("sslrootcert=")[0] + "sslrootcert=",
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


@pytest.mark.parametrize("failure", ["project", "service", "container", "ca", "synthetic", "tls", "plaintext", "password"])
def test_stale_or_different_ownership_and_ca_denied_before_database(monkeypatch, owned_fixture_context, failure):
    import init_local_stores as bootstrap
    details, proof, ca = owned_fixture_context
    body = json.loads(proof.read_text())
    if failure == "project": details["Config"]["Labels"]["com.docker.compose.project"] = "other"
    elif failure == "service": details["Config"]["Labels"]["com.docker.compose.service"] = "other"
    elif failure == "container": body["container_id"] = "b" * 64
    elif failure == "ca": ca.write_bytes(b"wrong-invented-ca")
    else:
        body[{"synthetic": "synthetic_only", "tls": "tls_verify_full", "plaintext": "plaintext_refused", "password": "wrong_password_refused"}[failure]] = False
    proof.write_text(json.dumps(body))
    monkeypatch.setenv("ORACLE2_TEST_ADMIN_URL", VALID_URL)
    with patch.object(bootstrap.psycopg, "connect") as connect, patch.object(bootstrap.PostgresSaver, "from_conn_string") as saver:
        with pytest.raises(PermissionError): bootstrap.main()
        connect.assert_not_called()
        saver.assert_not_called()


@pytest.mark.parametrize("failure", [None, "label", "port", "database", "user", "environment"])
def test_shared_owned_fixture_validator_preserves_exact_target(monkeypatch, failure):
    from dev.oracle2 import test_tls_bootstrap as tls
    details = dict(Id="a" * 64, Config=dict(Labels={"oracle.operating.synthetic": "true"}, Env=[
        "POSTGRES_USER=oracle2_admin", "POSTGRES_PASSWORD=oracle2_local_admin_only", "POSTGRES_DB=oracle2"]),
        NetworkSettings=dict(Ports={"5432/tcp": [dict(HostIp="127.0.0.1", HostPort="55432")]}))
    url = VALID_URL
    if failure == "label": details["Config"]["Labels"]["oracle.operating.synthetic"] = "false"
    elif failure == "port": details["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = "55433"
    elif failure == "database": url = url.replace("/oracle2?", "/other?")
    elif failure == "user": url = url.replace("oracle2_admin:", "other:")
    elif failure == "environment": details["Config"]["Env"] = []
    monkeypatch.setattr(tls, "run", lambda *args: json.dumps([details]))
    # The shared validator deliberately has no implicit global-project binding;
    # W10 separately owns a distinct project for each temporary worker.
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "oracle2-ci-different-parent")
    if failure:
        with pytest.raises(PermissionError): tls.owned_postgres_fixture("a" * 64, url)
    else:
        assert tls.owned_postgres_fixture("a" * 64, url) is not None


def test_filepath_import_has_no_sibling_path_requirement():
    import importlib.util
    import init_local_stores as bootstrap
    spec = importlib.util.spec_from_file_location("retained_filepath_bootstrap", bootstrap.ROOT / "scripts/oracle2/init_local_stores.py")
    value = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", [str(bootstrap.ROOT), *[p for p in sys.path if not p.endswith("scripts/oracle2")]]):
        spec.loader.exec_module(value)
    assert callable(value.setup_checkpoint_tables)
    assert value.SYNTHETIC_MIGRATIONS == bootstrap.SYNTHETIC_MIGRATIONS


def test_checkpoint_helper_uses_only_supplied_open_connection():
    import init_local_stores as bootstrap
    from unittest.mock import Mock
    connection = Mock(closed=False, autocommit=True)
    with patch.object(bootstrap, "PostgresSaver") as saver, patch.object(bootstrap.psycopg, "connect") as connect:
        bootstrap.setup_checkpoint_tables(connection)
        saver.assert_called_once_with(connection)
        saver.return_value.setup.assert_called_once_with()
        connect.assert_not_called()
        assert connection.execute.call_count == 3


@pytest.mark.parametrize("connection", ["postgresql://arbitrary", None])
def test_checkpoint_helper_cannot_choose_uri_target(connection):
    import init_local_stores as bootstrap
    from unittest.mock import Mock
    if connection is None: connection = Mock(closed=True, autocommit=True)
    with patch.object(bootstrap, "PostgresSaver") as saver, patch.object(bootstrap.psycopg, "connect") as connect:
        with pytest.raises(PermissionError): bootstrap.setup_checkpoint_tables(connection)
        saver.assert_not_called()
        connect.assert_not_called()
