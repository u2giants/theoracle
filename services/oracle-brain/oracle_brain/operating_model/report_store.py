"""Persist bounded synthetic report contracts with both documentary and event lineage."""
import json
from .contracts import digest,canonical_bytes
from .retrieval import build_pack
from .source_receipts import SourceRef
from .process_analysis.event_contracts import LogReceipt
from .process_analysis.metrics import measured_metrics
from .workflows.process_consult import consult

def derive_report_evidence(*,workspace_id,model_id,model_version,model_manifest,model_payload,
                          plan,pack,event_id=None,event_version=None,event_manifest=None,
                          event_payload=None,metrics=None):
    """Server-owned complete upstream binding; no containing-report hash cycle."""
    from uuid import UUID
    from .consultant.recommendations import EvidenceRevision
    if type(workspace_id) is not UUID or type(model_id) is not UUID or type(model_version) is not int or model_version<1:
        raise ValueError('exact upstream model identity required')
    if (model_manifest.workspace_id!=workspace_id or model_manifest.artifact_id!=model_id or
            model_manifest.version!=model_version or model_manifest.content_hash!=digest(model_payload)):
        raise ValueError('upstream model manifest identity mismatch')
    if pack.get('state')!='ready' or pack.get('artifact_hash')!=model_manifest.content_hash:
        raise ValueError('complete current report evidence pack required')
    if len(canonical_bytes(pack))>plan.max_bytes:
        raise ValueError('complete upstream evidence exceeds report budget')
    refs=['citation:'+digest(citation) for citation in pack.get('citations',())]
    model_refs=model_payload['source_refs']
    binding={'workspace_id':str(workspace_id),'model_artifact_id':str(model_id),
        'model_version':model_version,'model_content_hash':model_manifest.content_hash,
        'model_permission_digest':model_manifest.permission_digest,
        'query_plan_hash':digest(plan.model_dump(mode='json')),'pack_hash':digest(pack),
        'model_source_refs':model_refs,'event':None}
    if event_id is not None:
        if (type(event_id) is not UUID or type(event_version) is not int or event_version<1 or
                event_manifest is None or event_payload is None or metrics is None):
            raise ValueError('complete exact measured event identity required')
        if (event_manifest.workspace_id!=workspace_id or event_manifest.artifact_id!=event_id or
                event_manifest.version!=event_version or event_manifest.content_hash!=digest(event_payload)):
            raise ValueError('upstream event manifest identity mismatch')
        binding['event']={'artifact_id':str(event_id),'version':event_version,
            'content_hash':event_manifest.content_hash,'permission_digest':event_manifest.permission_digest,
            'source_refs':event_payload['source_refs'],'metrics_hash':digest(metrics)}
        refs.append('event:'+event_manifest.content_hash)
    elif any(value is not None for value in (event_version,event_manifest,event_payload,metrics)):
        raise ValueError('documentary report cannot infer a measured event')
    seal=digest(binding)
    return EvidenceRevision(seal,tuple(refs),seal)


def persist_report(ledger,*,workspace_id,model_id,model_version,report_id,report_version,plan,generate,synthetic,
                   permission_digest,compiler_digest,event_id=None,event_version=None,report_schema_version=1):
    if not synthetic:raise PermissionError('company report generation remains paused')
    if type(report_schema_version) is not int or report_schema_version not in (1,2):
        raise ValueError('unsupported requested report schema')
    model_manifest=None
    if report_schema_version==2:model_manifest,model=ledger.read_with_manifest(workspace_id,model_id,model_version)
    else:model=ledger.read(workspace_id,model_id,model_version)
    pack=build_pack(model,plan)
    refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in model['source_refs'])
    dependencies=[('artifact',str(model_id),str(model_version))]
    metrics=None;event_hash=None;event_manifest=None;event=None
    if event_id is not None:
        if event_version is None:raise ValueError('exact event version required')
        if report_schema_version==2:event_manifest,event=ledger.read_with_manifest(workspace_id,event_id,event_version)
        else:event=ledger.read(workspace_id,event_id,event_version)
        if event.get('actual_data_acceptance')!='unavailable':raise PermissionError('actual event acceptance cannot be inferred')
        log=LogReceipt.model_validate_json(json.dumps(event['event_import']))
        if log.import_id!=event_id:raise ValueError('event artifact identity mismatch')
        process_ids={p['process_id'] for p in pack.get('processes',())}
        if event['mapping']['process_id'] not in process_ids:raise ValueError('event window outside documentary scope')
        metrics=measured_metrics(log);event_hash=digest(event)
        refs=tuple(dict.fromkeys((*refs,*(SourceRef.model_validate_json(json.dumps(r)) for r in event['source_refs']))))
        dependencies.append(('artifact',str(event_id),str(event_version)))
    if len(canonical_bytes({'pack':pack,'metrics':metrics}))>plan.max_bytes:
        return {'state':'limited','reason':'complete measured evidence exceeds report budget','calls':0}
    expected_evidence=None
    if report_schema_version==2:
        if pack.get('state')!='ready':return {'state':'limited','reason':'coverage_incomplete','calls':0}
        expected_evidence=derive_report_evidence(workspace_id=workspace_id,model_id=model_id,
            model_version=model_version,model_manifest=model_manifest,model_payload=model,plan=plan,pack=pack,
            event_id=event_id,event_version=event_version,event_manifest=event_manifest,event_payload=event,metrics=metrics)
    result=consult(pack,generate=generate,synthetic=True,metrics=metrics,event_artifact_hash=event_hash,
                   report_schema_version=report_schema_version,expected_evidence=expected_evidence)
    if result['state']!='ready':return result
    if ledger.read(workspace_id,model_id,model_version)!=model:raise PermissionError('model input changed')
    if event_id is not None and digest(ledger.read(workspace_id,event_id,event_version))!=event_hash:raise PermissionError('event input changed')
    payload={'source_refs':[r.model_dump(mode='json') for r in refs],'report':result['report'],'calls':result['calls'],'synthetic':True,
             'model_id':str(model_id),'model_version':model_version,'event_id':str(event_id) if event_id else None,'event_version':event_version,'query_plan':plan.model_dump(mode='json')}
    if report_schema_version==2 and len(canonical_bytes(payload))>plan.max_bytes:
        return {'state':'limited','reason':'complete recommendation report exceeds report budget','calls':result['calls']}
    manifest=ledger.persist(workspace_id=workspace_id,artifact_id=report_id,version=report_version,kind='report',payload=payload,refs=refs,
        permission_digest=permission_digest,compiler_digest=compiler_digest,dependencies=tuple(dependencies))
    if report_schema_version==2:
        if ledger.read(workspace_id,report_id,report_version)!=payload:raise PermissionError('persisted report changed')
        if ledger.read_with_manifest(workspace_id,model_id,model_version)!=(model_manifest,model):raise PermissionError('current model input changed')
        if event_id is not None and ledger.read_with_manifest(workspace_id,event_id,event_version)!=(event_manifest,event):raise PermissionError('current event input changed')
    return {'state':'ready','artifact_id':str(manifest.artifact_id),'version':manifest.version,'content_hash':manifest.content_hash,'calls':result['calls'],'actual_data_acceptance':result['report']['actual_data_acceptance']}

def serve_report(ledger,workspace_id,report_id,version):
    from .consultant.process_analysis import parse_report
    from .consultant.challenge import validate_report
    payload=ledger.read(workspace_id,report_id,version)
    if payload.get('synthetic') is not True:raise PermissionError('company report serving remains paused')
    from uuid import UUID
    from .retrieval import QueryPlan
    report=parse_report(payload['report'])
    model_manifest=None
    if report.schema_version==2:
        report_manifest,current_payload=ledger.read_with_manifest(workspace_id,report_id,version)
        if report_manifest.kind!='report' or current_payload!=payload:raise PermissionError('exact report identity changed')
        model_manifest,model=ledger.read_with_manifest(workspace_id,UUID(payload['model_id']),payload['model_version'])
    else:model=ledger.read(workspace_id,UUID(payload['model_id']),payload['model_version'])
    plan=QueryPlan.model_validate_json(json.dumps(payload['query_plan']));pack=build_pack(model,plan)
    metrics=None;event_hash=None;event_manifest=None;event=None
    if payload.get('event_id'):
        if report.schema_version==2:event_manifest,event=ledger.read_with_manifest(workspace_id,UUID(payload['event_id']),payload['event_version'])
        else:event=ledger.read(workspace_id,UUID(payload['event_id']),payload['event_version'])
        event_hash=digest(event);metrics=measured_metrics(LogReceipt.model_validate_json(json.dumps(event['event_import'])))
    expected_evidence=None
    if report.schema_version==2:
        expected_evidence=derive_report_evidence(workspace_id=workspace_id,model_id=UUID(payload['model_id']),
            model_version=payload['model_version'],model_manifest=model_manifest,model_payload=model,plan=plan,pack=pack,
            event_id=UUID(payload['event_id']) if payload.get('event_id') else None,event_version=payload['event_version'],
            event_manifest=event_manifest,event_payload=event,metrics=metrics)
    validate_report(report,pack,metrics=metrics,event_artifact_hash=event_hash,expected_evidence=expected_evidence)
    if report.schema_version==2:
        if ledger.read_with_manifest(workspace_id,report_id,version)!=(report_manifest,payload):raise PermissionError('report access changed before serving')
        if ledger.read_with_manifest(workspace_id,UUID(payload['model_id']),payload['model_version'])!=(model_manifest,model):raise PermissionError('model access changed before serving')
        if payload.get('event_id') and ledger.read_with_manifest(workspace_id,UUID(payload['event_id']),payload['event_version'])!=(event_manifest,event):raise PermissionError('event access changed before serving')
    return report
