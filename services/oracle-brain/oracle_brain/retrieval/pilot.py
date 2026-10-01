"""Pilot retrieval: find source blocks relevant to a question via keyword overlap."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RetrievedSpan:
    block_id: UUID
    source_id: UUID
    span_start: int
    span_end: int
    quote: str
    score: float


def retrieve_spans(question: str, blocks: list[dict], *, limit: int = 5,
                   process_connections: list[dict] | None = None) -> list[RetrievedSpan]:
    """Rank blocks by keyword overlap with the question.

    When process_connections are supplied, blocks that participate in a
    confirmed/corrected connection receive a retrieval boost so a connected
    question can follow the process map rather than keyword overlap alone.
    This is a deliberately simple retrieval path for the pilot journey; S09
    replaces it with proper embedding-based retrieval.
    """
    if not question.strip():
        raise ValueError("question must be non-empty")
    stop_words = {"the", "a", "an", "is", "are", "can", "where", "how", "what",
                  "when", "does", "do", "in", "on", "to", "of", "for", "and",
                  "or", "be", "will", "would", "could", "should"}
    question_words = {
        w.lower().strip(".,;:!?") for w in question.split()
        if w.lower().strip(".,;:!?") and w.lower() not in stop_words
    }
    connected_indexes: set[int] = set()
    for connection in process_connections or []:
        for key in ("from", "to"):
            value = connection.get(key)
            if isinstance(value, int):
                connected_indexes.add(value)
            elif isinstance(value, str) and value.isdigit():
                connected_indexes.add(int(value))
    connection_boost = 0.15 if connected_indexes else 0.0
    scored: list[tuple[float, dict]] = []
    for block in blocks:
        text_lower = block["text"].lower()
        overlap = sum(1 for word in question_words if word in text_lower)
        score = overlap / max(len(question_words), 1)
        if block.get("block_index") in connected_indexes:
            score += connection_boost
        if score > 0:
            scored.append((score, block))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RetrievedSpan(
            block_id=block["block_id"],
            source_id=block["source_id"],
            span_start=block["span_start"],
            span_end=block["span_end"],
            quote=block["text"],
            score=score,
        )
        for score, block in scored[:limit]
    ]
