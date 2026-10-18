"""Compile/read separation for versioned qualified assembly lineage.

Compile validates actual original spans through the unchanged semantic verifier.
Serving validates immutable admitted seals and current metadata only. Neither
path issues admission; a trusted runtime supplies the existing external semantic
admission hash registry and real current source/extraction metadata resolvers.
"""
from datetime import datetime
from uuid import UUID
from typing import Literal

from pydantic import Field

from .captured_assembly import CapturedAssemblyCandidate, captured_assembly_candidate
from .contracts import ArtifactManifest, ProcessingExtractionSeal, StrictRecord, digest
from .coverage import validate_coverage
from .pipeline import assembly_inputs, assembly_candidate_payload
from .semantic_acceptance import (
    FrozenCensus, IndependentAssessment, SemanticAdmission, sealed,
    verify_semantic_acceptance,
)
from .semantic_runtime import ledger_object_evidence
from .source_receipts import SourceRef

HASH = r'^[0-9a-f]{64}$'


class CapturedAssemblySemanticAdmission(SemanticAdmission):
    """V2 of the existing external registry, never an upgrade of a V1 receipt."""
    schema_version: Literal[2] = 2
    final_envelope_hash: str = Field(pattern=HASH)


class FinalAssemblyLineage(StrictRecord):
    schema_version: Literal[2] = 2
    kind: Literal['captured-assembly-qualified-content-v2'] = 'captured-assembly-qualified-content-v2'
    candidate_hash: str = Field(pattern=HASH)
    capture_hash: str = Field(pattern=HASH)
    object_evidence_hash: str = Field(pattern=HASH)
    census_hash: str = Field(pattern=HASH)
    assessment_hash: str = Field(pattern=HASH)
    source_refs: tuple[SourceRef,...]
    extraction_manifest_hashes: tuple[str,...]


class AssemblyQualification(StrictRecord):
    schema_version: Literal[2] = 2
    admission: CapturedAssemblySemanticAdmission


def verify_captured_assembly_semantic_acceptance(*, context, observer,
        expected_observer_context_hash, protocol, expected_protocol_hash, observed, raw, assessment, admission,
        trusted_admission_hashes, source_regions, current_source, can_read, now):
    """Compiler/assessor only. Current original receipts are mandatory here."""
    if not isinstance(admission,CapturedAssemblySemanticAdmission):
        raise PermissionError('new qualified assembly requires independently admitted V2 final core')
    captured, _ = captured_assembly_candidate(context=context, observer=observer,
        expected_observer_context_hash=expected_observer_context_hash,
        protocol=protocol,expected_protocol_hash=expected_protocol_hash, observed=observed, raw=raw, now=now)
    if observer.protocol_hash != admission.protocol_hash or context.actor_id != admission.implementer_actor:
        raise PermissionError('externally admitted observation protocol differs')
    receipts = {}
    for ref in context.census.source_refs:
        if not can_read(ref.workspace_id, admission.assessor_actor, ref.source_id):
            raise PermissionError('independent compile original access denied')
        receipt = current_source(ref.workspace_id, ref.source_id)
        if receipt.ref != ref:
            raise PermissionError('compile original changed')
        receipts[str(ref.source_id)] = receipt
    evidence = ledger_object_evidence(captured.candidate, workspace_id=context.job.workspace_id,
                                     receipts=receipts, inventories=context.reviewed_inventories)
    evidence_hash = digest({k:[e.model_dump(mode='json') for e in v] for k,v in evidence.items()})
    if evidence_hash != captured.object_evidence_hash:
        raise PermissionError('compiled object evidence differs from captured candidate')
    verify_semantic_acceptance(census=context.census, assessment=assessment, admission=admission,
        trusted_admission_hashes=trusted_admission_hashes, source_regions=source_regions,
        candidate=captured.candidate, object_evidence=evidence,
        runtime_hash=context.runtime_hash, permission_hash=context.job.permission_hash,
        candidate_created_at=observed.observed_at, now=now,
        current_source=current_source, can_read=can_read)
    if digest(qualified_content_core(captured,census=context.census,assessment=assessment))!=admission.final_envelope_hash:
        raise PermissionError('external V2 admission does not bind exact qualified content core')
    return captured


def _qualified_content_core(captured, *, census, assessment, lineage_model=FinalAssemblyLineage, lineage_extra=None):
    """Private compiler derivation; caller must obtain real independent V2 admission.

    Raw census/assessment/whole originals never enter the minimized serving core.
    """
    import json
    if digest(captured.candidate)!=captured.candidate_hash:
        raise PermissionError('captured candidate identity differs')
    _,observations,findings=assembly_inputs((captured.candidate,))
    refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in captured.candidate['source_refs'])
    _,evidence=assembly_candidate_payload(captured.candidate['raw_response'],workspace_id=census.workspace_id,
        refs=refs,observations=observations,findings=findings)
    coverage=validate_coverage(census.obligations,assessment.coverage,object_evidence=evidence,
        independent_inventory_hash=digest({'obligations':[o.model_dump(mode='json') for o in census.obligations]}))
    lineage=lineage_model(**(lineage_extra or {}),candidate_hash=captured.candidate_hash,
        capture_hash=digest(captured.candidate['assembly_capture']),object_evidence_hash=captured.object_evidence_hash,
        census_hash=sealed(census),assessment_hash=sealed(assessment),source_refs=refs,
        extraction_manifest_hashes=tuple(e['manifest_hash'] for e in captured.candidate['assembly_capture']['extractions']))
    return {**captured.candidate,'coverage':coverage,'qualified_lineage':lineage.model_dump(mode='json')}


def qualified_content_core(captured,*,census,assessment):
    if type(captured) is not CapturedAssemblyCandidate:
        raise PermissionError('legacy qualified core cannot consume a purpose V2 capture')
    return _qualified_content_core(captured,census=census,assessment=assessment)


def final_assembly_envelope(captured, *, census, assessment, admission):
    """Final core excludes the admission/selfhash, avoiding circular certification."""
    if (not isinstance(admission,CapturedAssemblySemanticAdmission)
            or captured.candidate_hash!=admission.candidate_hash
            or sealed(census)!=admission.census_hash or sealed(assessment)!=admission.assessment_hash):
        raise PermissionError('current independent V2 qualified assembly admission required')
    core=qualified_content_core(captured,census=census,assessment=assessment)
    if digest(core)!=admission.final_envelope_hash:
        raise PermissionError('V2 admission does not bind deterministic final content core')
    return {**core,'assembly_qualification':AssemblyQualification(admission=admission).model_dump(mode='json')}


def _verify_final_assembly_lineage(manifest,payload,principal,now,*,trusted_admission_hashes,
        runtime_hash,current_source_identity,current_extraction_seal,qualification_model,lineage_model,
        protocol_model,wire_model,permission_field='permission_hash',additional_check=None,metadata_model=ArtifactManifest):
    """Serving-only: minimized admitted core/current metadata, never raw originals."""
    import json
    if (not isinstance(manifest,metadata_model) or manifest.kind!='processing_qualified_model_v1'
            or manifest.state!='ready' or not isinstance(principal,UUID)
            or now.tzinfo is None or now.utcoffset() is None):
        raise PermissionError('qualified model serving context required')
    qualification=qualification_model.model_validate_json(json.dumps(payload['assembly_qualification']))
    admission=qualification.admission
    lineage=lineage_model.model_validate_json(json.dumps(payload['qualified_lineage']))
    core={k:v for k,v in payload.items() if k!='assembly_qualification'}
    candidate={k:v for k,v in core.items() if k not in {'coverage','qualified_lineage'}}
    if (sealed(admission) not in trusted_admission_hashes or admission.expires_at<=now
            or admission.runtime_hash!=runtime_hash or admission.implementer_actor==admission.assessor_actor
            or digest(core)!=admission.final_envelope_hash or digest(payload)!=manifest.content_hash
            or digest(candidate)!=lineage.candidate_hash or lineage.candidate_hash!=admission.candidate_hash
            or lineage.census_hash!=admission.census_hash or lineage.assessment_hash!=admission.assessment_hash
            or lineage.object_evidence_hash!=admission.object_evidence_hash
            or digest(candidate['assembly_capture'])!=lineage.capture_hash
            or manifest.permission_digest!=getattr(admission,permission_field)):
        raise PermissionError('current external V2 assembly admission or minimized lineage differs')
    refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in candidate['source_refs'])
    if (refs!=lineage.source_refs or not refs or len(set(refs))!=len(refs)
            or any(r.workspace_id!=manifest.workspace_id for r in refs)
            or digest({'refs':[r.model_dump(mode='json') for r in refs]})!=manifest.source_digest):
        raise PermissionError('qualified source population differs')
    model=candidate['operating_models'][0]
    if manifest.artifact_id!=UUID(model['model_id']) or manifest.version!=model['version']:
        raise PermissionError('qualified manifest differs from generated model identity')
    capture=candidate['assembly_capture']
    protocol=protocol_model.model_validate_json(json.dumps(capture['protocol']))
    observed=wire_model.model_validate_json(json.dumps(capture['observed_wire']))
    if additional_check is not None:additional_check(capture,lineage,admission,principal)
    if (sealed(protocol)!=capture['protocol_hash'] or capture['protocol_hash']!=admission.protocol_hash
            or observed.observed_at!=admission.candidate_created_at
            or observed.observed_at>now or manifest.compiler_digest!=capture['compiler_digest']):
        raise PermissionError('current admitted observation/compile protocol differs')
    for ref in refs:
        if current_source_identity(ref.workspace_id,principal,ref.source_id)!=ref:
            raise PermissionError('current qualified source identity unavailable')
    extractions=capture['extractions'];seen=set();extracted_sources=[]
    if len(extractions)!=len(refs) or tuple(e['manifest_hash'] for e in extractions)!=lineage.extraction_manifest_hashes:
        raise PermissionError('qualified extraction population differs')
    for expected in extractions:
        key=(UUID(expected['artifact_id']),expected['version'])
        if key in seen:raise PermissionError('duplicate qualified extraction dependency')
        seen.add(key)
        current=current_extraction_seal(manifest.workspace_id,principal,*key)
        if (not isinstance(current,ProcessingExtractionSeal) or current.workspace_id!=manifest.workspace_id
                or any(current.model_dump(mode='json')[k]!=v for k,v in expected.items())
                or len(current.source_refs)!=1 or current.source_refs[0] not in refs
                or digest({'refs':[r.model_dump(mode='json') for r in current.source_refs]})!=current.source_digest):
            raise PermissionError('current sealed extraction dependency unavailable')
        extracted_sources.extend(current.source_refs)
    if len(extracted_sources)!=len(refs) or set(extracted_sources)!=set(refs):
        raise PermissionError('current extraction source population differs')
    _,observations,findings=assembly_inputs((candidate,))
    expected,evidence=assembly_candidate_payload(candidate['raw_response'],workspace_id=manifest.workspace_id,
        refs=refs,observations=observations,findings=findings)
    if {**expected,'assembly_capture':capture}!=candidate:
        raise PermissionError('qualified candidate contains unmatched generated bytes')
    if digest({k:[e.model_dump(mode='json') for e in v] for k,v in evidence.items()})!=admission.object_evidence_hash:
        raise PermissionError('qualified object evidence differs from independent V2 admission')
    for ref in refs:
        if current_source_identity(ref.workspace_id,principal,ref.source_id)!=ref:
            raise PermissionError('qualified source changed during serving checks')
    return None


def verify_final_assembly_lineage(manifest,payload,principal,now,*,trusted_admission_hashes,
        runtime_hash,current_source_identity,current_extraction_seal):
    """Legacy schema2 guard; no purpose V2/schema3 protocol reinterpretation."""
    from .captured_assembly import ObservedAssemblyProtocol,ObservedAssemblyWire
    return _verify_final_assembly_lineage(manifest,payload,principal,now,
        trusted_admission_hashes=trusted_admission_hashes,runtime_hash=runtime_hash,
        current_source_identity=current_source_identity,current_extraction_seal=current_extraction_seal,
        qualification_model=AssemblyQualification,lineage_model=FinalAssemblyLineage,
        protocol_model=ObservedAssemblyProtocol,wire_model=ObservedAssemblyWire)


class QualifiedAssemblyReadGuard:
    """Trusted constructor-only runtime wiring, never deserialize from a request.

    Callback types are not authentic authority. Runtime configuration must bind
    actual SQL-backed principal/source/extraction resolvers and the EXISTING
    current external semantic admission registry. No callback is run over raw
    original content at serving time.
    """
    def __init__(self, *, trusted_admissions, runtime_hash, current_source_identity,
                 current_extraction_seal, qualified_parent_reader):
        if any(not callable(c) for c in (trusted_admissions,current_source_identity,
                current_extraction_seal,qualified_parent_reader)):
            raise PermissionError('trusted current qualification runtime required')
        self._trust=trusted_admissions
        self._runtime=runtime_hash
        self._source=current_source_identity
        self._extraction=current_extraction_seal
        self._parent=qualified_parent_reader

    def valid_until(self, manifest, payload, principal, now):
        """Trusted compiler pre-lock deadline; SQL rechecks actual clock after locks."""
        self(manifest,payload,principal,now)
        if manifest.kind=='processing_qualified_model_v1':
            import json
            qualification=AssemblyQualification.model_validate_json(json.dumps(payload['assembly_qualification']))
            deadline=qualification.admission.expires_at
        elif manifest.kind=='processing_summary_v1':
            from .summaries import DocumentarySummary
            import json
            pack=DocumentarySummary.model_validate_json(json.dumps(payload['summary'])).pack
            parent,body=self._parent(pack.workspace_id,principal,pack.artifact_id,pack.version)
            if parent.kind!='processing_qualified_model_v1':
                raise PermissionError('summary deadline requires exact qualified parent')
            deadline=self.valid_until(parent,body,principal,now)
        else:
            raise PermissionError('semantic deadline unavailable for unqualified kind')
        if not isinstance(deadline,datetime) or deadline.tzinfo is None or deadline.utcoffset() is None or deadline<=now:
            raise PermissionError('current finite semantic deadline required')
        return deadline

    def __call__(self, manifest, payload, principal, now):
        if manifest.kind == 'processing_qualified_model_v1':
            return verify_final_assembly_lineage(manifest,payload,principal,now,
                trusted_admission_hashes=self._trust(),runtime_hash=self._runtime,
                current_source_identity=self._source,current_extraction_seal=self._extraction)
        if manifest.kind != 'processing_summary_v1':
            raise PermissionError('extraction/failed processing artifact is not qualified for serving')
        from .summaries import DocumentarySummary
        from .retrieval import build_pack
        import json
        summary=DocumentarySummary.model_validate_json(json.dumps(payload['summary']))
        pack=summary.pack
        if (manifest.state!='ready' or digest(payload)!=manifest.content_hash
                or pack.workspace_id!=manifest.workspace_id
                or pack.artifact_id==manifest.artifact_id
                or summary.summary_hash!=digest(pack.model_dump(mode='json'))
                or payload['source_refs']!=[r.model_dump(mode='json') for r in pack.source_refs]):
            raise PermissionError('qualified summary envelope or parent identity differs')
        parent,body=self._parent(pack.workspace_id,principal,pack.artifact_id,pack.version)
        if (parent.kind!='processing_qualified_model_v1'
                or parent.workspace_id!=pack.workspace_id or parent.artifact_id!=pack.artifact_id
                or parent.version!=pack.version or parent.content_hash!=pack.artifact_hash
                or body['source_refs']!=payload['source_refs']):
            raise PermissionError('qualified summary requires exact immutable qualified parent')
        self(parent,body,principal,now)
        if build_pack(body,pack.plan)!=pack.contents:
            raise PermissionError('qualified summary content differs from current admitted parent')
        return None


def read_documentary_artifact(ledger,workspace_id,artifact_id,version,*,qualification_guard=None,with_manifest=False):
    """Use authenticated manifest kinds; a payload marker is never authority."""
    from datetime import timezone
    if hasattr(ledger,'read_with_manifest'):
        manifest,payload=ledger.read_with_manifest(workspace_id,artifact_id,version)
        if manifest.kind.startswith('processing_'):
            if (manifest.kind not in {'processing_qualified_model_v1','processing_summary_v1'}
                    or not isinstance(qualification_guard,QualifiedAssemblyReadGuard)):
                raise PermissionError('explicit current processing qualification verifier required')
            if qualification_guard(manifest,payload,ledger.principal,datetime.now(timezone.utc)) is not None:
                raise PermissionError('processing qualification verifier denied')
        return (manifest,payload) if with_manifest else payload
    # Legacy Ledger cannot decode any new processing manifest kind. Keep its
    # old read contract, but never mistake qualification-shaped bytes for proof.
    payload=ledger.read(workspace_id,artifact_id,version)
    if 'assembly_qualification' in payload or 'assembly_capture' in payload:
        raise PermissionError('authenticated processing manifest API required')
    return (None,payload) if with_manifest else payload


def persist_qualified_assembly(ledger, *, context, observer, expected_observer_context_hash,
        protocol, expected_protocol_hash, observed, raw, assessment, admission,
        trusted_admission_hashes, source_regions, current_source, can_read, compiler_digest):
    """Single generation -> independent assessment -> explicit qualified commit.

    Requires the reviewed ProcessingCompilerLedger capability. Generic Ledger
    rejects the new kind. No generated model can supply its own admission or
    coverage, and this function never dispatches another extraction/provider.
    """
    from datetime import timezone
    refs=context.census.source_refs
    if compiler_digest!=context.compiler_digest:
        raise PermissionError('compiler identity differs from externally pinned assembly context')
    ledger.authorize_refs(refs,context.job.workspace_id)
    if not hasattr(ledger,'read_with_manifest'):
        raise PermissionError('authenticated current extraction manifests required')
    for expected in context.extractions:
        manifest,payload=ledger.read_with_manifest(context.job.workspace_id,
            expected.manifest.artifact_id,expected.manifest.version)
        if manifest!=expected.manifest or payload!=expected.payload:
            raise PermissionError('assembly extraction dependency changed before compilation')
    captured=verify_captured_assembly_semantic_acceptance(context=context,observer=observer,
        expected_observer_context_hash=expected_observer_context_hash,protocol=protocol,
        expected_protocol_hash=expected_protocol_hash,observed=observed,raw=raw,
        assessment=assessment,admission=admission,trusted_admission_hashes=trusted_admission_hashes,
        source_regions=source_regions,current_source=current_source,can_read=can_read,
        now=datetime.now(timezone.utc))
    payload=final_assembly_envelope(captured,census=context.census,assessment=assessment,admission=admission)
    # The required ProcessingCompilerLedger must independently recheck source authority,
    # reported invariants and semantic expiry atomically at its real SQL commit.
    return ledger.persist(workspace_id=context.job.workspace_id,artifact_id=context.model_id,
        version=context.model_version,kind='processing_qualified_model_v1',payload=payload,refs=refs,
        permission_digest=context.job.permission_hash,compiler_digest=compiler_digest,
        dependencies=tuple(('artifact',str(e.manifest.artifact_id),str(e.manifest.version)) for e in context.extractions))
