import os
import stat

import pytest

from oracle_brain.graph.evidence_answer import graph_tls_options

NAMES = ("ORACLE2_GRAPH_TLS_CA_PEM", "ORACLE2_GRAPH_TLS_CERT_PEM", "ORACLE2_GRAPH_TLS_KEY_PEM")


def test_no_tls_settings_means_no_options(monkeypatch):
    for n in NAMES:
        monkeypatch.delenv(n, raising=False)
    assert graph_tls_options("redis") == {}


def test_partial_or_plaintext_refused(monkeypatch):
    monkeypatch.setenv(NAMES[0], "ca")
    for n in NAMES[1:]:
        monkeypatch.delenv(n, raising=False)
    with pytest.raises(ValueError):
        graph_tls_options("rediss")
    monkeypatch.setenv(NAMES[0], "")  # set-but-empty is a configuration error
    with pytest.raises(ValueError):
        graph_tls_options("rediss")
    for n in NAMES:
        monkeypatch.setenv(n, "x")
    with pytest.raises(ValueError):
        graph_tls_options("redis")


def test_full_settings_write_private_files(monkeypatch):
    for n, v in zip(NAMES, ("CA", "CERT", "KEY")):
        monkeypatch.setenv(n, v)
    opts = graph_tls_options("rediss")
    assert graph_tls_options("rediss") == opts  # written once, reused
    try:
        assert opts["ssl_ca_data"] == "CA" and opts["ssl_check_hostname"] is True
        for key, value in (("ssl_certfile", "CERT"), ("ssl_keyfile", "KEY")):
            assert open(opts[key]).read() == value
            assert stat.S_IMODE(os.stat(opts[key]).st_mode) == 0o600
    finally:
        os.unlink(opts["ssl_certfile"]); os.unlink(opts["ssl_keyfile"])


def test_falkordb_client_accepts_tls_options(monkeypatch):
    import inspect
    from falkordb import FalkorDB
    accepted = set(inspect.signature(FalkorDB.__init__).parameters)
    assert {"ssl_ca_data", "ssl_certfile", "ssl_keyfile", "ssl_cert_reqs",
            "ssl_check_hostname"} <= accepted


def test_seed_target_guard():
    import importlib.util, pathlib
    path = pathlib.Path(__file__).resolve().parents[3] / "scripts/oracle2/seed_hosted_preview.py"
    spec = importlib.util.spec_from_file_location("seed_hosted_preview", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    ref = "abcdefghijklmnopqrst"
    ok = [f"postgresql://postgres:x@db.{ref}.supabase.co:5432/postgres?sslmode=require",
          f"postgresql://postgres.{ref}:x@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require"]
    for url in ok:
        mod._require_target(url, ref)
    bad = [f"postgresql://postgres:x@db.{ref}.supabase.co:5432/postgres",
           f"postgresql://postgres:x@db.{ref}.supabase.co.evil.example:5432/postgres?sslmode=require",
           f"postgresql://postgres.other:x@aws-0-us-east-1.pooler.supabase.com/postgres?sslmode=require",
           f"postgresql://postgres:x@db.eqccjfbyrywsqkxxpjvg.supabase.co/postgres?sslmode=require"]
    for url in bad:
        with pytest.raises(PermissionError):
            mod._require_target(url, "eqccjfbyrywsqkxxpjvg" if "eqcc" in url else ref)
    with pytest.raises(PermissionError):
        mod._require_outside_repo(path.parent / "x.json", path.parents[2])
