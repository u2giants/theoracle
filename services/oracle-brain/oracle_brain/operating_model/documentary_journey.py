"""Single-generation documentary integration; no company question or live route.

The caller supplies an admitted extraction provider, a source-only assembler and
an isolated SDKProjection. Injected responses prove integration only. Neither
this module nor the SDK projection promotes reported knowledge to company policy.
"""
from dataclasses import dataclass
from uuid import UUID, uuid4

from .pipeline import dispatch_source, persist_assembly
from .contracts import digest
from .summaries import summarize_from_ledger, persist_summary, serve_summary
from .answer import answer_from_summary


@dataclass(frozen=True)
class DocumentaryJourney:
    extraction_ids: tuple[UUID, ...]
    assembly_id: UUID
    summary_id: UUID
    graph_name: str
    answer: object


async def build_documentary_journey(
    ledger, provider, receipts, *, expected_source_refs, assemble,
    assembly_id, summary_id, projection, plan, obligations, coverage_records,
    permission_digest, compiler_digest, intent='overview', process_id=None,
):
    """Generate once per original, then seal, project, reload and explain.

    All source inventory/access checks precede the first provider call. Assembly
    receives only persisted extraction payloads. Projection must load its actual
    SDK graph before summary serving; there is no text/keyword fallback.
    """
    receipts = tuple(receipts)
    refs = tuple(receipt.ref for receipt in receipts)
    if (len(refs) < 2 or len({ref.source_id for ref in refs}) != len(refs)
            or len({ref.workspace_id for ref in refs}) != 1
            or len({ref.original_sha256 for ref in refs}) != len(refs)
            or len(expected_source_refs) != len(refs)
            or set(refs) != set(expected_source_refs)):
        raise ValueError('exact distinct multi-original source population required')
    workspace = refs[0].workspace_id
    ledger.authorize_refs(refs, workspace)
    extraction_ids = []
    for receipt in receipts:
        artifact = uuid4()
        dispatch_source(ledger, provider, receipt, artifact_id=artifact, version=1,
                        batch_id=assembly_id, permission_digest=permission_digest,
                        compiler_digest=compiler_digest)
        extraction_ids.append(artifact)
    extracted = tuple(ledger.read(workspace, artifact, 1) for artifact in extraction_ids)
    raw_assembly = assemble(extracted)
    persist_assembly(
        ledger, raw_assembly, workspace_id=workspace, artifact_id=assembly_id,
        version=1, extractions=tuple((artifact, 1) for artifact in extraction_ids),
        obligations=obligations, coverage_records=coverage_records,
        inventory_hash=digest({'obligations': [o.model_dump(mode='json') for o in obligations]}),
        permission_digest=permission_digest, compiler_digest=compiler_digest,
    )
    await projection.build(ledger, workspace, assembly_id, 1)
    reloaded = await projection.load(ledger, workspace, assembly_id, 1)
    if reloaded != ledger.read(workspace, assembly_id, 1):
        raise ValueError('SDK projection does not match sealed assembly')
    summary = summarize_from_ledger(ledger, workspace, assembly_id, 1, plan)
    persist_summary(ledger, summary, summary_id=summary_id, summary_version=1,
                    permission_digest=permission_digest, compiler_digest=compiler_digest)
    served = serve_summary(ledger, workspace, summary_id, 1)
    answer = answer_from_summary(ledger, served, intent=intent, process_id=process_id)
    return DocumentaryJourney(tuple(extraction_ids), assembly_id, summary_id,
                              projection.graph_name, answer)
