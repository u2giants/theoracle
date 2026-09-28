import importlib.metadata as metadata
import json
import os
from pathlib import Path
from urllib.request import urlopen


def test_pinned_bundle_imports_and_lock_exists():
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    assert lock.exists()
    assert metadata.version("graphiti-core") == "0.30.2"
    import graphiti_core  # noqa: F401
    import docling  # noqa: F401
    import langgraph  # noqa: F401
    import langgraph.checkpoint.postgres  # noqa: F401
    import falkordb  # noqa: F401


def test_graphiti_telemetry_disabled(monkeypatch):
    monkeypatch.setenv("GRAPHITI_TELEMETRY_ENABLED", "false")
    from oracle_brain.config import Settings
    monkeypatch.setenv("ORACLE2_DATABASE_URL", "postgres://x@localhost/test")
    settings = Settings.from_env("test")
    assert settings.mode == "synthetic"


def test_graphiti_edge_has_no_exact_source_span_contract():
    # Pinned Graphiti's public edge exposes episode references and a fact,
    # but no exact source-region offsets. Oracle must require a separate
    # Pydantic extraction receipt before candidate admission.
    from graphiti_core.edges import EntityEdge
    fields = set(EntityEdge.model_fields)
    assert {"episodes", "fact", "group_id"} <= fields
    assert not {"source_start", "source_end"} <= fields


def test_local_object_store_is_real_and_healthy():
    endpoint = os.environ.get("ORACLE2_TEST_BLOB_ENDPOINT")
    assert endpoint, "isolated object-store endpoint required"
    with urlopen(f"{endpoint}/_localstack/health", timeout=5) as response:
        health = json.load(response)
    assert health["services"]["s3"] in {"available", "running"}
