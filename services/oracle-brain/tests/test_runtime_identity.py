from pathlib import Path

import psycopg
import pytest

from oracle_brain.config import Settings
from oracle_brain.graph.falkor import FalkorGraphStore
from uuid import uuid4


def test_extractor_cannot_write_accepted_or_read_projector(admin_url, candidate_url, confirmed_url, monkeypatch):
    extract_db = admin_url.replace("oracle2_admin:oracle2_local_admin_only", "oracle2_extract:oracle2_local_extract_only")
    with psycopg.connect(extract_db) as connection:
        with pytest.raises(psycopg.Error):
            connection.execute("INSERT INTO oracle2.accepted(workspace_id,assertion_id,revision,status,payload) VALUES (gen_random_uuid(),gen_random_uuid(),1,'active','{}')")
    monkeypatch.setenv("ORACLE2_DATABASE_URL", extract_db)
    monkeypatch.setenv("ORACLE2_CANDIDATE_GRAPH_URL", candidate_url)
    monkeypatch.setenv("ORACLE2_CONFIRMED_GRAPH_URL", confirmed_url)
    with pytest.raises(ValueError, match="confirmed graph"):
        Settings.from_env("extractor")
    monkeypatch.delenv("ORACLE2_CONFIRMED_GRAPH_URL")
    assert Settings.from_env("extractor").confirmed_graph_url is None
    monkeypatch.setenv("ORACLE2_CHECKPOINT_DATABASE_URL", extract_db)
    with pytest.raises(ValueError, match="checkpoint credentials"):
        Settings.from_env("extractor")
    monkeypatch.delenv("ORACLE2_CHECKPOINT_DATABASE_URL")
    with pytest.raises(Exception):
        # Candidate password cannot authenticate to the confirmed instance.
        wrong = confirmed_url.replace("oracle2_confirmed_local_only",
                                      "oracle2_candidate_local_only")
        FalkorGraphStore(wrong).query(uuid4())


def test_identity_manifest_forbids_shared_project():
    text = (Path(__file__).resolve().parents[3] / "dev/oracle2/runtime-identities.yaml").read_text()
    assert "oracle2_tasks_allowed: false" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text


def test_preview_builds_use_pinned_python_layer():
    root = Path(__file__).resolve().parents[3] / "apps/workers"
    for name in ("trigger.oracle2-extract.config.ts", "trigger.oracle2-project.config.ts"):
        text = (root / name).read_text()
        assert "oracle2Python(" in text and "pythonExtension" not in text, name
    layer = (root / "oracle2-python-extension.ts").read_text()
    assert "ORACLE2_PYTHON_VERSION = '3.12.14'" in layer
    assert "--require-hashes" in layer


def test_preview_status_vocabulary():
    text = (Path(__file__).resolve().parents[3] / "dev/oracle2/runtime-identities.yaml").read_text()
    status = text.split("preview_status:", 1)[1].split()[0]
    assert status in {"not_provisioned", "measured_synthetic", "failed_synthetic", "deleted"}
