"""Additive canonical recommendation producer. No general report/store bypass."""
import hashlib
import json
from datetime import datetime,timezone
from uuid import UUID
from ..contracts import ArtifactManifest,SourceRef,canonical_bytes,digest
from ..processing_ledger import PurposeProcessingCompilerLedgerV3
from ..request_deadline_v1 import request_remaining_v1,sql_remaining_v1
from ..consolidation_recommendations_v1 import validate_recommendation_parent
from .recommendation_actions_v1 import QualifiedConsultingRecommendationsV2
from .recommendation_authority_v1 import RecommendationAuthorityV1,RecommendationOutcomeUnknown


def compile_recommendation_actions_v1(compiler,registration,*,workspace_id,artifact_id,
        version,recommendations,permission_digest,caller_deadline):
    """Actual qualified parent -> canonical owner -> own registration receipt.

    Reconciliation can inspect a possible committed artifact/registration; this
    entry never retries either writer or dispatches any provider or action.
    """
    request_remaining_v1()
    sql_remaining_v1(caller_deadline)
    if (type(compiler) is not PurposeProcessingCompilerLedgerV3
            or type(registration) is not RecommendationAuthorityV1
            or registration.binding.operation!='register'
            or type(recommendations) is not QualifiedConsultingRecommendationsV2
            or type(workspace_id) is not UUID or type(artifact_id) is not UUID
            or type(version) is not int or version<1
            or compiler.principal!=registration.binding.principal_id
            or workspace_id!=registration.binding.workspace_id
            or recommendations.parent_model_id!=registration.binding.model_id):
        raise PermissionError('actual independently appointed canonical recommendation compiler required')
    parent=compiler.read_validated_qualified_parent_v3(workspace_id,
        recommendations.parent_model_id,recommendations.parent_version)
    parent_body=json.loads(parent.canonical_body)
    payload={'source_refs':parent_body['source_refs'],'findings':[],
             'recommendations':recommendations.model_dump(mode='json')}
    payload_bytes=canonical_bytes(payload)
    actual_refs=tuple(compiler.processing_sources.artifact_metadata(workspace_id,
        parent.manifest.artifact_id,parent.manifest.version)[1])
    refs=tuple(SourceRef.model_validate_json(canonical_bytes(r)) for r in parent_body['source_refs'])
    if len(set(refs))!=len(refs) or set(refs)!=set(actual_refs):
        raise PermissionError('actual complete parent source population differs')
    ref_bytes=canonical_bytes({'refs':[r.model_dump(mode='json') for r in refs]})
    dependencies=(('artifact',str(parent.manifest.artifact_id),str(parent.manifest.version)),)
    all_deps=tuple(sorted(set(dependencies)|{('source',str(r.source_id),str(r.revision)) for r in refs}))
    manifest=ArtifactManifest(workspace_id=workspace_id,artifact_id=artifact_id,version=version,
        kind='processing_recommendation_v1',input_digest=hashlib.sha256(ref_bytes).hexdigest(),
        source_digest=hashlib.sha256(ref_bytes).hexdigest(),permission_digest=permission_digest,
        compiler_digest=compiler.processing_sources.binding.runtime_hash,
        dependency_digest=digest({'dependencies':all_deps}),content_hash=digest(payload),
        private_object_key=f'operating-model/{workspace_id}/{digest(payload)}.json',state='ready')
    validate_recommendation_parent(manifest,payload,parent.manifest,parent_body)
    if datetime.now(timezone.utc)>=parent.valid_until:
        raise PermissionError('complete actual qualified parent expired')
    request_remaining_v1();sql_remaining_v1(caller_deadline)
    # The canonical compiler remains the only accepted-artifact writer. It
    # independently repeats qualification/currentness; this is not a sibling
    # unqualified payload or an alternate Ledger.persist path.
    persisted=compiler.persist(workspace_id=workspace_id,artifact_id=artifact_id,version=version,
        kind=manifest.kind,payload=payload,refs=refs,permission_digest=permission_digest,
        compiler_digest=manifest.compiler_digest,dependencies=dependencies,caller_deadline=caller_deadline)
    try:
        request_remaining_v1();sql_remaining_v1(caller_deadline)
        if persisted!=manifest:raise PermissionError('canonical recommendation artifact differs')
        receipt=registration.register_v1(persisted,payload_bytes,parent.canonical_body,deadline=caller_deadline)
        request_remaining_v1();sql_remaining_v1(caller_deadline)
        return persisted,receipt
    except Exception as error:
        raise RecommendationOutcomeUnknown('canonical artifact may exist; read-only registration reconciliation; never recompile or resend') from error
