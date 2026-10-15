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
    for n in NAMES:
        monkeypatch.setenv(n, "x")
    with pytest.raises(ValueError):
        graph_tls_options("redis")


def test_full_settings_write_private_files(monkeypatch):
    for n, v in zip(NAMES, ("CA", "CERT", "KEY")):
        monkeypatch.setenv(n, v)
    opts = graph_tls_options("rediss")
    try:
        assert opts["ssl_ca_data"] == "CA" and opts["ssl_check_hostname"] is True
        for key, value in (("ssl_certfile", "CERT"), ("ssl_keyfile", "KEY")):
            assert open(opts[key]).read() == value
            assert stat.S_IMODE(os.stat(opts[key]).st_mode) == 0o600
    finally:
        os.unlink(opts["ssl_certfile"]); os.unlink(opts["ssl_keyfile"])
