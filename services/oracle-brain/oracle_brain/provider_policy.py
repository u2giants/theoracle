"""Default-deny outbound processing admission and redacted telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProcessingApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    account: str
    endpoint: str
    data_classes: frozenset[str]
    purpose: str
    terms_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    register_ref: str
    fallback: bool = False


class ProcessingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    account: str
    endpoint: str
    data_classes: frozenset[str]
    purpose: str
    terms_hash: str
    fallback: bool = False


def authorize(request: ProcessingRequest, approvals: list[ProcessingApproval],
              *, now: datetime | None = None) -> ProcessingApproval:
    now = now or datetime.now(timezone.utc)
    for approval in approvals:
        if (approval.provider == request.provider and approval.account == request.account
            and approval.endpoint == request.endpoint and approval.purpose == request.purpose
            and approval.terms_hash == request.terms_hash
            and request.data_classes <= approval.data_classes
            and request.fallback == approval.fallback and approval.expires_at > now):
            return approval
    raise PermissionError("no current processing approval for exact request")


def dispatch(request: ProcessingRequest, approvals: list[ProcessingApproval],
             sender: Callable[[], object]) -> object:
    authorize(request, approvals)
    return sender()


def safe_telemetry(metadata: dict) -> dict:
    allowed = {"run_id", "provider", "model", "status", "elapsed_ms", "token_count"}
    if set(metadata) - allowed:
        raise ValueError("telemetry contains unapproved fields")
    if "run_id" in metadata:
        try:
            UUID(str(metadata["run_id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("invalid telemetry run ID") from exc
    for key in ("provider", "model"):
        if key in metadata and (not isinstance(metadata[key], str)
                                or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", metadata[key])):
            raise ValueError(f"invalid telemetry {key}")
    if "status" in metadata and metadata["status"] not in {"started", "passed", "failed", "denied"}:
        raise ValueError("invalid telemetry status")
    for key in ("elapsed_ms", "token_count"):
        if key in metadata and (not isinstance(metadata[key], int) or isinstance(metadata[key], bool)
                                or metadata[key] < 0 or metadata[key] > 1_000_000_000):
            raise ValueError(f"invalid telemetry {key}")
    return dict(metadata)
