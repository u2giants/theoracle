"""Role/workspace access filter, history span filter and coverage-bound answers.

Pure assembly from fixture evidence spans. Missing evidence abstains. No
company-wide claim is produced without explicit coverage bounds. Complete
aggregate totals are never claimed from partial or top-k evidence. Exceptions
and contradictions are carried as labels, never dropped.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from secrets import token_hex
from typing import Callable, Literal
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


class SourceDependency(_StrictModel):
    """Immutable exact-content dependency; identifiers alone never prove text."""
    workspace_id: UUID
    source_id: UUID
    revision: int = Field(strict=True, ge=1)
    span_id: str
    quote_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class CurrentSourceAccess(_StrictModel):
    dependency: SourceDependency
    actor_id: UUID
    role: str
    permitted: bool
    challenge: str
    valid_until: float
    mac: str


SOURCE_ACCESS_PURPOSE = 'retrieval-source-current:v1'
CurrentSourceReader = Callable[[SourceDependency, AccessBounds, str], CurrentSourceAccess]


def dependency_for(span: SpanCandidate) -> SourceDependency:
    return SourceDependency(workspace_id=span.workspace_id, source_id=span.source_id,
                            revision=span.revision, span_id=span.span_id,
                            quote_sha256=hashlib.sha256(span.quote.encode()).hexdigest())


def current_source_payload(proof: CurrentSourceAccess) -> str:
    return json.dumps(proof.model_dump(mode='json', exclude={'mac'}),
                      sort_keys=True, separators=(',', ':'), allow_nan=False)


def current_supported_spans(spans, access: AccessBounds,
                            current_source_reader: CurrentSourceReader | None):
    """Final independent current-access proof for each retained dependency."""
    from oracle_brain.seal import verify_mac
    if current_source_reader is None or access.actor_id is None:
        return ()
    retained = []
    seen = set()
    for span in filter_by_access(spans, access):
        dependency = dependency_for(span)
        identity = (dependency.workspace_id, dependency.source_id,
                    dependency.revision, dependency.span_id, dependency.quote_sha256)
        if identity in seen:
            continue
        challenge = token_hex(32)
        try:
            proof = current_source_reader(dependency, access, challenge)
            if (type(proof) is not CurrentSourceAccess or proof.dependency != dependency
                    or proof.actor_id != access.actor_id or proof.role != access.role
                    or proof.permitted is not True or proof.challenge != challenge
                    or not math.isfinite(proof.valid_until)
                    or not time.time() < proof.valid_until <= time.time() + 60):
                continue
            verify_mac(SOURCE_ACCESS_PURPOSE, proof.mac, current_source_payload(proof))
        except Exception:
            # An unavailable/denied source cannot contribute text or citations.
            continue
        retained.append((span, dependency))
        seen.add(identity)
    return tuple(retained)


class CoverageBounds(_StrictModel):
    """Explicit coverage for global answers; never inferred from hit count."""
    declared_population: int = Field(strict=True, ge=1)
    represented: int | None = Field(strict=True, ge=0)
    complete: bool

    @model_validator(mode="after")
    def _represented_within_population(self) -> "CoverageBounds":
        if self.represented is not None and self.represented > self.declared_population:
            raise ValueError("represented cannot exceed declared_population")
        if self.complete and self.represented != self.declared_population:
            raise ValueError("complete coverage requires full representation")
        return self


def coverage_after_access(coverage, required_dependencies, authorized_dependencies, *, missing_support=False):
    """A pruned source does not establish how many business units remain.

    Keep the declared population boundary, but the represented population is
    UNKNOWN after support loss. Source-span counts are not business counts.
    """
    if coverage is None:
        return None
    required = {dep.model_dump_json() for dep in required_dependencies}
    authorized = {dep.model_dump_json() for dep in authorized_dependencies}
    if missing_support or required != authorized:
        return coverage.model_copy(update={'represented': None, 'complete': False})
    return coverage


class AssembledAnswer(_StrictModel):
    schema_version: Literal[1] = 1
    state: AnswerState
    mode: RetrievalMode
    question: str = Field(min_length=1, max_length=4000)
    claim: str | None = None
    citations: tuple[str, ...] = ()
    dependencies: tuple[SourceDependency, ...] = ()
    coverage: CoverageBounds | None = None
    caveats: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    clarifying_question: str | None = None

    @model_validator(mode="after")
    def _state_shape(self) -> "AssembledAnswer":
        if self.state == "answered":
            if not self.claim:
                raise ValueError("answered requires a claim")
            if not self.citations or not self.dependencies:
                raise ValueError("answered requires citations and dependencies")
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
    current_source_reader: CurrentSourceReader | None = None,
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

    required_spans = tuple(spans)
    if mode == "historical" and history is not None:
        required_spans = filter_by_history(required_spans, history)
    required_dependencies = tuple(dependency_for(span) for span in required_spans)
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
            coverage=coverage_after_access(coverage, required_dependencies, (), missing_support=True),
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

    current = current_supported_spans(visible, access, current_source_reader)
    coverage = coverage_after_access(coverage, required_dependencies,
                                     tuple(dep for _, dep in current), missing_support=not current)
    if not current:
        return AssembledAnswer(
            state="abstained", mode=mode, question=question,
            coverage=coverage, caveats=("No currently authorized source support.",),
        )
    visible = tuple(span for span, _ in current)

    supported = {key for span in visible for key in span.supports}
    contradicted = {key for span in visible for key in span.contradicts}
    conflict_keys = sorted(supported & contradicted)
    labels: list[str] = []
    caveats: list[str] = []
    if conflict_keys:
        labels.append("contradiction")
        caveats.append(
            "Contradictory evidence retained and labeled; candidate relation "
            "labels do not establish an unsupported claim."
        )

    caveats.append(
        "Answers are generated only from bounded evidence spans; "
        "unsupported causal links remain labeled and are not asserted."
    )

    if coverage is not None:
        if not coverage.complete:
            if coverage.represented is None:
                caveats.append("Represented population is UNKNOWN after unavailable source support; "
                               "source dependency counts do not determine business population coverage.")
            caveats.append(
                f"Coverage is partial ({coverage.represented if coverage.represented is not None else 'UNKNOWN'} of "
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

    # The caller's claim is a query/selector, never returned evidence. Build
    # extractive text only from exact current-accessible source quotes.
    return AssembledAnswer(
        state="answered", mode=mode, question=question,
        claim="\n".join(span.quote for span, _ in current),
        citations=tuple(span.span_id for span, _ in current),
        dependencies=tuple(dependency for _, dependency in current),
        coverage=coverage,
        caveats=tuple(caveats),
        labels=tuple(labels),
    )
