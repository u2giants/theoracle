"""Persist complete typed fixed/provider responses before any graph conversion."""
import json
from uuid import UUID
from typing import Literal
from pydantic import Field
from .source_receipts import SourceReceipt, EvidenceRef, _StrictModel
from .observations import ObservationKind, create_observation
from .findings import Finding

class ObservationResponse(_StrictModel):
    occurrence_key: str = Field(min_length=1)
    kind: ObservationKind
    scope: str = Field(min_length=1)
    value: str = Field(min_length=1)
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)

class ExtractionResponse(_StrictModel):
    schema_version: Literal[1] = 1
    source_id: UUID
    source_revision: int = Field(strict=True,ge=1)
    complete: bool
    observations: tuple[ObservationResponse, ...]
    findings: tuple[Finding, ...]
    unresolved_items: tuple[str, ...]


def persist_response(ledger, receipt: SourceReceipt, raw_response: str, *, artifact_id: UUID,
                     version: int, permission_digest: str, compiler_digest: str):
    refs = (receipt.ref,)
    base = {'source_refs':[receipt.ref.model_dump(mode='json')]}
    try:
        response = ExtractionResponse.model_validate_json(raw_response)
        if response.source_id!=receipt.ref.source_id or response.source_revision!=receipt.ref.revision:
            raise ValueError('wrong current source identity')
        if not response.complete or response.unresolved_items:
            raise ValueError('incomplete response; explicit unresolved findings required')
        observations = tuple(create_observation(receipt,r.occurrence_key,r.kind,r.scope,r.value,r.evidence) for r in response.observations)
        if any(f.source_refs != refs for f in response.findings):
            raise ValueError('document-local extraction borrowed another source')
        payload = {**base,'observations':[o.model_dump(mode='json') for o in observations],
                   'findings':[f.model_dump(mode='json') for f in response.findings],
                   'raw_response':raw_response,'complete':True}
    except (ValueError,KeyError,TypeError) as exc:
        # Failed extraction is itself durable, source-bound and reviewer-visible.
        failed = {**base,'complete':False,'raw_response':raw_response,
                  'failure_class':type(exc).__name__,'observations':[],'findings':[]}
        ledger.persist(workspace_id=receipt.ref.workspace_id,artifact_id=artifact_id,version=version,
                       kind='failed_extraction',payload=failed,refs=refs,permission_digest=permission_digest,
                       compiler_digest=compiler_digest,failed=True)
        raise ValueError('invalid extraction preserved in failed receipt') from None

    return ledger.persist(workspace_id=receipt.ref.workspace_id,artifact_id=artifact_id,version=version,
                          kind='extraction',payload=payload,refs=refs,permission_digest=permission_digest,
                          compiler_digest=compiler_digest)
