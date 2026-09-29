"""Pilot consultant: cited answer plus one explicitly hypothetical improvement."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from ..retrieval.pilot import RetrievedSpan


@dataclass(frozen=True)
class Citation:
    source_id: UUID
    span_start: int
    span_end: int
    quote: str


@dataclass(frozen=True)
class HypotheticalExperiment:
    label: str
    description: str
    measure: str
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PilotAnswer:
    answer_text: str
    citations: list[Citation]
    hypothetical: HypotheticalExperiment | None
    is_established_fact: bool


def answer_question(
    question: str,
    spans: list[RetrievedSpan],
    *,
    process_connections: list[dict] | None = None,
) -> PilotAnswer:
    """Produce a cited answer from retrieved spans.

    The answer distinguishes established facts (cited from source spans) from
    one explicitly hypothetical improvement experiment. When no spans support
    the question, the answer says so rather than fabricating content.
    """
    if not spans:
        return PilotAnswer(
            answer_text="No source evidence was found for this question.",
            citations=[],
            hypothetical=None,
            is_established_fact=False,
        )
    citations = [
        Citation(source_id=s.source_id, span_start=s.span_start,
                 span_end=s.span_end, quote=s.quote)
        for s in spans
    ]
    fact_lines = [f"According to the source: {s.quote}" for s in spans[:3]]
    answer_text = "\n".join(fact_lines)
    hypothetical = HypotheticalExperiment(
        label="Hypothetical improvement experiment (not established fact)",
        description=(
            "Consider testing whether consolidating sequential handoffs into a "
            "single checkpoint reduces cycle time."
        ),
        measure="Measure cycle time before and after the change over two sprints.",
        missing_inputs=["current cycle-time baseline", "team capacity data"],
    )
    return PilotAnswer(
        answer_text=answer_text,
        citations=citations,
        hypothetical=hypothetical,
        is_established_fact=True,
    )
