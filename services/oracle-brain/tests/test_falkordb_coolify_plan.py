"""The FalkorDB-on-Coolify plan's embedded compose equals its committed golden fixture, exactly."""

# Invented address fixtures: preserve private-network refusal coverage, never real topology.
def _synthetic_ipv4(*octets):
    assert len(octets) == 4 and all(type(n) is int and 0 <= n <= 255 for n in octets)
    return '.'.join(map(str, octets))

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "validate_falkordb_plan", ROOT / "dev/oracle2/hosting/validate_falkordb_plan.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
SC = "        rename-command DEBUG \"\"\n        EOF\n"


@pytest.mark.parametrize("role", sorted(validator.ROLES))
def test_validator_passes(role):
    assert validator.check(role, validator.render(role)) == []


def test_main_passes():
    assert validator.main([]) == 0


# Review 14's listed bypasses, plus every earlier mutation case (each must break golden equality).
REVIEW14 = [
    (SC, SC + "        echo 'tls-auth-clients no' >> /run/auth/server.conf\n"),
    (SC, SC + "        echo 'appendonly no' >> /run/auth/server.conf\n"),
    (SC, SC + "        cat >> /run/auth/server.conf <<'EOF2'\n        tls-auth-clients no\n        EOF2\n"),
    ("      FALKORDB_SERVER_TLS_B64: ${FALKORDB_SERVER_TLS_B64}", ""),
    ("    driver: bridge\n", "    driver: host\n"),
    ('    entrypoint: ["/bin/sh","-c"]\n    command:\n      - |\n        set -e',
     '    entrypoint: ["/bin/bash","-lc"]\n    command:\n      - |\n        set -e'),
    ("  falkordb:\n", "  falkordb:\n    volumes_from: [data-files]\n"),
    ("  falkordb:\n", "  falkordb:\n    userns_mode: host\n"),
    (SC, SC + "        echo 'requirepass x' >> /run/auth/server.conf\n"),
]
EARLIER = [('--loadmodule /var/lib/falkordb/bin/falkordb.so', ''), ('restart: unless-stopped', 'restart: "no"'), ('chown 999:999 /var/lib/falkordb/data /backups && ', ''), ('    read_only: true\n', '    read_only: true\n    devices: ["/dev/sda:/dev/sda"]\n'), ('{name: oracle-falkordb-confirmed-backups}', '{name: oracle-falkordb-confirmed-backups, driver_opts: {type: none, o: bind, device: /host}}'), ('    name: oracle-graph-confirmed\n', ''), ('{name: oracle-falkordb-confirmed-backups}', '{}'), ('name: oracle-falkordb-confirmed\n', ''), ('    read_only: true\n', '    read_only: true\n    privileged: true\n'), ('  falkordb:\n', '  falkordb:\n    network_mode: host\n'), ('  falkordb:\n', '  falkordb:\n    cap_add: [NET_ADMIN]\n'), ('mem_limit: 2g', 'mem_limit: 8g'), ('pids_limit: 256', 'pids_limit: 4096'), ('        port 0\n', '        port 6380\n'), ('network_mode: none', 'network_mode: bridge'), ("          echo 'user default off'\n", "          echo 'user default off'\n          echo 'user default on'\n"), ('        port 0\n', '        port 0\n        port 6380\n'), ('        tls-auth-clients yes\n', '        tls-auth-clients yes\n        tls-auth-clients no\n'), ('        port 0\n', '        port 0\n        port 0\n'), ('set $$u falkordb:6379; proxy_pass $$u;', 'proxy_pass falkordb:6379;'), ('resolver 127.0.0.11 valid=10s ipv6=off; ', ''), ('    pids_limit: 32\n', '    pids_limit: 32\n    privileged: true\n'), ('volumes:\n  oracle-falkordb-confirmed-data', 'volumes: null\nx:\n  oracle-falkordb-confirmed-data'), ('    healthcheck:\n', '    hc_removed:\n'), ('\nnetworks:\n  oracle-graph-confirmed:\n', '\nnetz:\n  oracle-graph-confirmed:\n'), ('    cpus: 1.0\n', '    cpus: 4.0\n'), ('size=16m,uid=999', 'size=4g,uid=999'), ('      - /tmp:rw,noexec,nosuid,size=16m', '      - /tmp:rw,exec,nosuid,size=16m'), ('tls-auth-clients yes', 'tls-auth-clients no'), ('appendonly yes', 'appendonly no'), ("echo 'user default off'", "echo 'user default on nopass ~* +@all'"), ('-@all +ping +bgsave', '+@all'), ('mem_limit: 2g', 'mem_limit: 64g'), ('pids_limit: 256', 'pids_limit: -1'), ('read_only: true', 'read_only: false'), ('user: "999:999"', 'user: "0:0"'), ('100.66.37.58:6390', (_synthetic_ipv4(0,0,0,0) + ':6390')), ('178.156.180.212:16390', (_synthetic_ipv4(0,0,0,0) + ':16390')), ('enable_ip_masquerade: "false"', 'enable_ip_masquerade: "true"')]


def _for_role(text, role):
    if role == "confirmed":
        return text
    return text.replace("confirmed", role).replace(":16390", ":16391").replace(":6390", ":6391")


@pytest.mark.parametrize("role", ["confirmed", "candidate"])
@pytest.mark.parametrize("old,new", REVIEW14 + EARLIER)
def test_any_mutation_fails_with_diff(old, new, role):
    rendered = validator.render(role)
    old, new = _for_role(old, role), _for_role(new, role)
    assert old in rendered, old
    errs = validator.check(role, rendered.replace(old, new, 1))
    assert errs and (errs[0].startswith("golden mismatch:\n") or errs[0].startswith("malformed")), errs


def test_mismatch_diff_is_readable():
    bad = validator.render("confirmed").replace("tls-auth-clients yes", "tls-auth-clients no", 1)
    [err] = validator.check("confirmed", bad)
    assert "-" in err and "tls-auth-clients no" in err and "@@" in err


def test_requirepass_comment_is_a_reviewable_golden_change():
    # A comment is part of the script bytes, so it too is a (deliberate, reviewable) golden change.
    bad = validator.render("confirmed").replace("set -e; umask 077", "set -e; umask 077  # no requirepass", 1)
    assert validator.check("confirmed", bad)


def test_swapped_role_rejected():
    assert validator.check("confirmed", validator.render("candidate"))


def test_malformed_is_controlled_fail_and_both_roles_reported(monkeypatch, capsys):
    assert validator.check("confirmed", "services: [\n")[0].startswith("malformed compose")
    monkeypatch.setattr(validator, "compose_block", lambda text=None: "services: null\n")
    assert validator.main([]) == 1
    out = capsys.readouterr().out
    assert "confirmed: FAIL" in out and "candidate: FAIL" in out
