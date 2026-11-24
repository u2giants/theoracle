"""Environment configuration for the brain service.

Every variable read here is listed in plan_oracle_company_map.md §12.
Model identifiers are never default values in code; they arrive through
the environment only.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
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
    # Direct OpenAI API key (#607 step 2.4 native /v1/batches + openai-api/* routes).
    # BRAIN_OPENAI_API_KEY overrides OPENAI_API_KEY when set; missing key falls back
    # to the synchronous OpenRouter path with a warning.
    openai_api_key: str | None = None
    brain_openai_api_key: str | None = None
    brain_relations_batch_enabled: bool = True
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
    # Message-source relations model (plan_pm_message_intake.md step 2.3, #607).
    # Used for sources with origin IS NOT NULL when set or seated on relations_messages.
    brain_message_relations_model: str | None = None
    # Pre-ingest thread business-relevance gate model (#607 phase 1).
    brain_intake_gate_model: str | None = None
    brain_intake_gate_batch_enabled: bool = True
    brain_vision_model: str | None = None
    brain_embed_model: str | None = None
    brain_embed_dims: int = 1024
    scaledown_api_key: str | None = None
    brain_scaledown_enabled: bool = False
    # Business-area sorting on message-intake passages (#607 step 2.5).
    # Default off: ScaleDown /classify missed the step 2.5 precision/recall gates, so
    # message sources default to the step 2.3 winner (relations_messages) rather than
    # ScaleDown or any frontier model (L9).
    brain_scaledown_function_assign_enabled: bool = False
    brain_scaledown_function_threshold: float = 0.1
    brain_scaledown_function_multi_label: bool = False
    brain_message_function_model: str | None = None
    brain_shared_token: str | None = None
    brain_max_frontier_calls_per_job: int | None = None
    # Hard token ceiling for one answer's assembled context (repair C4).
    # The answer never exceeds it; ScaleDown compression is optional only.
    brain_answer_context_tokens: int = 12000
    # Delete reports superseded more than one build ago at the end of each
    # successful community build (repair plan A1). Off keeps every old report.
    brain_community_prune_enabled: bool = True
    brain_interview_enabled: bool = False
    brain_interview_weekly_cap: int = 2
    # Rollback switch for the interview fast lane (#604 plan Step 4). Off sends
    # every job to the main lane and starts only the main worker.
    brain_interview_lane_enabled: bool = True
    # Database pool size (#604 plan Step 4): two worker lanes each fan out to
    # several threads, and the API shares the pool.
    brain_db_pool_size: int = 12
    brain_web_base_url: str | None = None
    brain_import_dir: str = "/data/import"
    # Project-manager message intake (plan_pm_message_intake.md). Intake
    # refuses to start without a spend cap (step 0.1 gate).
    brain_intake_enabled: bool = False
    brain_intake_max_usd: float | None = None
    clickup_api_token: str | None = None
    # DesignFlow people/roles directory sync (DECISIONS.md
    # D-dflow-directory-source-of-truth). Off until both the flag and the
    # second-database URL are set.
    dflow_directory_sync_enabled: bool = False
    dflow_directory_database_url: str | None = None
    # Google Colab batch offload (plan_colab_gpu_offload.md Step 0.2).
    # Dedicated bearer token for /colab/*; never reuse brain_shared_token.
    brain_colab_worker_token: str | None = None
    brain_colab_lease_enabled: bool = False
    brain_colab_lease_ttl_seconds: int = 900
    brain_colab_max_batch_size: int = 64

    @field_validator("brain_colab_lease_ttl_seconds")
    @classmethod
    def _validate_colab_lease_ttl_seconds(cls, v: int) -> int:
        if not 60 <= v <= 1800:
            raise ValueError("brain_colab_lease_ttl_seconds must be between 60 and 1800")
        return v

    @field_validator("brain_colab_max_batch_size")
    @classmethod
    def _validate_colab_max_batch_size(cls, v: int) -> int:
        if not 1 <= v <= 256:
            raise ValueError("brain_colab_max_batch_size must be between 1 and 256")
        return v


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""
    return Settings()


def intake_spend_cap(settings: Settings) -> float:
    """BRAIN_INTAKE_MAX_USD; raise if unset or not positive (no intake run without a cap)."""
    cap = settings.brain_intake_max_usd
    if cap is None or cap <= 0:
        raise RuntimeError(
            "BRAIN_INTAKE_MAX_USD must be set to a positive dollar cap before intake runs"
        )
    return cap


def chat_model(settings: Settings) -> str | None:
    """Model for human-facing conversation: BRAIN_CHAT_MODEL, else the frontier model."""
    return settings.brain_chat_model or settings.brain_frontier_model


def flat_model(settings: Settings) -> str | None:
    """Model for flat extraction: BRAIN_FLAT_MODEL, else the frontier model."""
    return settings.brain_flat_model or settings.brain_frontier_model


def eval_model(settings: Settings) -> str | None:
    """Model that grades eval answers: BRAIN_EVAL_MODEL, else the frontier model."""
    return settings.brain_eval_model or settings.brain_frontier_model


def openai_api_key(settings: Settings) -> str | None:
    """Direct OpenAI API key: BRAIN_OPENAI_API_KEY, else OPENAI_API_KEY."""
    return settings.brain_openai_api_key or settings.openai_api_key
