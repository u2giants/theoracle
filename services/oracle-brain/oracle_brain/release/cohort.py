"""Pure adoption rules: mode routing, named cohort, cutover plan, watermark, writer ownership.

Fixture-only validation. No provider, credential, network, or database call lives
here; live cutover evidence is claimed elsewhere and never simulated by these DTOs.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from ..operating_model.source_receipts import _StrictModel

Oracle2Mode = Literal["off", "shadow", "pilot", "primary"]
RouteTarget = Literal["legacy", "oracle2", "shadow"]
WriterSystem = Literal["legacy", "oracle2"]
CutoverStep = Literal[
    "pause_intake",
    "drain_legacy_writers",
    "record_final_watermark",
    "apply_through_watermark",
    "reconcile",
    "transfer_writer_ownership",
    "resume_intake",
]

_CUTOVER_ORDER: tuple[CutoverStep, ...] = (
    "pause_intake",
    "drain_legacy_writers",
    "record_final_watermark",
    "apply_through_watermark",
    "reconcile",
    "transfer_writer_ownership",
    "resume_intake",
)


class CohortMembership(_StrictModel):
    """Named pilot cohort; membership is explicit and never implicit."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    cohort_name: str = Field(min_length=1)
    member_ids: tuple[UUID, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_members(self):
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("duplicate cohort member")
        return self

    def includes(self, employee_id: UUID) -> bool:
        return employee_id in self.member_ids


def route(
    mode: Oracle2Mode,
    employee_id: UUID,
    cohort: CohortMembership | None,
    *,
    employee_visible: bool = True,
    writes_old_records: bool = False,
) -> RouteTarget:
    """Server-owned dispatch. Shadow never serves employees or writes old records."""
    if mode == "off":
        return "legacy"
    if mode == "shadow":
        if employee_visible:
            raise PermissionError("shadow results cannot appear to employees")
        if writes_old_records:
            raise PermissionError("shadow results cannot write old records")
        return "shadow"
    if cohort is None:
        raise PermissionError("pilot/primary routing requires a named cohort")
    if employee_visible is False and mode != "shadow":
        # pilot/primary serve employees; a hidden path is a misconfiguration
        raise PermissionError("pilot/primary employee path must be visible")
    if mode == "pilot":
        return "oracle2" if cohort.includes(employee_id) else "legacy"
    return "oracle2"


class WatermarkBoundary(_StrictModel):
    """Final watermark W recorded at pause; reconciliation is bound to the same W."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    initial_watermark: int = Field(strict=True, ge=0)
    final_watermark: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def _monotonic(self):
        if self.final_watermark < self.initial_watermark:
            raise ValueError("final watermark precedes initial watermark")
        return self

    def covers(self, sequence: int) -> bool:
        """A change is in the applied set only when it is at or below W."""
        return sequence <= self.final_watermark


class SourceReconciliation(_StrictModel):
    """Per-source totals at the watermark boundary; counts must sum to inventory."""

    schema_version: Literal[1] = 1
    source_id: UUID
    inventory_count: int = Field(strict=True, ge=0)
    accepted_count: int = Field(strict=True, ge=0)
    quarantined_count: int = Field(strict=True, ge=0)
    excluded_count: int = Field(strict=True, ge=0)
    failed_count: int = Field(strict=True, ge=0)
    content_hash_legacy: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_hash_replacement: str = Field(pattern=r"^[0-9a-f]{64}$")
    permission_digest_legacy: str = Field(pattern=r"^[0-9a-f]{64}$")
    permission_digest_replacement: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_state_digest_legacy: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_state_digest_replacement: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _totals(self):
        parts = (
            self.accepted_count,
            self.quarantined_count,
            self.excluded_count,
            self.failed_count,
        )
        if sum(parts) != self.inventory_count:
            raise ValueError("reconciliation counts must sum to inventory")
        return self

    def unexplained_differences(self) -> int:
        n = 0
        if self.content_hash_legacy != self.content_hash_replacement:
            n += 1
        if self.permission_digest_legacy != self.permission_digest_replacement:
            n += 1
        if self.approval_state_digest_legacy != self.approval_state_digest_replacement:
            n += 1
        return n


class ReconciliationReport(_StrictModel):
    """Whole-boundary reconciliation; zero unexplained differences is required to transfer."""

    schema_version: Literal[1] = 1
    boundary: WatermarkBoundary
    sources: tuple[SourceReconciliation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _workspace_sources(self):
        ids = [s.source_id for s in self.sources]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate source reconciliation")
        return self

    @property
    def unexplained_differences(self) -> int:
        return sum(s.unexplained_differences() for s in self.sources)


class CutoverPlan(_StrictModel):
    """Ordered offline plan. Execution and live proof are not claimed by this DTO."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    cohort: CohortMembership
    steps: tuple[CutoverStep, ...] = Field(min_length=len(_CUTOVER_ORDER))
    boundary: WatermarkBoundary

    @model_validator(mode="after")
    def _steps(self):
        if self.cohort.workspace_id != self.workspace_id:
            raise ValueError("cross-workspace cohort")
        if self.boundary.workspace_id != self.workspace_id:
            raise ValueError("cross-workspace boundary")
        if self.steps[: len(_CUTOVER_ORDER)] != _CUTOVER_ORDER:
            raise ValueError("cutover steps out of order")
        return self

    def permits_ownership_transfer(self, report: ReconciliationReport) -> bool:
        if report.boundary != self.boundary:
            return False
        return report.unexplained_differences == 0


class QueueReceipt(_StrictModel):
    """Durable intake during the pause; one idempotency key maps to one receipt."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    idempotency_key: str = Field(min_length=1)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class IntakeQueue(_StrictModel):
    """In-memory fixture of the durable queue; production storage is elsewhere."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    paused: bool = False
    receipts: tuple[QueueReceipt, ...] = ()

    def arrive(self, idempotency_key: str, payload_digest: str) -> QueueReceipt:
        for prior in self.receipts:
            if prior.idempotency_key == idempotency_key:
                if prior.payload_digest != payload_digest:
                    raise ValueError("idempotency key reuse with different payload")
                return prior
        receipt = QueueReceipt(
            workspace_id=self.workspace_id,
            idempotency_key=idempotency_key,
            payload_digest=payload_digest,
        )
        object.__setattr__(self, "receipts", self.receipts + (receipt,))
        return receipt


class WriterOwnership(_StrictModel):
    """One system owns each ingestion event; generation is the fence."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    owner: WriterSystem
    generation: int = Field(strict=True, ge=1)
    intake_open: bool = True

    def claim_write(self, claimed_generation: int) -> None:
        if not self.intake_open:
            raise PermissionError("intake is paused; queue the request instead")
        if claimed_generation != self.generation:
            raise PermissionError("expired writer generation denied")

    def pause(self) -> "WriterOwnership":
        return self.model_copy(update={"intake_open": False})

    def transfer(self, report: ReconciliationReport, *, expected_generation: int) -> "WriterOwnership":
        """Atomic ownership switch only after zero unexplained differences at W."""
        if self.intake_open:
            raise PermissionError("ownership transfer requires paused intake")
        if self.generation != expected_generation:
            raise PermissionError("serving writer generation moved concurrently")
        if report.unexplained_differences != 0:
            raise PermissionError("unexplained reconciliation differences block ownership transfer")
        return self.model_copy(
            update={
                "owner": "oracle2" if self.owner == "legacy" else "legacy",
                "generation": self.generation + 1,
                "intake_open": True,
            }
        )

    def abort_to_legacy(self, *, expected_generation: int) -> "WriterOwnership":
        """Rollback: restore legacy intake; never serve a partially caught-up corpus."""
        if self.generation != expected_generation:
            raise PermissionError("serving writer generation moved concurrently")
        return self.model_copy(update={"owner": "legacy", "generation": self.generation + 1, "intake_open": True})
