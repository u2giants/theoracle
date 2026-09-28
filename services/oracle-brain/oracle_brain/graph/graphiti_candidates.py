"""Candidate-only Graphiti boundary; evidence spans remain Oracle-owned."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from oracle_brain.contracts import CandidateAssertion, CandidateBundle, SourceSpan


class ExtractedRelation(BaseModel):
    """Supported public fields only; no Graphiti edge internal state."""
    subject: str
    predicate: str
    object: str
    quote: str
    start: int
    end: int
    confidence: float


def candidate_bundle(*, workspace_id: UUID, run_id: UUID, source_id: UUID,
                     source_revision: int, source_text: str,
                     relations: list[ExtractedRelation]) -> CandidateBundle:
    """Reject invented spans; never accept a model's quote as evidence alone."""
    assertions = []
    for index, relation in enumerate(relations):
        if (relation.start < 0 or relation.end > len(source_text)
            or relation.end <= relation.start
            or source_text[relation.start:relation.end] != relation.quote):
            raise ValueError("relation lacks exact source-span attribution")
        from uuid import uuid5, NAMESPACE_URL
        assertion_id = uuid5(NAMESPACE_URL, f"{workspace_id}/{source_id}/{source_revision}/{index}/{relation.quote}")
        assertions.append(CandidateAssertion(
            assertion_id=assertion_id, subject=relation.subject,
            predicate=relation.predicate, object=relation.object,
            confidence=relation.confidence,
            span=SourceSpan(source_id=source_id, source_revision=source_revision,
                            start=relation.start, end=relation.end, quote=relation.quote),
        ))
    return CandidateBundle(workspace_id=workspace_id, run_id=run_id,
                           source_id=source_id, source_revision=source_revision,
                           assertions=assertions)
