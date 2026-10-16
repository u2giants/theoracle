"""Knowledge admission: claim confirmation rules and document intake approval.

Pure confirmation admission (S05): a single employee confirms their own account
only; company-policy promotion respects process-owner authority; unknown
ownership is explicit and blocks confirmation; stale review submissions return a
conflict with a readable diff; correcting an assertion updates dependent
recommendation status.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..provider_policy import ProcessingApproval, ProcessingRequest, authorize

# --- Pure claim confirmation admission ---

KIND_EMPLOYEE_ACCOUNT = "employee_account"
KIND_COMPANY_POLICY = "company_policy"
KIND_UNKNOWN = "unknown"

REC_ACTIVE = "active"
REC_STALE = "stale"


@dataclass(frozen=True)
class Ownership:
    """Who owns an assertion. Unknown ownership is an explicit kind, never a guess."""

    kind: str
    owner_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.kind not in (KIND_EMPLOYEE_ACCOUNT, KIND_COMPANY_POLICY, KIND_UNKNOWN):
            raise ValueError(f"unsupported ownership kind: {self.kind}")
        if self.kind == KIND_UNKNOWN:
            if self.owner_id is not None:
                raise ValueError("unknown ownership must not name an owner")
        elif self.owner_id is None:
            raise ValueError(f"{self.kind} ownership requires an owner_id")


@dataclass(frozen=True)
class Actor:
    actor_id: UUID
    process_owner: bool = False


@dataclass(frozen=True)
class Assertion:
    assertion_id: UUID
    subject: str
    content: str
    ownership: Ownership
    version: int = 1


@dataclass(frozen=True)
class ReviewConflict:
    """Readable diff shown when a review submission is based on a stale version."""

    assertion_id: UUID
    your_version: int
    current_version: int
    diff: str


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    reason: str = ""
    conflict: ReviewConflict | None = None


@dataclass
class Recommendation:
    key: str
    text: str
    depends_on: frozenset[UUID]
    status: str = REC_ACTIVE


@dataclass
class AssertionLedger:
    """Versioned assertions with confirmation admission and correction history."""

    assertions: dict[UUID, Assertion] = field(default_factory=dict)
    history: dict[UUID, list[Assertion]] = field(default_factory=dict)
    confirmed: set[UUID] = field(default_factory=set)
    recommendations: dict[str, Recommendation] = field(default_factory=dict)

    def submit(
        self,
        subject: str,
        content: str,
        ownership: Ownership,
    ) -> Assertion:
        assertion = Assertion(uuid4(), subject, content, ownership)
        self.assertions[assertion.assertion_id] = assertion
        self.history[assertion.assertion_id] = [assertion]
        return assertion

    def add_recommendation(
        self, key: str, text: str, depends_on: frozenset[UUID]
    ) -> Recommendation:
        rec = Recommendation(key, text, depends_on)
        self.recommendations[key] = rec
        return rec

    def _stale_check(
        self, assertion: Assertion, based_on_version: int
    ) -> AdmissionResult | None:
        if based_on_version == assertion.version:
            return None
        prior = self.history[assertion.assertion_id][based_on_version - 1]
        diff = f'content: "{prior.content}" -> "{assertion.content}"'
        return AdmissionResult(
            False,
            "review submission is based on a stale version",
            ReviewConflict(
                assertion.assertion_id,
                based_on_version,
                assertion.version,
                diff,
            ),
        )

    def confirm(
        self,
        assertion_id: UUID,
        *,
        actor: Actor,
        based_on_version: int,
    ) -> AdmissionResult:
        """Confirm an assertion under its ownership rules.

        A single employee confirms their account only. Company-policy claims
        respect authority and need a process owner. Unknown ownership blocks
        confirmation until it is established explicitly.
        """
        assertion = self.assertions[assertion_id]
        stale = self._stale_check(assertion, based_on_version)
        if stale is not None:
            return stale
        ownership = assertion.ownership
        if ownership.kind == KIND_UNKNOWN:
            return AdmissionResult(
                False,
                "ownership is unknown; establish ownership before confirmation",
            )
        if ownership.kind == KIND_EMPLOYEE_ACCOUNT:
            if actor.actor_id != ownership.owner_id:
                return AdmissionResult(
                    False,
                    "only the single employee named as owner confirms their account",
                )
        elif ownership.kind == KIND_COMPANY_POLICY:
            if not actor.process_owner:
                return AdmissionResult(
                    False,
                    "company-policy confirmation requires process-owner authority",
                )
        self.confirmed.add(assertion_id)
        return AdmissionResult(True)

    def promote_to_company_policy(
        self,
        assertion_id: UUID,
        *,
        actor: Actor,
        based_on_version: int,
    ) -> AdmissionResult:
        """Promote an assertion to company policy; respects authority and bumps version."""
        assertion = self.assertions[assertion_id]
        stale = self._stale_check(assertion, based_on_version)
        if stale is not None:
            return stale
        if assertion.ownership.kind == KIND_UNKNOWN:
            return AdmissionResult(
                False,
                "ownership is unknown; establish ownership before promotion",
            )
        if not actor.process_owner:
            return AdmissionResult(
                False,
                "company-policy promotion requires process-owner authority",
            )
        updated = replace(
            assertion,
            ownership=Ownership(KIND_COMPANY_POLICY, actor.actor_id),
            version=assertion.version + 1,
        )
        self.assertions[assertion_id] = updated
        self.history[assertion_id].append(updated)
        return AdmissionResult(True)

    def correct(
        self,
        assertion_id: UUID,
        content: str,
    ) -> Assertion:
        """Correct an assertion: bump version, keep history, stale dependent recs."""
        assertion = self.assertions[assertion_id]
        updated = replace(
            assertion,
            content=content,
            version=assertion.version + 1,
        )
        self.assertions[assertion_id] = updated
        self.history[assertion_id].append(updated)
        for rec in self.recommendations.values():
            if assertion_id in rec.depends_on and rec.status == REC_ACTIVE:
                rec.status = REC_STALE
        return updated


# --- Document intake with processing approval ---


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
    from ..authz import has_authority

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
