"""Environment configuration for the brain service.

Every variable read here is listed in plan_oracle_company_map.md §12.
Model identifiers are never default values in code; they arrive through
the environment only.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """One settings object per process, filled from the environment."""

    # Compose passes unset variables as empty strings; treat them as unset.
    model_config = SettingsConfigDict(env_ignore_empty=True)

    database_url: str | None = None
    direct_url: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    falkordb_url: str = "redis://localhost:6379"
    openrouter_api_key: str | None = None
    # Direct Meta (Muse) API key. Model ids starting with ``meta-model-api/``
    # route here instead of OpenRouter (issue #426).
    brain_meta_api_key: str | None = None
    brain_frontier_model: str | None = None
    # Human-facing conversation (question answers). Falls back to the frontier model.
    brain_chat_model: str | None = None
    # Eval grader; keep it fixed across runs so scores stay comparable.
    brain_eval_model: str | None = None
    # Flat entity pickup. When set, it extracts every chunk (ScaleDown still
    # classifies); unset keeps ScaleDown /extract with the frontier fallback.
    # Flat extraction model. When set it extracts every non-chatter chunk (ScaleDown
    # still classifies), and each call counts against BRAIN_MAX_FRONTIER_CALLS_PER_JOB,
    # so size that cap to at least the chunk count of the largest job.
    brain_flat_model: str | None = None
    # Contradiction classifier (repair D3). Falls back to the frontier model.
    brain_contradictions_model: str | None = None
    brain_vision_model: str | None = None
    brain_embed_model: str | None = None
    brain_embed_dims: int = 1024
    scaledown_api_key: str | None = None
    brain_scaledown_enabled: bool = False
    brain_shared_token: str | None = None
    brain_max_frontier_calls_per_job: int | None = None
    # Delete reports superseded more than one build ago at the end of each
    # successful community build (repair plan A1). Off keeps every old report.
    brain_community_prune_enabled: bool = True
    brain_interview_enabled: bool = False
    brain_interview_weekly_cap: int = 2
    brain_web_base_url: str | None = None
    brain_import_dir: str = "/data/import"
    # DesignFlow people/roles directory sync (DECISIONS.md
    # D-dflow-directory-source-of-truth). Off until both the flag and the
    # second-database URL are set.
    dflow_directory_sync_enabled: bool = False
    dflow_directory_database_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""
    return Settings()


def chat_model(settings: Settings) -> str | None:
    """Model for human-facing conversation: BRAIN_CHAT_MODEL, else the frontier model."""
    return settings.brain_chat_model or settings.brain_frontier_model


def flat_model(settings: Settings) -> str | None:
    """Model for flat extraction: BRAIN_FLAT_MODEL, else the frontier model."""
    return settings.brain_flat_model or settings.brain_frontier_model


def eval_model(settings: Settings) -> str | None:
    """Model that grades eval answers: BRAIN_EVAL_MODEL, else the frontier model."""
    return settings.brain_eval_model or settings.brain_frontier_model
