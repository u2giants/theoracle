"""Step 0.2: Colab offload settings validation and GPU-free brain dependency guard."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from brain.config import Settings

BRAIN_DIR = Path(__file__).resolve().parents[1]
PYPROJECT = BRAIN_DIR / "pyproject.toml"
FORBIDDEN_GPU_PACKAGES = frozenset(
    {"torch", "vllm", "peft", "trl", "bitsandbytes", "accelerate", "datasets"}
)


def _clear_colab_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "BRAIN_COLAB_WORKER_TOKEN",
        "BRAIN_COLAB_LEASE_ENABLED",
        "BRAIN_COLAB_LEASE_TTL_SECONDS",
        "BRAIN_COLAB_MAX_BATCH_SIZE",
    ):
        monkeypatch.delenv(var, raising=False)


def test_colab_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_colab_env(monkeypatch)
    settings = Settings()
    assert settings.brain_colab_worker_token is None
    assert settings.brain_colab_lease_enabled is False
    assert settings.brain_colab_lease_ttl_seconds == 900
    assert settings.brain_colab_max_batch_size == 64


@pytest.mark.parametrize("ttl", [1801, 59, 0, -1])
def test_colab_lease_ttl_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch, ttl: int
) -> None:
    _clear_colab_env(monkeypatch)
    with pytest.raises(ValidationError):
        Settings(brain_colab_lease_ttl_seconds=ttl)


@pytest.mark.parametrize("ttl", [60, 1800])
def test_colab_lease_ttl_accepts_boundaries(
    monkeypatch: pytest.MonkeyPatch, ttl: int
) -> None:
    _clear_colab_env(monkeypatch)
    settings = Settings(brain_colab_lease_ttl_seconds=ttl)
    assert settings.brain_colab_lease_ttl_seconds == ttl


@pytest.mark.parametrize("batch_size", [0, 257])
def test_colab_max_batch_size_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch, batch_size: int
) -> None:
    _clear_colab_env(monkeypatch)
    with pytest.raises(ValidationError):
        Settings(brain_colab_max_batch_size=batch_size)


@pytest.mark.parametrize("batch_size", [1, 256])
def test_colab_max_batch_size_accepts_boundaries(
    monkeypatch: pytest.MonkeyPatch, batch_size: int
) -> None:
    _clear_colab_env(monkeypatch)
    settings = Settings(brain_colab_max_batch_size=batch_size)
    assert settings.brain_colab_max_batch_size == batch_size


def test_pyproject_has_no_gpu_dependencies() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    pkg_names = {
        re.split(r"[<>=!~;\[\s]", dep.strip())[0].lower()
        for dep in deps
        if dep.strip()
    }
    assert not (pkg_names & FORBIDDEN_GPU_PACKAGES), (
        f"Forbidden GPU packages in brain production dependencies: "
        f"{sorted(pkg_names & FORBIDDEN_GPU_PACKAGES)}"
    )
