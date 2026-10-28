"""Environment configuration for the brain service.

Every variable read here is listed in plan_oracle_company_map.md §12.
Model identifiers are never default values in code; they arrive through
the environment only.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """One settings object per process, filled from the environment."""

    database_url: str | None = None
    direct_url: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    falkordb_url: str = "redis://localhost:6379"
    openrouter_api_key: str | None = None
    brain_frontier_model: str | None = None
    brain_vision_model: str | None = None
    brain_embed_model: str | None = None
    brain_embed_dims: int = 1024
    scaledown_api_key: str | None = None
    brain_scaledown_enabled: bool = False
    brain_shared_token: str | None = None
    brain_max_frontier_calls_per_job: int | None = None
    brain_interview_enabled: bool = False
    brain_interview_weekly_cap: int = 2
    brain_import_dir: str = "/data/import"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""
    return Settings()
