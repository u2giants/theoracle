"""U4/U5 pure DTO validation for append-only correction and scoped confirmation.

Offline pieces only: no database, no authority grant, no serving grant, no
provider call. U4 correction is append-only authenticated ORIGINAL user
evidence bound to an exact edge/base artifact/hash and SourceRefs, producing a
genuinely NEW independently admitted candidate with the same model UUID and
the next version. A user correction is not automatically truth. U5 scoped
confirmation pins an exact map/version/hash/workflow/reviewer scope; explicit
withdrawal or current reviewer-leaf revocation removes the CURRENT badge while
history remains, and confirmation never grants serving.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ..operating_model.contracts import StrictRecord
from ..operating_model.source_receipts import SourceRef

HASH = r'^[0-9a-f]{64}$'


class UserEvidenceV1(StrictRecord):
    """ORIGINAL user evidence. Bound to an exact SourceRef span; never truth."""

    schema_version: Literal[1] = 1
    ref: SourceRef
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    principal_role: Literal['original-user'] = 'original-user'

    @model_validator(mode='after')
    def _span(self) -> 'UserEvidenceV1':
        if self.end <= self.start:
            raise ValueError('evidence end must be greater than start')
        return self


class CorrectionCandidateSubmissionV1(StrictRecord):
    """U4: append-only correction input; yields a NEW candidate, not an edit.

    This DTO validates shape and refusal rules only. Independent admission of
    the resulting candidate is a separate act; `truth_status` is fixed to
    unadmitted-user-evidence so a user correction can never claim truth here.
    """

    schema_version: Literal[1] = 1
    workspace_id: UUID
    actor_id: UUID
    model_id: UUID
    base_artifact_id: UUID
    base_version: int = Field(ge=1)
    base_content_hash: str = Field(pattern=HASH)
    next_version: int = Field(ge=2)
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    evidence: tuple[UserEvidenceV1, ...] = Field(min_length=1)
    correction_text: str = Field(min_length=1)
    targets_admitted_content: bool = False
    patches_historical_review: bool = False
    bypasses_source_population: bool = False
    truth_status: Literal['unadmitted-user-evidence'] = 'unadmitted-user-evidence'

    @field_validator('actor_id')
    @classmethod
    def _actor_present(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError('authenticated actor_id required')
        return value

    @model_validator(mode='after')
    def _append_only_new_candidate(self) -> 'CorrectionCandidateSubmissionV1':
        if self.targets_admitted_content:
            raise ValueError('immutable admitted content cannot be edited; submit a NEW candidate')
        if self.patches_historical_review:
            raise ValueError('historical review cannot be patched by a correction')
        if self.bypasses_source_population:
            raise ValueError('correction cannot bypass source population completeness')
        if self.next_version != self.base_version + 1:
            raise ValueError('next_version must be the exact next version of the base')
        seen = set()
        for ref in self.source_refs:
            if ref.workspace_id != self.workspace_id:
                raise ValueError('every SourceRef must belong to the submission workspace')
            if ref.source_id in seen:
                raise ValueError('SourceRefs must be distinct')
            seen.add(ref.source_id)
        for item in self.evidence:
            if item.ref.workspace_id != self.workspace_id:
                raise ValueError('evidence SourceRef must belong to the submission workspace')
            if item.ref.source_id not in seen:
                raise ValueError('evidence must bind an exact listed SourceRef')
        return self

    @property
    def is_truth(self) -> bool:
        return False

    @property
    def candidate_identity(self) -> tuple[UUID, int]:
        """Same model UUID, next version — a NEW candidate identity."""
        return (self.model_id, self.next_version)


class ScopedConfirmationV1(StrictRecord):
    """U5: exact map/version/hash/workflow/reviewer scope. Never serving."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    actor_id: UUID
    model_id: UUID
    map_version: int = Field(ge=1)
    map_hash: str = Field(pattern=HASH)
    artifact_id: UUID
    artifact_version: int = Field(ge=1)
    artifact_content_hash: str = Field(pattern=HASH)
    workflow_id: str = Field(min_length=1)
    reviewer_scope: Literal['process-map', 'review', 'confirm']
    reviewer_appointment_id: UUID
    reviewer_leaf_current: bool
    withdrawn: bool = False
    grants_serving: Literal[False] = False

    @field_validator('actor_id', 'reviewer_appointment_id')
    @classmethod
    def _nonzero(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError('nonzero identity required')
        return value

    @property
    def current_badge(self) -> bool:
        """CURRENT badge only while not withdrawn and reviewer-leaf is current."""
        return (not self.withdrawn) and self.reviewer_leaf_current

    @property
    def serving_granted(self) -> bool:
        return False

    def badge_after_withdrawal(self) -> 'ScopedConfirmationV1':
        """Withdrawal removes CURRENT badge; history is retained by the caller."""
        return self.model_copy(update={'withdrawn': True})

    def badge_after_reviewer_revocation(self) -> 'ScopedConfirmationV1':
        """Current reviewer-leaf revocation removes CURRENT badge; history remains."""
        return self.model_copy(update={'reviewer_leaf_current': False})


class ConfirmationHistoryEntryV1(StrictRecord):
    """Append-only history record; retained even after badge removal."""

    schema_version: Literal[1] = 1
    confirmation: ScopedConfirmationV1
    badge_was_current: bool
    removed_reason: Literal['none', 'withdrawn', 'reviewer-leaf-revoked'] = 'none'
