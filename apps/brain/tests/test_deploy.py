"""Step 14: the Coolify compose file and image workflow stay well formed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BRAIN = Path(__file__).resolve().parents[1]
REPO = BRAIN.parents[1]
COMPOSE = BRAIN / "deploy" / "compose.coolify.yaml"
DEV_COMPOSE = BRAIN / "compose.dev.yaml"
WORKFLOW = REPO / ".github" / "workflows" / "brain-image.yml"
SETTINGS_FIELDS = (
    "DATABASE_URL",
    "OPENROUTER_API_KEY",
    "BRAIN_FRONTIER_MODEL",
    "BRAIN_CHAT_MODEL",
    "BRAIN_EVAL_MODEL",
    "BRAIN_VISION_MODEL",
    "BRAIN_EMBED_MODEL",
    "SCALEDOWN_API_KEY",
    "BRAIN_SHARED_TOKEN",
    "BRAIN_INTERVIEW_ENABLED",
    "BRAIN_WEB_BASE_URL",
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _env(service: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in service["environment"]:
        name, _, value = item.partition("=")
        out[name] = value
    return out


def test_falkordb_pinned_like_dev_and_internal() -> None:
    prod = _load(COMPOSE)["services"]["oracle-falkordb"]
    dev = _load(DEV_COMPOSE)["services"]["falkordb"]
    assert prod["image"] == dev["image"]
    assert "@sha256:" in prod["image"]
    assert "ports" not in prod
    assert "--save 60 1" in _env(prod)["REDIS_ARGS"]
    assert _env(prod)["FALKORDB_DATA_PATH"] == "/data"
    assert any(v.endswith(":/data") for v in prod["volumes"])


def test_brain_env_comes_from_variables_not_values() -> None:
    brain = _load(COMPOSE)["services"]["oracle-brain"]
    env = _env(brain)
    for name in SETTINGS_FIELDS:
        assert name in env, name
        assert env[name].startswith("${"), name
    assert env["FALKORDB_URL"] == "redis://oracle-falkordb:6379"
    assert env["BRAIN_IMPORT_DIR"] == "/data/import"
    assert any(v.endswith(":/data/import") for v in brain["volumes"])
    assert brain["image"].startswith("ghcr.io/u2giants/theoracle-brain:")


def test_interviews_default_off() -> None:
    env = _env(_load(COMPOSE)["services"]["oracle-brain"])
    assert env["BRAIN_INTERVIEW_ENABLED"] == "${BRAIN_INTERVIEW_ENABLED:-false}"


def test_no_model_id_hardcoded_in_deploy_files() -> None:
    text = COMPOSE.read_text(encoding="utf-8") + WORKFLOW.read_text(encoding="utf-8")
    assert not re.search(r"(anthropic|openai)/[a-z0-9.-]+", text)


def test_image_workflow_publishes_sha_and_latest_on_main_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ghcr.io/u2giants/theoracle-brain:${{ github.sha }}" in text
    assert "ghcr.io/u2giants/theoracle-brain:latest" in text
    assert (
        "push: ${{ github.ref == 'refs/heads/main' && github.event_name != 'pull_request' }}"
        in text
    )
    flow = _load(WORKFLOW)
    on = flow.get("on", flow.get(True))
    assert on["push"]["branches"] == ["main"]


def test_unset_compose_variables_do_not_break_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compose renders an unset ${VAR} as ''; Settings must treat it as unset."""
    from brain.config import Settings

    monkeypatch.setenv("BRAIN_MAX_FRONTIER_CALLS_PER_JOB", "")
    monkeypatch.setenv("BRAIN_EMBED_DIMS", "")
    settings = Settings()
    assert settings.brain_max_frontier_calls_per_job is None
    assert settings.brain_embed_dims == 1024


def test_brain_port_declared_for_proxy() -> None:
    """Coolify's proxy needs the port: the API drops it from the domain."""
    brain = _load(COMPOSE)["services"]["oracle-brain"]
    assert brain["expose"] == ["8000"]
    assert "EXPOSE 8000" in (BRAIN / "Dockerfile").read_text(encoding="utf-8")
