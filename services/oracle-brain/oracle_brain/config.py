"""Fail-closed runtime configuration. No production defaults or shared keys."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID


@dataclass(frozen=True)
class Settings:
    mode: str
    environment: str
    database_url: str
    candidate_graph_url: str | None
    confirmed_graph_url: str | None
    blob_endpoint: str | None
    workspace_allowlist: frozenset[str]
    daily_budget: int | None

    @classmethod
    def from_env(cls, role: str) -> "Settings":
        if role not in {"extractor", "projector", "test"}:
            raise ValueError("invalid runtime role")
        mode = os.getenv("ORACLE2_MODE", "synthetic")
        environment = os.getenv("ORACLE2_ENVIRONMENT", "local")
        if mode not in {"synthetic", "approved_real"}:
            raise ValueError("invalid mode")
        if environment not in {"local", "test", "preview", "production"}:
            raise ValueError("invalid environment")
        database_url = os.getenv("ORACLE2_DATABASE_URL", "")
        candidate_graph_url = os.getenv("ORACLE2_CANDIDATE_GRAPH_URL")
        confirmed_graph_url = os.getenv("ORACLE2_CONFIRMED_GRAPH_URL")
        blob_endpoint = os.getenv("ORACLE2_BLOB_ENDPOINT")
        if not database_url:
            raise ValueError("missing isolated database URL")
        if role == "extractor" and confirmed_graph_url:
            raise ValueError("extractor must never receive confirmed graph credentials")
        if role == "projector" and candidate_graph_url:
            raise ValueError("projector must never receive candidate graph credentials")
        if role in {"extractor", "projector"} and os.getenv("ORACLE2_CHECKPOINT_DATABASE_URL"):
            raise ValueError("graph workers must not receive checkpoint credentials")
        if role == "extractor" and not candidate_graph_url:
            raise ValueError("missing candidate graph URL")
        if role == "projector" and not confirmed_graph_url:
            raise ValueError("missing confirmed graph URL")
        if environment in {"local", "test"}:
            for value in (database_url, candidate_graph_url, confirmed_graph_url, blob_endpoint):
                if value and urlparse(value).hostname not in {"localhost", "127.0.0.1", "postgres", "falkor-candidate", "falkor-confirmed", "object-store"}:
                    raise ValueError("local/test store points outside isolated network")
            if mode != "synthetic":
                raise ValueError("local/test mode is synthetic only")
        else:
            for value in (database_url, candidate_graph_url, confirmed_graph_url):
                if value and not urlparse(value).password:
                    raise ValueError("nonlocal store URL must carry its own credential")
        try:
            allowlist = frozenset(str(UUID(value.strip())) for value in
                                  os.getenv("ORACLE2_WORKSPACE_ALLOWLIST", "").split(",")
                                  if value.strip())
        except ValueError as exc:
            raise ValueError("workspace allowlist must contain UUIDs") from exc
        budget_raw = os.getenv("ORACLE2_DAILY_BUDGET")
        budget = int(budget_raw) if budget_raw else None
        if environment not in {"local", "test"} and (not allowlist or not budget or budget <= 0):
            raise ValueError("nonlocal runtime needs workspace allowlist and budget")
        if os.getenv("ORACLE2_TELEMETRY_MODE", "off") != "off":
            raise ValueError("Oracle 2 telemetry must be off")
        os.environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"
        return cls(mode, environment, database_url, candidate_graph_url, confirmed_graph_url,
                   blob_endpoint, allowlist, budget)
