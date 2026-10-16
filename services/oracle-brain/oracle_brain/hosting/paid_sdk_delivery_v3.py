"""Protected paid-vector materialization, no dispatch, graph credentials or ACK."""
from dataclasses import dataclass
from datetime import datetime,timezone
from uuid import UUID
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2
from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.operating_model.purpose_qualification_v3 import PurposeQualifiedAssemblyReadGuardV3
from oracle_brain.operating_model.paid_sdk_embeddings_v3 import (
    PaidSDKEmbeddingPinsV3,PaidProjectionEmbedderV3,verify_paid_sdk_embedding_v3,
    processing_embedding_inventory_v3)
from .purpose_journey_v2 import (CompilerWorkerSettingsV2,_PurposeCompilerReadGuardV3,
    build_purpose_compiler_ledger_v3,_worker_parse,_unique,_require)
import json
from oracle_brain.operating_model.processing_projection import ProcessingProjectionAuthorityWindowV3


class CurrentPaidSDKGuardV3(PurposeQualifiedAssemblyReadGuardV3):
    """Actual protected compiler composition; no injected authority callbacks."""
    def __init__(self,combined):
        _require(type(combined) is _PurposeCompilerReadGuardV3,'actual compiler read guard required')
        self.combined=combined
        super().__init__(trusted_admissions=combined.trust,runtime_hash=combined.settings.config.runtime_hash,
            current_source_identity=combined.source,current_extraction_seal=combined.extraction_seal,
            qualified_parent_reader=combined.parent)
    def __call__(self,manifest,payload,principal,now):
        return self.combined(manifest,payload,principal,now)
    def valid_until(self,manifest,payload,principal,now):
        return self.combined.valid_until(manifest,payload,principal,now)


@dataclass(frozen=True)
class AuthenticatedPaidSDKBundleV3:
    embedder: PaidProjectionEmbedderV3
    qualification_guard: CurrentPaidSDKGuardV3
    ledger: object
    manifest: object
    payload: dict
    window: ProcessingProjectionAuthorityWindowV3


def load_paid_sdk_bundle_v3(settings,job,*,artifact_id,artifact_version,embedding_dispatch_id):
    """Current own SQL/custody BEFORE bytes, then exact historical native proof."""
    _require(type(settings) is CompilerWorkerSettingsV2 and type(job) is PurposeWorkerJobV2
        and job.phase=='compile' and type(artifact_id) is UUID and type(embedding_dispatch_id) is UUID
        and type(artifact_version) is int and artifact_version>=1,'exact protected compiler SDK consume required')
    settings.authorize(job)
    ledger=build_purpose_compiler_ledger_v3(settings,job)
    metadata,refs=settings.resolver.artifact_metadata(job.workspace_id,artifact_id,artifact_version)
    _require(metadata.kind=='processing_qualified_model_v1'
        and len(set(refs))==len(refs) and len(set(job.source_refs))==len(job.source_refs)
        and set(refs)==set(job.source_refs),
        'current exact qualified compiler metadata required before embedding custody')
    manifest,payload=ledger.read_with_manifest(job.workspace_id,artifact_id,artifact_version)
    _require(manifest==metadata,'qualified artifact changed before private embedding read')
    combined=ledger.processing_read_guard
    guard=CurrentPaidSDKGuardV3(combined)
    guard(manifest,payload,settings.config.actor_id,datetime.now(timezone.utc))
    selector=dict(artifact_id=artifact_id,artifact_version=artifact_version,dispatch_id=embedding_dispatch_id)
    ((context_raw,context_entry),(pins_raw,_),(commit_raw,commit_entry),
     (native_raw,native_entry),(wire,wire_entry))=settings.private_bundle(job,
        tuple((kind,selector) for kind in ('embedding_context','embedding_pins','phase_commit','native_receipt','raw_wire')))
    private=_worker_parse(context_raw,PurposePrivateContextV2)
    pins=_worker_parse(pins_raw,PaidSDKEmbeddingPinsV3)
    commit=_worker_parse(commit_raw,PhaseResponseCommitV2)
    native=json.loads(native_raw,object_pairs_hook=_unique)
    _require(private.phase=='embedding' and private.job.dispatch_id==embedding_dispatch_id
        and context_entry.sha256==pins.context_hash
        and pins.parent_registry_hash==settings.population.parent_registry_sha256
        and pins.population_digest==settings.population.population_digest
        and pins.allocation_hash==settings.config.allocation_projection_sha256
        and pins.ledger_identity_hash==settings.allocation.ledger_registry_hash,
        'paid embedding pins differ from exact original compiler allocation/population')
    for entry in (commit_entry,native_entry,wire_entry):
        _require(entry.native_job_hash==digest(private.job.model_dump(mode='json'))
            and (entry.sha256 is not None or (entry.producer_runtime_hash==private.context.runtime_hash
                and entry.request_hash==private.job.request_hash)), 'embedding producer appointment differs')
    data=verify_paid_sdk_embedding_v3(private,commit,native,wire,pins=pins)
    _require(data.witness.qualified_artifact_id==artifact_id
        and data.witness.qualified_artifact_version==artifact_version
        and data.inventory==processing_embedding_inventory_v3(payload),
        'paid vectors do not cover exact current qualified artifact')
    settings.authorize(job)
    again,current=ledger.read_with_manifest(job.workspace_id,artifact_id,artifact_version)
    _require(again==manifest and current==payload,'qualified artifact changed during embedding consumption')
    now=datetime.now(timezone.utc)
    guard(manifest,payload,settings.config.actor_id,now)
    # Expensive qualification first; fresh currentness LAST. Observation age
    # is never cached as the whole lifetime of this V3 paid delivery.
    guard.valid_until(manifest,payload,settings.config.actor_id,now)
    semantic_until=_semantic_operation_horizon_v3(settings,payload)
    fresh=settings.custody_window_v3(job)
    from oracle_brain.operating_model.processing_projection import ProcessingProjectionAuthorityWindowV3
    operation=min(fresh.operation_horizon,semantic_until)
    window=ProcessingProjectionAuthorityWindowV3(min(fresh.current_until,operation),operation)
    _require(datetime.now(timezone.utc)<window.current_until,'current compiler delivery boundary expired')
    return AuthenticatedPaidSDKBundleV3(PaidProjectionEmbedderV3(data),guard,ledger,manifest,payload,window)


def _semantic_operation_horizon_v3(settings,payload):
    from oracle_brain.operating_model.purpose_qualification_v3 import PurposeSemanticAdmissionV3
    from .purpose_journey_v2 import _worker_parse
    from oracle_brain.operating_model.contracts import canonical_bytes
    admission=_worker_parse(canonical_bytes(payload['assembly_qualification']['admission']),PurposeSemanticAdmissionV3)
    return settings.authorize_semantic(admission)
