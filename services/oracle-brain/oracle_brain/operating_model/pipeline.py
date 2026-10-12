"""Source-only assembly from current immutable extractions; no question/report route."""
import json
from .model import BusinessOperatingModel
from .observations import Observation
from .source_receipts import SourceRef,EvidenceRef
from .assembly import validate_assembly
from .coverage import validate_coverage


def persist_assembly(ledger,raw_response,*,workspace_id,artifact_id,version,extractions,obligations,coverage_records,inventory_hash,permission_digest,compiler_digest):
    # Reads and access checks precede parsing; failed suggestions retain the full raw response.
    refs=[];observations={};findings={};dependencies=[]
    for source_artifact,source_version in extractions:
        current=ledger.read(workspace_id,source_artifact,source_version)
        dependencies.append(('artifact',str(source_artifact),str(source_version)))
        for raw in current['source_refs']:
            ref=SourceRef.model_validate_json(json.dumps(raw))
            if ref not in refs:refs.append(ref)
        for raw in current.get('observations',[]):
            observation=Observation.model_validate_json(json.dumps(raw))
            prior=observations.get(observation.observation_id)
            if prior is not None and prior!=observation:raise ValueError('upstream observation identity collision')
            observations[observation.observation_id]=observation
        for raw in current.get('findings',[]):
            key=raw['finding_id']
            if key in findings and findings[key]!=raw:raise ValueError('upstream finding identity collision')
            findings[key]=raw
    if not refs or not obligations:raise ValueError('current source extractions and independent obligations required')
    base={'source_refs':[r.model_dump(mode='json') for r in refs]}
    try:
        model=BusinessOperatingModel.model_validate_json(raw_response)
        if model.workspace_id!=workspace_id or set(model.source_refs)!=set(refs):raise ValueError('assembly must account for the exact admitted source population')
        validate_assembly(model,observations)
        if not set(model.finding_ids)<=findings.keys() or any(not set(w.finding_ids)<=findings.keys() for w in model.workflows):raise ValueError('assembly finding absent from current extraction')
        if any(w.status!='reported' for w in model.workflows):raise PermissionError('suggestions cannot confer company policy')
        evidence={}
        def support(identifier,ids):
            evidence[identifier]=tuple(e for oid in ids for e in observations[oid].evidence)
        for p in model.processes:support(p.process_id,p.observation_ids)
        for o in model.objects:support(o.object_id,o.support.observation_ids)
        for i in model.interfaces:support(i.interface_id,i.support.observation_ids)
        for w in model.workflows:
            for item in (*w.steps,*w.gateways,*w.transitions,*w.roles,*w.artifacts,*w.handoffs,*w.conditions):
                key=next(getattr(item,k) for k in ('step_id','gateway_id','transition_id','assignment_id','artifact_id','handoff_id','condition_id') if hasattr(item,k))
                support(w.workflow_id+':'+key,item.support.observation_ids)
        for key,f in findings.items():evidence[key]=tuple(EvidenceRef.model_validate_json(json.dumps(e)) for e in f['evidence_refs'])
        coverage=validate_coverage(obligations,coverage_records,object_evidence=evidence,independent_inventory_hash=inventory_hash)
        payload={**base,'observations':[o.model_dump(mode='json') for o in observations.values()],'findings':list(findings.values()),'workflows':[w.model_dump(mode='json') for w in model.workflows],'operating_models':[model.model_dump(mode='json')],'raw_response':raw_response,'coverage':coverage}
    except (ValueError,KeyError,PermissionError,TypeError) as exc:
        ledger.persist(workspace_id=workspace_id,artifact_id=artifact_id,version=version,kind='failed_assembly',payload={**base,'raw_response':raw_response,'failure_class':type(exc).__name__},refs=tuple(refs),permission_digest=permission_digest,compiler_digest=compiler_digest,dependencies=tuple(dependencies),failed=True)
        raise ValueError('assembly rejected; complete response retained') from None
    return ledger.persist(workspace_id=workspace_id,artifact_id=artifact_id,version=version,kind='operating_model',payload=payload,refs=tuple(refs),permission_digest=permission_digest,compiler_digest=compiler_digest,dependencies=tuple(dependencies))


def dispatch_source(ledger,provider,receipt,*,artifact_id,version,batch_id,permission_digest,compiler_digest,attempt=1):
    from .extraction import ExtractionResponse,persist_response
    ledger.authorize_refs((receipt.ref,),receipt.ref.workspace_id)
    messages=[{'role':'system','content':'Extract literal documentary observations and unresolved findings only. No company questions, reports, recommendations or policy promotion. Return exactly the provided JSON schema: '+json.dumps(ExtractionResponse.model_json_schema(),sort_keys=True)},
              {'role':'user','content':json.dumps({'source_ref':receipt.ref.model_dump(mode='json'),'reading':receipt.reading},ensure_ascii=False)}]
    bound=len(json.dumps(messages,ensure_ascii=False).encode())+1024*len(messages)
    raw=provider.extract(workspace_id=receipt.ref.workspace_id,artifact_id=artifact_id,batch_id=batch_id,purpose='source-extraction',attempt=attempt,input_tokens_upper_bound=bound,messages=messages)
    if not isinstance(raw,str):raw=json.dumps(raw,ensure_ascii=False,allow_nan=False)
    return persist_response(ledger,receipt,raw,artifact_id=artifact_id,version=version,permission_digest=permission_digest,compiler_digest=compiler_digest)
