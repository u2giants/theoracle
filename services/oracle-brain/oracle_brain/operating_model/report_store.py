"""Persist bounded synthetic report contracts with both documentary and event lineage."""
import json
from .contracts import digest,canonical_bytes
from .retrieval import build_pack
from .source_receipts import SourceRef
from .process_analysis.event_contracts import LogReceipt
from .process_analysis.metrics import measured_metrics
from .workflows.process_consult import consult

def persist_report(ledger,*,workspace_id,model_id,model_version,report_id,report_version,plan,generate,synthetic,
                   permission_digest,compiler_digest,event_id=None,event_version=None):
    if not synthetic:raise PermissionError('company report generation remains paused')
    model=ledger.read(workspace_id,model_id,model_version);pack=build_pack(model,plan)
    refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in model['source_refs'])
    dependencies=[('artifact',str(model_id),str(model_version))]
    metrics=None;event_hash=None
    if event_id is not None:
        if event_version is None:raise ValueError('exact event version required')
        event=ledger.read(workspace_id,event_id,event_version)
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
    result=consult(pack,generate=generate,synthetic=True,metrics=metrics,event_artifact_hash=event_hash)
    if result['state']!='ready':return result
    ledger.read(workspace_id,model_id,model_version)
    if event_id is not None and digest(ledger.read(workspace_id,event_id,event_version))!=event_hash:raise PermissionError('event input changed')
    payload={'source_refs':[r.model_dump(mode='json') for r in refs],'report':result['report'],'calls':result['calls'],'synthetic':True,
             'model_id':str(model_id),'model_version':model_version,'event_id':str(event_id) if event_id else None,'event_version':event_version,'query_plan':plan.model_dump(mode='json')}
    manifest=ledger.persist(workspace_id=workspace_id,artifact_id=report_id,version=report_version,kind='report',payload=payload,refs=refs,
        permission_digest=permission_digest,compiler_digest=compiler_digest,dependencies=tuple(dependencies))
    return {'state':'ready','artifact_id':str(manifest.artifact_id),'version':manifest.version,'content_hash':manifest.content_hash,'calls':result['calls'],'actual_data_acceptance':result['report']['actual_data_acceptance']}

def serve_report(ledger,workspace_id,report_id,version):
    from .consultant.process_analysis import Report
    from .consultant.challenge import validate_report
    payload=ledger.read(workspace_id,report_id,version)
    if payload.get('synthetic') is not True:raise PermissionError('company report serving remains paused')
    from uuid import UUID
    from .retrieval import QueryPlan
    model=ledger.read(workspace_id,UUID(payload['model_id']),payload['model_version'])
    plan=QueryPlan.model_validate_json(json.dumps(payload['query_plan']));pack=build_pack(model,plan)
    metrics=None;event_hash=None
    if payload.get('event_id'):
        event=ledger.read(workspace_id,UUID(payload['event_id']),payload['event_version'])
        event_hash=digest(event);metrics=measured_metrics(LogReceipt.model_validate_json(json.dumps(event['event_import'])))
    report=Report.model_validate_json(json.dumps(payload['report']))
    validate_report(report,pack,metrics=metrics,event_artifact_hash=event_hash)
    return report
