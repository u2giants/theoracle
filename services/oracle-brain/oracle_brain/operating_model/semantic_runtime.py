"""Read-only semantic admission for an actual current operating-model ledger.

No caller-provided coverage map, provider call, store write or serving authority.
"""
import json
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from .assembly import validate_assembly
from .contracts import ArtifactManifest, digest
from .findings import Finding, validate_finding
from .model import BusinessOperatingModel
from .workflows.process_model import canonical_workflow_items
from .observations import Observation, create_observation
from .semantic_acceptance import sealed, verify_semantic_acceptance
from .source_receipts import SourceRef
from .workflows.process_model import WorkflowModel
from .workflows.process_validate import validate_workflow


def _typed(record_type, raw):
    return record_type.model_validate_json(json.dumps(raw))


def ledger_object_evidence(payload, *, workspace_id, receipts, inventories):
    """Derive the pipeline's exact projection support, never aggregate shortcuts."""
    refs = tuple(_typed(SourceRef, r) for r in payload['source_refs'])
    if len(set(refs)) != len(refs) or any(r.workspace_id != workspace_id for r in refs):
        raise ValueError('duplicate or cross-workspace source manifest')
    observations = {}
    for raw in payload.get('observations', ()):
        observation = _typed(Observation, raw)
        if observation.observation_id in observations or observation.ref not in refs:
            raise ValueError('duplicate or out-of-population observation')
        receipt = receipts[str(observation.ref.source_id)]
        expected = create_observation(receipt, observation.occurrence_key, observation.kind,
                                      observation.scope, observation.value, observation.evidence)
        if expected != observation:
            raise ValueError('observation does not reproduce current original support')
        observations[observation.observation_id] = observation
    findings = {}
    for raw in payload.get('findings', ()):
        finding = _typed(Finding, raw)
        if finding.finding_id in findings or finding.workspace_id != workspace_id:
            raise ValueError('duplicate or cross-workspace finding')
        if not set(finding.source_refs) <= set(refs):
            raise ValueError('finding outside artifact source population')
        findings[finding.finding_id] = validate_finding(finding, receipts, inventories=inventories)
    evidence, workflows = {}, {}

    def support(identifier, ids):
        if identifier in evidence or identifier in observations:
            raise ValueError('projection identity collision')
        if len(set(ids)) != len(ids) or any(oid not in observations for oid in ids):
            raise ValueError('projection references duplicate or absent observation')
        evidence[identifier] = tuple(e for oid in ids for e in observations[oid].evidence)

    def workflow(raw, *, nested=False):
        model = _typed(WorkflowModel, raw)
        if model.workspace_id != workspace_id or not set(model.source_refs) <= set(refs):
            raise ValueError('workflow outside artifact source population')
        if model.status != 'reported' or not set(model.finding_ids) <= findings.keys():
            raise PermissionError('workflow policy or finding is not admitted')
        if len(set(model.finding_ids)) != len(model.finding_ids):
            raise ValueError('duplicate workflow finding identity')
        validate_workflow(model, observations)
        prior = workflows.get(model.workflow_id)
        if prior is not None:
            if not nested or prior != model:
                raise ValueError('duplicate or divergent workflow identity')
            return model
        workflows[model.workflow_id] = model
        for _,key,item in canonical_workflow_items(model):
            support(model.workflow_id + ':' + key, item.support.observation_ids)
        return model

    for raw in payload.get('workflows', ()):
        workflow(raw)
    models = payload.get('operating_models', ())
    if len(models) != 1:
        raise ValueError('semantic candidate requires exactly one operating model')
    model = _typed(BusinessOperatingModel, models[0])
    if model.workspace_id != workspace_id or set(model.source_refs) != set(refs):
        raise ValueError('operating model source population mismatch')
    if len(set(model.finding_ids)) != len(model.finding_ids) or not set(model.finding_ids) <= findings.keys():
        raise ValueError('duplicate or absent company finding')
    validate_assembly(model, observations)
    for process in model.processes:
        support(process.process_id, process.observation_ids)
    for obj in model.objects:
        support(obj.object_id, obj.support.observation_ids)
    for interface in model.interfaces:
        support(interface.interface_id, interface.support.observation_ids)
    nested_ids = set()
    for item in model.workflows:
        workflow(item.model_dump(mode='json'), nested=True)
        nested_ids.add(item.workflow_id)
    if set(workflows) != nested_ids:
        raise ValueError('top-level workflow absent from operating model')
    for key, finding in findings.items():
        if key in evidence or key in observations:
            raise ValueError('finding projection identity collision')
        evidence[key] = finding.evidence_refs
    if 'consolidation_core' in payload:
        from .consolidation_contracts_v1 import ConsolidationCoreV1,validate_core_evidence
        core=ConsolidationCoreV1.model_validate_json(json.dumps(payload['consolidation_core']))
        if core.model!=model:raise PermissionError('temporal core model differs from captured model')
        temporal=validate_core_evidence(core,observations,{k:v.model_dump(mode='json') for k,v in findings.items()})
        if set(temporal)&evidence.keys():raise ValueError('temporal evidence identity collision')
        evidence.update(temporal)
    return evidence


def verify_ledger_semantic_acceptance(*, ledger, workspace_id, artifact_id, version,
        census, assessment, admission, trusted_admission_hashes, source_regions,
        runtime_hash, expected_compiler_digest, current_permission_digest, now,
        current_time=None):
    """Accept only independently admitted exact current bytes, not hosted release.

    ``candidate_created_at`` is the reviewed first-exposure provenance. Database
    persistence may occur later, but can never be used to invent an earlier freeze.
    Permission/runtime/compiler inputs come from the trusted coordinator.
    """
    def check_time():
        clock = current_time() if current_time else max(now, datetime.now(timezone.utc))
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError('semantic clock requires a timezone')
        if admission.expires_at <= clock:
            raise PermissionError('semantic admission expired')
        return clock

    if sealed(admission) not in trusted_admission_hashes:
        raise PermissionError('independent semantic admission unavailable')
    if ledger.principal != admission.assessor_actor or ledger.principal != assessment.assessor_actor:
        raise PermissionError('ledger principal must be the independent assessor')
    if admission.implementer_actor == admission.assessor_actor:
        raise PermissionError('implementer cannot assess its own work')
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('semantic clock requires a timezone')
    clock = check_time()
    if census.workspace_id != workspace_id or assessment.workspace_id != workspace_id:
        raise PermissionError('cross-workspace semantic assessment')
    pairs = ((sealed(census), admission.census_hash), (sealed(assessment), admission.assessment_hash),
        (runtime_hash, admission.runtime_hash), (assessment.census_hash, admission.census_hash),
        (assessment.candidate_hash, admission.candidate_hash),
        (assessment.permission_hash, admission.permission_hash),
        (assessment.protocol_hash, admission.protocol_hash),
        (digest({'regions': [r.model_dump(mode='json') for r in source_regions]}),
         admission.source_region_register_hash))
    if any(actual != expected for actual, expected in pairs) or census.regions != source_regions:
        raise PermissionError('semantic admission does not bind exact current inputs')
    if not census.frozen_at < admission.candidate_created_at <= assessment.assessed_at <= clock:
        raise PermissionError('source census was not frozen before candidate access')

    def metadata():
        if current_permission_digest(workspace_id, ledger.principal) != admission.permission_hash:
            raise PermissionError('current permission digest differs from admission')
        with psycopg.connect(ledger.url, row_factory=dict_row) as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            row = conn.execute('SELECT * FROM oracle2.artifact_manifests WHERE workspace_id=%s '
                'AND artifact_id=%s AND version=%s', (workspace_id, artifact_id, version)).fetchone()
            denied = conn.execute('SELECT 1 FROM oracle2.artifact_invalidations WHERE workspace_id=%s '
                'AND artifact_id=%s AND version=%s LIMIT 1', (workspace_id, artifact_id, version)).fetchone()
            source_rows = conn.execute("SELECT r.receipt->'ref' AS ref FROM oracle2.artifact_dependencies d "
                'JOIN oracle2.operating_model_source_receipts r ON r.workspace_id=d.workspace_id '
                'AND r.source_id::text=d.upstream_id AND r.revision::text=d.upstream_revision '
                'WHERE d.workspace_id=%s AND d.artifact_id=%s AND d.version=%s '
                "AND d.upstream_kind='source'", (workspace_id, artifact_id, version)).fetchall()
        if not row or denied:
            raise PermissionError('artifact unavailable or invalidated')
        manifest = _typed(ArtifactManifest, row['manifest'])
        columns = ArtifactManifest.model_validate({key: row[key] for key in ArtifactManifest.model_fields
                                                  if key != 'schema_version'})
        if manifest != columns or manifest.kind != 'operating_model' or manifest.state != 'ready':
            raise PermissionError('current operating model manifest unavailable or changed')
        if manifest.permission_digest != admission.permission_hash or manifest.compiler_digest != expected_compiler_digest:
            raise PermissionError('artifact permission or compiler seal differs')
        expected_sources = digest({'refs': [r.model_dump(mode='json') for r in census.source_refs]})
        if manifest.content_hash != admission.candidate_hash or manifest.source_digest != expected_sources:
            raise PermissionError('ledger candidate or source seal differs from admission')
        relational_refs = tuple(_typed(SourceRef, item['ref']) for item in source_rows)
        if len(set(relational_refs)) != len(relational_refs) or set(relational_refs) != set(census.source_refs):
            raise PermissionError('relational source population differs from admitted census')
        if row['created_at'] < admission.candidate_created_at:
            raise PermissionError('persisted artifact predates admitted candidate exposure')
        return manifest, row['created_at']

    initial = metadata()
    candidate = ledger.read(workspace_id, artifact_id, version)
    if digest(candidate) != admission.candidate_hash:
        raise PermissionError('candidate differs from admitted ledger content')
    receipts = ledger.authorize_refs(census.source_refs, workspace_id)
    evidence = ledger_object_evidence(candidate, workspace_id=workspace_id, receipts=receipts,
                                      inventories=ledger.reviewed_inventories)
    result = verify_semantic_acceptance(census=census, assessment=assessment, admission=admission,
        trusted_admission_hashes=trusted_admission_hashes, source_regions=source_regions,
        candidate=candidate, object_evidence=evidence, runtime_hash=runtime_hash,
        permission_hash=admission.permission_hash, candidate_created_at=admission.candidate_created_at,
        now=clock, current_source=ledger.current_source, can_read=ledger.can_read)
    if metadata() != initial:
        raise PermissionError('ledger manifest changed during semantic acceptance')
    if ledger.read(workspace_id, artifact_id, version) != candidate:
        raise PermissionError('ledger candidate changed during semantic acceptance')
    if metadata() != initial:
        raise PermissionError('ledger manifest changed during final read')
    check_time()
    return result
