"""Four-role LangGraph, without cycles, provider retries or company report dispatch."""
import json
from typing import TypedDict
from langgraph.graph import StateGraph,END
from ..consultant.process_analysis import Report
from ..consultant.challenge import validate_report

class State(TypedDict):
    calls:int
    roles:dict
    challenge_passed:bool


def consult(pack,*,generate,synthetic:bool,metrics=None,event_artifact_hash=None):
    if not synthetic:raise PermissionError('company report generation remains paused')
    if pack.get('state')!='ready':return {'state':'limited','reason':'coverage_incomplete','calls':0}
    graph=StateGraph(State)
    attempts={'count':0}
    original_pack=json.dumps(pack,sort_keys=True)
    original_metrics=json.dumps(metrics,sort_keys=True) if metrics is not None else None
    def role(name):
        def node(state):
            if state['calls']>=4:raise RuntimeError('consulting generation ceiling exceeded')
            attempts['count']+=1
            raw=generate(name,json.loads(json.dumps({'pack':pack,'metrics':metrics,'event_artifact_hash':event_artifact_hash,'prior':state['roles']})))
            if json.dumps(pack,sort_keys=True)!=original_pack or (json.dumps(metrics,sort_keys=True) if metrics is not None else None)!=original_metrics:raise ValueError('report role mutated sealed inputs')
            roles={**state['roles'],name:raw}
            challenge_passed=state['challenge_passed']
            if name=='planner' and (not isinstance(raw,dict) or set(raw.get('operations',[]))-{'documentary_map','describe_metrics','propose_measurement'}):raise ValueError('planner requested unapproved operation')
            if name=='challenger':challenge_passed=isinstance(raw,dict) and raw.get('supported') is True
            return {'calls':state['calls']+1,'roles':roles,'challenge_passed':challenge_passed}
        return node
    for name in ('planner','analyst','challenger','writer'):graph.add_node(name,role(name))
    graph.set_entry_point('planner');graph.add_edge('planner','analyst');graph.add_edge('analyst','challenger');graph.add_edge('challenger','writer');graph.add_edge('writer',END)
    try:
        result=graph.compile().invoke({'calls':0,'roles':{},'challenge_passed':False},{'recursion_limit':8})
        report=Report.model_validate_json(json.dumps(result['roles']['writer']))
        validate_report(report,pack,metrics=metrics,event_artifact_hash=event_artifact_hash)
        if not result['challenge_passed']:
            return {'state':'limited','reason':'independent role challenge did not pass','calls':result['calls']}
        return {'state':report.state,'report':report.model_dump(mode='json'),'calls':result['calls']}
    except (ValueError,RuntimeError,PermissionError):
        return {'state':'limited','reason':'bounded report contract failed; source model preserved','calls':attempts['count']}
