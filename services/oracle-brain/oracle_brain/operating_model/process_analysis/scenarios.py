"""Typed documentary traversals; conditions never execute source expressions."""

def traverse(model,*,transition_ids:tuple[str,...]):
    edges={e.transition_id:e for e in model.transitions}
    steps={s.step_id:s for s in model.steps}
    position=None
    for eid in transition_ids:
        edge=edges.get(eid)
        if edge is None:raise ValueError('unknown scenario transition')
        if position is None and (edge.from_id not in steps or steps[edge.from_id].kind!='start'):raise ValueError('scenario must begin at explicit start')
        if position is not None and position!=edge.from_id:raise ValueError('scenario sequence is disconnected')
        position=edge.to_id
    return {'state':'documentary_path','end_id':position,'source_condition_execution':False,'parallel_token_semantics_checked':False}
