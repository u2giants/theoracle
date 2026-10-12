from .process_model import WorkflowModel
from ..observations import Observation

def validate_workflow(model: WorkflowModel, observations: dict[str, Observation]) -> WorkflowModel:
    refs = set(model.source_refs)
    supports = []
    for item in (*model.steps, *model.gateways, *model.conditions, *model.transitions, *model.roles, *model.artifacts, *model.handoffs):
        supports.append(item.support)
    for support in supports:
        for observation_id in support.observation_ids:
            obs = observations.get(observation_id)
            if obs is None: raise ValueError("missing observation support")
            if obs.ref not in refs or obs.scope != model.scope: raise ValueError("observation support outside model")
    return model

def formal_eligible(model: WorkflowModel) -> bool:
    if model.completeness != "complete" or model.status not in {"reported", "confirmed"}: return False
    if any(g.kind == "unsupported" for g in model.gateways) or any(c.applicability != "known" for c in model.conditions): return False
    starts = {s.step_id for s in model.steps if s.kind == "start"}; ends = {s.step_id for s in model.steps if s.kind == "end"}
    if not starts or not ends: return False
    outgoing = {n: 0 for n in {s.step_id for s in model.steps} | {g.gateway_id for g in model.gateways}}
    incoming = dict(outgoing)
    for t in model.transitions: outgoing[t.from_id] += 1; incoming[t.to_id] += 1
    for node in outgoing:
        if node not in ends and outgoing[node] == 0: return False
        if node not in starts and incoming[node] == 0: return False
    for g in model.gateways:
        if g.kind.endswith("split") and outgoing[g.gateway_id] < 2: return False
        if g.kind.endswith("join") and incoming[g.gateway_id] < 2: return False
    return True
