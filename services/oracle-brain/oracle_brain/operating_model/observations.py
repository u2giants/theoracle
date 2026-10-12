"""Deterministic, evidence-backed operating model observations."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, field_validator

from .source_receipts import EvidenceRef, SourceReceipt, SourceRef, _StrictModel, validate_evidence


ObservationKind = Literal[
    "process", "step", "role", "artifact", "handoff", "decision",
    "uncertainty", "assertion", "objective", "metric_definition",
]


class Observation(_StrictModel):
    schema_version: Literal[1] = 1
    observation_id: str
    ref: SourceRef
    occurrence_key: str
    kind: ObservationKind
    scope: str
    value: str
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)

    @field_validator("observation_id", "occurrence_key", "scope", "value")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError("value must be nonempty")
        return value


def create_observation(
    receipt: SourceReceipt,
    occurrence_key: str,
    kind: ObservationKind,
    scope: str,
    value: str,
    evidence: tuple[EvidenceRef, ...] | list[EvidenceRef],
) -> Observation:
    if not occurrence_key or not scope or not value:
        raise ValueError("occurrence_key, scope, and value must be nonempty")
    evidence_tuple = tuple(evidence)
    if not evidence_tuple:
        raise ValueError("evidence must be nonempty")
    for item in evidence_tuple:
        validate_evidence(receipt, item)
    canonical_evidence = [
        {"end": item.end, "quote": item.quote, "start": item.start}
        for item in evidence_tuple
    ]
    canonical = {
        "evidence": sorted(canonical_evidence, key=lambda item: (item["start"], item["end"], item["quote"])),
        "kind": kind,
        "occurrence_key": occurrence_key,
        "original_sha256": receipt.ref.original_sha256,
        "parser_id": receipt.ref.parser_id,
        "reading_sha256": receipt.ref.reading_sha256,
        "revision": receipt.ref.revision,
        "scope": scope,
        "source_id": str(receipt.ref.source_id),
        "value": value,
        "workspace_id": str(receipt.ref.workspace_id),
    }
    observation_id = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return Observation(
        observation_id=observation_id, ref=receipt.ref, occurrence_key=occurrence_key,
        kind=kind, scope=scope, value=value, evidence=evidence_tuple,
    )
