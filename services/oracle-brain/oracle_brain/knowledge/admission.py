"""Knowledge admission: scope-checked document intake with processing approval."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..authz import has_authority
from ..provider_policy import ProcessingApproval, ProcessingRequest, authorize


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    workspace_id: UUID
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1)


class AdmissionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    admitted: bool
    source_id: UUID
    reason: str = ""


def admit_document(
    document: SourceDocument,
    *,
    actor_id: UUID,
    database_url: str,
    approvals: list[ProcessingApproval],
    now: datetime | None = None,
) -> AdmissionDecision:
    """Admit a document if the actor has intake scope and processing is approved."""
    now = now or datetime.now(timezone.utc)
    if not has_authority(database_url, workspace_id=document.workspace_id,
                         actor_id=actor_id, scope="intake"):
        return AdmissionDecision(admitted=False, source_id=document.source_id,
                                 reason="actor lacks intake authority")
    request = ProcessingRequest(
        provider="local-synthetic",
        account="test",
        endpoint="memory://local",
        data_classes=frozenset({"document_text"}),
        purpose="pilot_ingest",
        terms_hash="0" * 64,
    )
    try:
        authorize(request, approvals, now=now)
    except PermissionError as exc:
        return AdmissionDecision(admitted=False, source_id=document.source_id,
                                 reason=str(exc))
    return AdmissionDecision(admitted=True, source_id=document.source_id)
