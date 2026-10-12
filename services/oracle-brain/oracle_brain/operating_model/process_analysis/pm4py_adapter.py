"""PM4Py capability stays unavailable until exact license/runtime qualification."""
import re
from importlib.metadata import version,PackageNotFoundError
from .compiler import compile_contract

PIN='2.7.22'


def analyze(model,*,qualification):
    compiled=compile_contract(model)
    if compiled['state']!='compiled':return compiled
    if not qualification or qualification.get('version')!=PIN or qualification.get('deployment_fit')!='APPROVE' or qualification.get('runtime_resource_fit')!='APPROVE' or not re.fullmatch(r'[0-9a-f]{64}',qualification.get('review_report_hash','')):
        return {'state':'unavailable','reason':'PM4Py exact deployment/license qualification required','model':model.model_dump(mode='json')}
    return _analyze_compiled(compiled,model.workflow_id)

def _analyze_compiled(compiled,workflow_id):
    # Private operation, called after admission or by the isolated qualification harness.
    try:
        installed=version('pm4py')
    except PackageNotFoundError:
        return {'state':'unavailable','reason':'Qualified PM4Py runtime not installed','model':compiled['model']}
    if installed!=PIN:raise RuntimeError('analytical runtime dependency mismatch')
    net,initial,final=build_net(compiled,workflow_id)
    from pm4py import check_soundness
    sound,diagnostics=check_soundness(net,initial,final)
    return {'state':'analyzed','structural_soundness':bool(sound),'company_truth_accepted':False,'compiler':compiled['compiler'],'step_map':compiled['step_map'],'transition_map':compiled['transition_map'],'diagnostic_keys':sorted(str(getattr(key,'value',key)) for key in diagnostics)}

def build_net(compiled,workflow_id):
    # Called only inside the separately admitted bounded worker.
    from pm4py.objects.petri_net.obj import PetriNet,Marking
    from pm4py.objects.petri_net.utils.petri_utils import add_arc_from_to
    net=PetriNet(workflow_id);places={p:PetriNet.Place(p) for p in compiled['places']}
    transitions={t['id']:PetriNet.Transition(t['id'],t['label']) for t in compiled['transitions']}
    net.places.update(places.values());net.transitions.update(transitions.values())
    nodes={**places,**transitions}
    for a,b in compiled['arcs']:add_arc_from_to(nodes[a],nodes[b],net)
    initial=Marking({places[compiled['initial']]:1});final=Marking({places[compiled['final']]:1})
    return net,initial,final
