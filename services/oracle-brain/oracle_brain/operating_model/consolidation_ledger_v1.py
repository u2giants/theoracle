"""Actual immutable canonical qualified-owner commit; no offline FactStore writer."""
from datetime import datetime,timezone
import psycopg
from psycopg.types.json import Jsonb
from .contracts import ArtifactManifest,canonical_bytes,digest
from .consolidation_contracts_v1 import ConsolidationCoreV1
from .consolidation_authority_v1 import ConsolidationAuthorityV1
from .processing_ledger import require_explicit_compiler_ledger_v3


class ConsolidationCommitUnknown(PermissionError):
    """The write was attempted; read-only reconciliation is required, never retry."""


def persist_consolidation_revision_v1(ledger,authority,*,payload,permission_digest,dependencies,idempotency,deadline,protected_settings=None,worker_job=None):
    require_explicit_compiler_ledger_v3(ledger)
    if (type(authority) is not ConsolidationAuthorityV1 or authority.binding.operation!='consolidate'
            or ledger.url!=authority.url or ledger.principal!=authority.binding.principal_id):
        raise PermissionError('exact current canonical compiler and separate consolidation appointment required')
    authority._deadline(deadline)
    if protected_settings is not None:
        from oracle_brain.hosting.purpose_journey_v2 import CompilerWorkerSettingsV2
        if (type(protected_settings) is not CompilerWorkerSettingsV2 or protected_settings.resolver is not ledger.processing_sources
                or protected_settings.config_sha256!=authority.binding.config_hash):
            raise PermissionError('exact protected compiler metadata consumer required')
    core=ConsolidationCoreV1.model_validate_json(canonical_bytes(payload['consolidation_core']))
    from .purpose_qualification_v3 import PurposeAssemblyQualificationV3
    from .semantic_acceptance import sealed
    qualification_hash=sealed(PurposeAssemblyQualificationV3.model_validate_json(canonical_bytes(payload['assembly_qualification'])).admission)
    if qualification_hash not in authority.binding.retained_semantic_admissions:
        raise PermissionError('exact independently selected consolidation qualification required')
    workspace=core.model.workspace_id;artifact=core.model.model_id;version=core.model.version
    if workspace!=authority.binding.workspace_id or artifact!=authority.binding.model_id:raise PermissionError('cross-workspace consolidation')
    refs=tuple(core.model.source_refs)
    receipts=ledger.authorize_refs(refs,workspace)
    ledger.validate_reported_payload(payload,refs,workspace,receipts)
    deps=tuple(sorted(set(tuple(d) for d in dependencies)|{('source',str(r.source_id),str(r.revision)) for r in refs}))
    if any(len(d)!=3 or d[0] not in {'source','artifact'} or d[0]=='artifact' and d[1]==str(artifact) for d in deps):
        raise PermissionError('revision ancestry cannot masquerade as support')
    raw=canonical_bytes(payload);refs_raw=canonical_bytes({'refs':[r.model_dump(mode='json') for r in refs]})
    dep_raw=canonical_bytes({'dependencies':deps});content=digest(payload)
    manifest=ArtifactManifest(workspace_id=workspace,artifact_id=artifact,version=version,
        kind='processing_qualified_model_v1',input_digest=digest({'refs':[r.model_dump(mode='json') for r in refs]}),
        source_digest=digest({'refs':[r.model_dump(mode='json') for r in refs]}),permission_digest=permission_digest,
        compiler_digest=ledger.processing_sources.binding.runtime_hash,dependency_digest=digest({'dependencies':deps}),
        content_hash=content,private_object_key=f'operating-model/{workspace}/{content}.json',state='ready')
    now=datetime.now(timezone.utc)
    until=ledger._validate_processing_guard(ledger.processing_compile_guard,manifest,payload,now)
    # Narrow ONCE, before private storage; never recompute or renew on retry.
    deadline=min(deadline,until,ledger.processing_sources.binding.expires_at,authority.binding.original_horizon)
    # Synchronous filesystem may finish late; no subsequent SQL is then allowed.
    if ledger.blobs.put(workspace,payload)!=(manifest.private_object_key,content):raise PermissionError('private immutable object identity differs')
    authority._deadline(deadline)
    attempted=False
    try:
        with psycopg.connect(authority.url,connect_timeout=2) as c:
            authority._check(c,deadline);ledger.processing_sources._check(c)
            attempted=True
            result=c.execute('SELECT oracle2.commit_processing_model_revision_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (Jsonb(manifest.model_dump(mode='json')),raw,refs_raw,dep_raw,
                 Jsonb([r.model_dump(mode='json') for r in receipts.values()]),*authority._arguments(deadline),idempotency)).fetchone()[0]
            if result['manifest']!=manifest.model_dump(mode='json'):raise PermissionError('canonical commit returned another artifact')
            authority._check(c,deadline);ledger.processing_sources._check(c)
            if protected_settings is not None:
                from oracle_brain.hosting.purpose_journey_v2 import _worker_file
                _worker_file(protected_settings.config_path,protected_settings.config_sha256)
                if protected_settings.jobs.current(worker_job.job_id,now=datetime.now(timezone.utc))!=worker_job:
                    raise PermissionError('externally appointed compiler job changed before commit')
                if qualification_hash not in protected_settings.semantic.current(datetime.now(timezone.utc)):
                    raise PermissionError('current external semantic registry changed before commit')
        authority._check_after_close(deadline,result)
    except (psycopg.errors.SerializationFailure,psycopg.errors.UniqueViolation,psycopg.errors.InsufficientPrivilege):
        raise
    except Exception:
        if attempted:raise ConsolidationCommitUnknown('consolidation write outcome UNKNOWN; no automatic retry') from None
        raise
    # Actual new readonly transaction after actual write connection closed.
    with psycopg.connect(authority.url,connect_timeout=2) as c:
        authority._check(c,deadline)
        fresh=c.execute('SELECT oracle2.hosting_processing_model_revision_v1(%s,%s,%s,%s,%s,%s,%s)',
            (artifact,version,*authority._arguments(deadline))).fetchone()[0]
        authority._check(c,deadline)
    if fresh['manifest']!=result['manifest'] or fresh['recordedAt']!=result['recordedAt']:
        raise PermissionError('committed revision no longer current')
    authority._check_after_close(deadline,fresh)
    return manifest,fresh
