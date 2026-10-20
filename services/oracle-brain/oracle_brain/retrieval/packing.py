"""Role/workspace access filter, history span filter and coverage-bound answers.

Pure assembly from fixture evidence spans. Missing evidence abstains. No
company-wide claim is produced without explicit coverage bounds. Complete
aggregate totals are never claimed from partial or top-k evidence. Exceptions
and contradictions are carried as labels, never dropped.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from ..operating_model.source_receipts import _StrictModel
from .planner import AccessBounds, HistorySpan, RetrievalMode

AnswerState = Literal["answered", "abstained", "needs_clarification"]


class SpanCandidate(_StrictModel):
    """One fixture evidence span with the bounds assembly must honor."""
    span_id: str = Field(min_length=1, max_length=200)
    workspace_id: UUID
    source_id: UUID
    revision: int = Field(strict=True, ge=1)
    quote: str = Field(min_length=1)
    roles: tuple[str, ...] = Field(min_length=1)
    supports: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()


class CoverageBounds(_StrictModel):
    """Explicit coverage for global answers; never inferred from hit count."""
    declared_population: int = Field(strict=True, ge=1)
    represented: int = Field(strict=True, ge=0)
    complete: bool

    @model_validator(mode="after")
    def _represented_within_population(self) -> "CoverageBounds":
        if self.represented > self.declared_population:
            raise ValueError("represented cannot exceed declared_population")
        if self.complete and self.represented != self.declared_population:
            raise ValueError("complete coverage requires full representation")
        return self


class AssembledAnswer(_StrictModel):
    schema_version: Literal[1] = 1
    state: AnswerState
    mode: RetrievalMode
    question: str = Field(min_length=1, max_length=4000)
    claim: str | None = None
    citations: tuple[str, ...] = ()
    coverage: CoverageBounds | None = None
    caveats: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    clarifying_question: str | None = None

    @model_validator(mode="after")
    def _state_shape(self) -> "AssembledAnswer":
        if self.state == "answered":
            if not self.claim:
                raise ValueError("answered requires a claim")
            if not self.citations:
                raise ValueError("answered requires citations")
            if self.clarifying_question:
                raise ValueError("clarifying_question only on needs_clarification")
        elif self.state == "abstained":
            if self.claim or self.citations:
                raise ValueError("abstained carries no claim or citations")
            if self.clarifying_question:
                raise ValueError("clarifying_question only on needs_clarification")
        else:
            if self.claim or self.citations:
                raise ValueError("needs_clarification carries no claim or citations")
            if not self.clarifying_question:
                raise ValueError("needs_clarification requires clarifying_question")
        if self.mode == "global" and self.state == "answered" and self.coverage is None:
            raise ValueError("global answers require explicit coverage bounds")
        return self


def filter_by_access(
    spans: tuple[SpanCandidate, ...] | list[SpanCandidate],
    access: AccessBounds,
) -> tuple[SpanCandidate, ...]:
    """Keep only spans inside the role and workspace bounds."""
    allowed = set(access.allowed_workspace_ids)
    return tuple(
        span for span in spans
        if span.workspace_id in allowed and access.role in span.roles
    )


def filter_by_history(
    spans: tuple[SpanCandidate, ...] | list[SpanCandidate],
    history: HistorySpan,
) -> tuple[SpanCandidate, ...]:
    """Keep only spans whose revision falls inside the closed history window."""
    return tuple(span for span in spans if history.contains(span.revision))


def assemble_answer(
    *,
    question: str,
    mode: RetrievalMode,
    spans: tuple[SpanCandidate, ...] | list[SpanCandidate],
    access: AccessBounds,
    history: HistorySpan | None = None,
    coverage: CoverageBounds | None = None,
    claim: str | None = None,
    clarifying_question: str | None = None,
) -> AssembledAnswer:
    """Assemble a coverage-honest answer from fixture evidence under bounds.

    Order of operations: access filter first, then the history window when the
    mode is historical. Missing evidence abstains. Global claims without
    coverage bounds abstain. Partial coverage is labeled, never sold as a
    complete total. Contradictions are labeled and retained.
    """
    if not question.strip():
        raise ValueError("question must be non-empty")
    if mode == "historical" and history is None:
        return AssembledAnswer(
            state="needs_clarification", mode=mode, question=question,
            clarifying_question=(
                "Which revision range should the historical answer cover? "
                "Provide revision_from and revision_to."
            ),
        )
    if mode != "historical" and history is not None:
        raise ValueError("HistorySpan only applies to historical retrieval")

    visible = filter_by_access(spans, access)
    if mode == "historical" and history is not None:
        visible = filter_by_history(visible, history)

    if clarifying_question is not None and not visible:
        return AssembledAnswer(
            state="needs_clarification", mode=mode, question=question,
            clarifying_question=clarifying_question,
        )

    if not visible:
        return AssembledAnswer(
            state="abstained", mode=mode, question=question,
            caveats=("Missing evidence under current role/workspace/access bounds.",),
        )

    if mode == "global" and coverage is None:
        return AssembledAnswer(
            state="abstained", mode=mode, question=question,
            caveats=(
                "No company-wide claim without explicit coverage bounds.",
                "Missing evidence must abstain.",
            ),
        )

    supported = {key for span in visible for key in span.supports}
    contradicted = {key for span in visible for key in span.contradicts}
    conflict_keys = sorted(supported & contradicted)
    labels: list[str] = []
    caveats: list[str] = []
    if conflict_keys:
        labels.append("contradiction")
        caveats.append(
            "Contradictory evidence retained and labeled for: "
            + ", ".join(conflict_keys)
            + "."
        )

    caveats.append(
        "Answers are generated only from bounded evidence spans; "
        "unsupported causal links remain labeled and are not asserted."
    )

    if coverage is not None:
        if not coverage.complete:
            caveats.append(
                f"Coverage is partial ({coverage.represented} of "
                f"{coverage.declared_population} in the declared population); "
                "this is not a complete aggregate total."
            )
            labels.append("partial_coverage")
        else:
            caveats.append(
                f"Coverage bounds: {coverage.represented} of "
                f"{coverage.declared_population} in the declared population."
            )

    if not claim:
        return AssembledAnswer(
            state="abstained", mode=mode, question=question,
            coverage=coverage, caveats=tuple(caveats), labels=tuple(labels),
        )

    return AssembledAnswer(
        state="answered", mode=mode, question=question,
        claim=claim,
        citations=tuple(span.span_id for span in visible),
        coverage=coverage,
        caveats=tuple(caveats),
        labels=tuple(labels),
    )
