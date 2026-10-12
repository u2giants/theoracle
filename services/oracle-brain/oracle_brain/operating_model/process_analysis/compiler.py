"""Pure bounded Petri contract. Formal success never establishes company truth."""
from ..contracts import digest
from ..workflows.process_validate import formal_eligible

MAX_STEPS=250
MAX_EDGES=500
MAX_GATEWAYS=50


def compile_contract(model):
    original=model.model_dump(mode='json')
    if len(model.steps)>MAX_STEPS or len(model.transitions)>MAX_EDGES or len(model.gateways)>MAX_GATEWAYS:
        return {'state':'not_analyzable','reason':'Qualified resource bounds exceeded','model':original}
    if not formal_eligible(model):
        return {'state':'not_analyzable','reason':'Partial, unsupported or unspecified workflow semantics','model':original}
    places={f'edge:{e.transition_id}' for e in model.transitions}
    places.update(('compiler:start','compiler:end'))
    transitions=[];arcs=[];step_map={};edge_map={e.transition_id:f'edge:{e.transition_id}' for e in model.transitions}
    incoming={n:[] for n in [s.step_id for s in model.steps]+[g.gateway_id for g in model.gateways]}
    outgoing={n:[] for n in incoming}
    for edge in model.transitions:
        incoming[edge.to_id].append('edge:'+edge.transition_id)
        outgoing[edge.from_id].append('edge:'+edge.transition_id)
    def add(identifier,label,ins,outs,origin):
        transitions.append({'id':identifier,'label':label,'origin_id':origin})
        arcs.extend((p,identifier) for p in ins);arcs.extend((identifier,p) for p in outs)
    for step in model.steps:
        # Implicit forks/joins at activities are unsupported; gateways must be explicit.
        if len(incoming[step.step_id])>1 or len(outgoing[step.step_id])>1:
            return {'state':'not_analyzable','reason':'Implicit step control flow requires explicit gateways','model':original}
        identifier='step:'+step.step_id;step_map[step.step_id]=identifier
        ins=incoming[step.step_id] or (['compiler:start'] if step.kind=='start' else [])
        outs=outgoing[step.step_id] or (['compiler:end'] if step.kind in {'end','rejection'} else [])
        add(identifier,step.step_id,ins,outs,step.step_id)
    for gateway in model.gateways:
        ins,outs=incoming[gateway.gateway_id],outgoing[gateway.gateway_id]
        if gateway.kind=='exclusive_split':
            if len(ins)!=1:return {'state':'not_analyzable','reason':'Unsupported XOR split inputs','model':original}
            for n,p in enumerate(outs):add(f'gateway:{gateway.gateway_id}:{n}',None,ins,[p],gateway.gateway_id)
        elif gateway.kind=='exclusive_join':
            if len(outs)!=1:return {'state':'not_analyzable','reason':'Unsupported XOR join outputs','model':original}
            for n,p in enumerate(ins):add(f'gateway:{gateway.gateway_id}:{n}',None,[p],outs,gateway.gateway_id)
        elif gateway.kind in {'parallel_split','parallel_join'}:
            if (gateway.kind=='parallel_split' and len(ins)!=1) or (gateway.kind=='parallel_join' and len(outs)!=1):return {'state':'not_analyzable','reason':'Unsupported AND gateway degree','model':original}
            add('gateway:'+gateway.gateway_id,None,ins,outs,gateway.gateway_id)
    return {'state':'compiled','model_hash':digest(original),'model':original,'places':sorted(places),'transitions':transitions,'arcs':sorted(arcs),'step_map':step_map,'transition_map':edge_map,'initial':'compiler:start','final':'compiler:end','plumbing_is_company_fact':False,'compiler':'oracle-petri-contract-v1'}
