"""Preview settings and projector exit contract; needs no running store."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from oracle_brain.config import Settings

ALLOW = "00000000-0000-4000-8000-000000000002"
BRAIN = Path(__file__).resolve().parents[1]


def _preview(monkeypatch, **env):
    for key in ("ORACLE2_CANDIDATE_GRAPH_URL", "ORACLE2_CONFIRMED_GRAPH_URL",
                "ORACLE2_CHECKPOINT_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ORACLE2_ENVIRONMENT", "preview")
    monkeypatch.setenv("ORACLE2_WORKSPACE_ALLOWLIST", ALLOW)
    monkeypatch.setenv("ORACLE2_DAILY_BUDGET", "1")
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_preview_store_urls_need_credentials(monkeypatch):
    _preview(monkeypatch, ORACLE2_DATABASE_URL="postgresql://oracle2_extract@db.invalid/oracle2",
             ORACLE2_CANDIDATE_GRAPH_URL="redis://:synthetic@candidate.invalid:6379")
    with pytest.raises(ValueError, match="own credential"):
        Settings.from_env("extractor")
    monkeypatch.setenv("ORACLE2_DATABASE_URL", "postgresql://oracle2_extract:synthetic@db.invalid/oracle2")
    assert Settings.from_env("extractor").environment == "preview"


def test_projector_fails_closed_with_nonzero_exit():
    env = {"ORACLE2_ENVIRONMENT": "preview", "ORACLE2_WORKSPACE_ALLOWLIST": ALLOW,
           "ORACLE2_DAILY_BUDGET": "1", "ORACLE2_TELEMETRY_MODE": "off",
           "ORACLE2_DATABASE_URL": "postgresql://oracle2_project:synthetic@db.invalid:5432/oracle2?connect_timeout=2",
           "ORACLE2_CONFIRMED_GRAPH_URL": "redis://:synthetic@confirmed.invalid:6379",
           "ORACLE2_PROJECTION_SIGNING_KEY": "s" * 64, "PATH": "/usr/bin:/bin"}
    done = subprocess.run([sys.executable, str(BRAIN / "oracle_brain/projector_cli.py")],
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 1
    assert json.loads(done.stderr.strip().splitlines()[-1])["status"] == "failed"
    assert "synthetic" not in done.stderr
