"""Fixed operations, cancellable subprocess, preserved original map on exhaustion.

Runtime remains unqualified and uninstalled until W04a admission. These limits
are proposed, not a claim of measured PM4Py resource fit.
"""
import json,multiprocessing,queue,re,os,signal
from .compiler import compile_contract
from .pm4py_adapter import PIN,analyze,build_net,_analyze_compiled
from .event_contracts import LogReceipt
from .metrics import measured_metrics
from ..workflows.process_model import WorkflowModel
from ..contracts import digest

OPERATIONS=frozenset({'structural','discovery','conformance'})

def admitted(qualification):
    return bool(qualification and qualification.get('version')==PIN and qualification.get('deployment_fit')=='APPROVE'
                and re.fullmatch(r'[0-9a-f]{64}',qualification.get('review_report_hash','')) and qualification.get('runtime_resource_fit')=='APPROVE')

def _worker(model_json,operation,log_json,qualification,output):
    if not admitted(qualification):
        output.put({"state":"unavailable","reason":"Exact product admission required"});return
    _execute_operation(model_json,operation,log_json,output)

def _execute_operation(model_json,operation,log_json,output):
    # Private analytical operation used by the admitted worker and isolated test harness.
    try:
        import resource,os
        os.environ["OPENBLAS_NUM_THREADS"]="1"
        os.environ["OMP_NUM_THREADS"]="1"
        os.environ["MPLBACKEND"]="Agg"
        resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(30,30))
        model=WorkflowModel.model_validate_json(model_json)
        if operation=='structural':result=_analyze_compiled(compile_contract(model),model.workflow_id)
        else:
            from importlib.metadata import version
            if version('pm4py')!=PIN:raise RuntimeError('exact analytical runtime required')
            log=LogReceipt.model_validate_json(log_json);metrics=measured_metrics(log)
            if any(v=='unordered' for v in metrics['variants'].values()):raise ValueError('unordered cases cannot establish execution paths')
            eligible=set(metrics['event_ids'])-set(log.case_censoring)
            eligible={c for c in eligible if not any(e.status!='completed' for e in log.events if e.case_id==c)}
            import pandas as pd
            events=sorted((e for e in log.events if e.case_id in eligible and e.lifecycle in {'point','complete'}),key=lambda e:(e.case_id,e.timestamp,e.tie_order if e.tie_order is not None else 0))
            if not events:raise ValueError('no complete ordered cases for analysis')
            frame=pd.DataFrame([{'case:concept:name':e.case_id,'concept:name':e.activity_id,'time:timestamp':e.timestamp} for e in events])
            if operation=='discovery':
                from pm4py import discover_petri_net_inductive
                net,initial,final=discover_petri_net_inductive(frame,noise_threshold=0.0,multi_processing=False)
                result={'state':'analyzed','observed_model':{'places':len(net.places),'transitions':sorted(t.label for t in net.transitions if t.label is not None)},'observed_is_documented_policy':False}
            else:
                compiled=compile_contract(model)
                if compiled['state']!='compiled':raise ValueError('documented model not formally analyzable')
                if not {e.activity_id for e in events}<={s.step_id for s in model.steps}:raise ValueError('explicit event-to-step mapping required')
                net,initial,final=build_net(compiled,model.workflow_id)
                from pm4py import conformance_diagnostics_token_based_replay
                diagnostics=conformance_diagnostics_token_based_replay(frame,net,initial,final,return_diagnostics_dataframe=False)
                cases=sorted(eligible)
                if len(diagnostics)!=len(cases):raise ValueError('conformance case population mismatch')
                result={'state':'analyzed','case_diagnostics':[{'case_id':case,'fits':bool(raw['trace_is_fit']),'missing_tokens':int(raw['missing_tokens']),'remaining_tokens':int(raw['remaining_tokens'])} for case,raw in zip(cases,diagnostics)],'deviations_are_policy_failures':False}
            result.update({'metrics':metrics,'event_artifact_hash':digest(log.model_dump(mode='json')),'event_ids':metrics['event_ids'],'actual_data_acceptance':'unavailable'})
        output.put(result)
    except Exception:output.put({'state':'incomplete','reason':'Qualified analytical execution failed; original map retained'})

def run_bounded(model,*,operation,qualification,log=None,timeout_seconds=30):
    original=model.model_dump(mode='json')
    if operation not in OPERATIONS or not 0<timeout_seconds<=30:raise ValueError('operation or resource bound not admitted')
    if not admitted(qualification):return {'state':'unavailable','reason':'Exact license and measured runtime qualification required','model':original}
    if compile_contract(model)['state']!='compiled':return {'state':'not_analyzable','model':original}
    if operation!='structural' and log is None:return {'state':'unavailable','reason':'Admitted event export required','model':original}
    return _execute_bounded(original,_worker,(model.model_dump_json(),operation,log.model_dump_json() if log else None,qualification),timeout_seconds)

def _isolated_worker(worker,args,output,ready):
    # Own a new session before any analytical code can spawn a native solver.
    os.setsid()
    ready.send(os.getpid());ready.close()
    worker(*args,output)

def _execute_bounded(original,worker,args,timeout_seconds):
    # Private process mechanism; callers cannot choose a product operation or target.
    context=multiprocessing.get_context('spawn');output=context.Queue(maxsize=1)
    ready,child_ready=context.Pipe(duplex=False)
    process=context.Process(target=_isolated_worker,args=(worker,args,output,child_ready))
    process.start();process.join(timeout_seconds)
    child_ready.close()
    try:owned_group=ready.poll() and ready.recv()==process.pid
    except EOFError:owned_group=False
    ready.close()
    if process.is_alive():
        if owned_group:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        else:process.terminate()
        process.join(2)
        if owned_group:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        elif process.is_alive():process.kill()
        process.join(2)
        result={'state':'incomplete','reason':'Analytical timeout; original map retained'}
    else:
        try:result=output.get(timeout=.5)
        except queue.Empty:result={'state':'incomplete','reason':'Analytical memory or process exhaustion; original map retained'}
        if owned_group:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    output.close();output.join_thread()
    return {**result,'model':original,'resource_bounds':{'seconds':timeout_seconds,'memory_bytes':512*1024*1024},'company_truth_accepted':False}
