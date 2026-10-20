"""Quote-level entailment contract for citations; pure, fixture-only.

A citation is valid only when (1) the quoted span matches the source text at
its declared offsets and (2) the quote entails the claim. Unsupported claim
content is rejected — never carried as a soft caveat. No provider calls.
"""
from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from ..operating_model.source_receipts import _StrictModel

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
        "was", "were", "with",
    }
)


def content_tokens(text: str) -> frozenset[str]:
    """Lowercase alphanumeric tokens minus stopwords; the entailment unit."""
    return frozenset(
        token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS
    )


class QuoteCitation(_StrictModel):
    """One quote-level citation: exact span offsets into one source."""
    schema_version: Literal[1] = 1
    source_id: UUID
    span_start: int = Field(strict=True, ge=0)
    span_end: int = Field(strict=True, gt=0)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered_span(self) -> "QuoteCitation":
        if self.span_end <= self.span_start:
            raise ValueError("span_end must be greater than span_start")
        return self


class SourceText(_StrictModel):
    """Fixture source text a citation must align to."""
    schema_version: Literal[1] = 1
    source_id: UUID
    text: str = Field(min_length=1)


class EntailmentResult(_StrictModel):
    """Verdict for one citation against one claim."""
    schema_version: Literal[1] = 1
    valid: bool
    reason: str
    claim: str = Field(min_length=1)
    citation: QuoteCitation


class EntailmentReport(_StrictModel):
    """Aggregate verdict: every citation must validate for the claim."""
    schema_version: Literal[1] = 1
    valid: bool
    claim: str = Field(min_length=1)
    accepted: tuple[EntailmentResult, ...] = ()
    rejected: tuple[EntailmentResult, ...] = ()


def _source_index(
    sources: tuple[SourceText, ...] | list[SourceText],
) -> dict[UUID, str]:
    return {source.source_id: source.text for source in sources}


def align_quote(citation: QuoteCitation, sources: tuple[SourceText, ...] | list[SourceText]) -> str | None:
    """Return the source slice at the citation span, or None when it mismatches."""
    text = _source_index(sources).get(citation.source_id)
    if text is None:
        return None
    if citation.span_end > len(text):
        return None
    return text[citation.span_start : citation.span_end]


def quote_entails_claim(claim: str, quote: str) -> bool:
    """Deterministic lexical entailment: every claim content token sits in the quote."""
    claim_tokens = content_tokens(claim)
    if not claim_tokens:
        return False
    return claim_tokens <= content_tokens(quote)


def validate_citation(
    *,
    claim: str,
    citation: QuoteCitation,
    sources: tuple[SourceText, ...] | list[SourceText],
) -> EntailmentResult:
    """Validate one citation: exact quote alignment plus quote-level entailment."""
    if not claim.strip():
        raise ValueError("claim must be non-empty")
    aligned = align_quote(citation, sources)
    if aligned is None:
        return EntailmentResult(
            valid=False,
            reason="quote does not match source at declared span offsets",
            claim=claim,
            citation=citation,
        )
    if aligned != citation.quote:
        return EntailmentResult(
            valid=False,
            reason="quote does not match source at declared span offsets",
            claim=claim,
            citation=citation,
        )
    if not quote_entails_claim(claim, citation.quote):
        return EntailmentResult(
            valid=False,
            reason="unsupported claim: quote does not entail claim content",
            claim=claim,
            citation=citation,
        )
    return EntailmentResult(
        valid=True,
        reason="quote matches source and entails claim",
        claim=claim,
        citation=citation,
    )


def validate_citations(
    *,
    claim: str,
    citations: tuple[QuoteCitation, ...] | list[QuoteCitation],
    sources: tuple[SourceText, ...] | list[SourceText],
) -> EntailmentReport:
    """Validate every citation; the claim is supported only when all are valid."""
    if not claim.strip():
        raise ValueError("claim must be non-empty")
    accepted: list[EntailmentResult] = []
    rejected: list[EntailmentResult] = []
    for citation in citations:
        result = validate_citation(claim=claim, citation=citation, sources=sources)
        if result.valid:
            accepted.append(result)
        else:
            rejected.append(result)
    return EntailmentReport(
        valid=bool(accepted) and not rejected,
        claim=claim,
        accepted=tuple(accepted),
        rejected=tuple(rejected),
    )
