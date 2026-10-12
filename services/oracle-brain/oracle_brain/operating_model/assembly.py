"""Deterministic assembly admission. Model suggestions never create identity or policy."""
from .model import BusinessOperatingModel
from .observations import Observation
from .workflows.process_validate import validate_workflow


def validate_assembly(model:BusinessOperatingModel, observations:dict[str,Observation], *, accepted_mapping_events:frozenset[str]=frozenset()) -> BusinessOperatingModel:
    manifest=set(model.source_refs)
    identities=[p.process_id for p in model.processes]+[o.object_id for o in model.objects]+[i.interface_id for i in model.interfaces]
    if len(set(identities))!=len(identities) or set(identities)&observations.keys():raise ValueError('assembly projection identity collision')
    def check(ids,scope=None):
        values=[]
        for oid in ids:
            o=observations.get(oid)
            if o is None or o.ref not in manifest or (scope is not None and o.scope!=scope):raise ValueError('unsupported or cross-scope assembly support')
            values.append(o)
        return values
    decisions={}
    for decision in model.assembly_decisions:
        inputs=check(decision.observation_ids,decision.scope)
        if decision.method=='authorized_mapping':
            if str(decision.authority_event_id) not in accepted_mapping_events:raise PermissionError('identity mapping lacks current scoped authority')
        elif any(decision.semantic_identity not in e.quote for o in inputs for e in o.evidence):
            raise ValueError('shared identity must be source-explicit, not similar labels')
        decisions[frozenset(decision.observation_ids)]=decision
    for process in model.processes:
        inputs=check(process.observation_ids,process.scope)
        sources={o.ref.source_id for o in inputs}
        if sources!=set(process.source_ids):raise ValueError('process source population mismatch')
        if len(sources)>1 and not any(sources <= {observations[oid].ref.source_id for oid in d.observation_ids} and d.scope==process.scope for d in model.assembly_decisions):
            raise ValueError('cross-document process join requires explicit admitted identity')
    for obj in model.objects:check(obj.support.observation_ids,obj.scope)
    for interface in model.interfaces:
        values=check(interface.support.observation_ids,interface.scope)
        artifact=next(o for o in model.objects if o.object_id==interface.artifact_id)
        endpoints=[p.label for p in model.processes if p.process_id in {interface.from_process,interface.to_process}]
        if interface.status=='supported' and not any(o.kind=='handoff' and all(label in e.quote for label in [artifact.label,*endpoints]) for o in values for e in o.evidence):
            raise ValueError('cross-process interface lacks explicit artifact handoff')
    for workflow in model.workflows:validate_workflow(workflow,observations)
    return model
