"""Deterministic synthetic documentary explanations; company questions stay paused."""
import json
from typing import Literal
from .contracts import StrictRecord
from .source_receipts import EvidenceRef

Intent=Literal['overview','process_steps','roles','artifacts','interfaces','findings']
SUGGESTION_PREFIX='Suggested improvement: '
class Answer(StrictRecord):
    state:Literal['answered','abstained']
    intent:Intent
    records:tuple[dict,...]=()
    findings:tuple[dict,...]=()
    citations:tuple[EvidenceRef,...]=()
    caveats:tuple[str,...]
    artifact_hash:str

def labeled_suggestions(findings)->tuple[str,...]:
    """Deterministic suggestion lines from linked unknown/conflict findings only.

    Every line is separately labeled and never established fact or a staff-contact
    action. Unsupported finding kinds contribute no suggestion.
    """
    out=[]
    for finding in findings:
        if type(finding) is not dict:continue
        kind=finding.get('kind')
        if kind=='missing_information':
            line=SUGGESTION_PREFIX+'Record an explicit handoff owner after authorized review.'
        elif kind=='source_conflict':
            line=SUGGESTION_PREFIX+'Resolve the reported source conflict after authorized review.'
        else:continue
        if line not in out:out.append(line)
    return tuple(out)

def answer_from_summary(ledger,summary,*,intent:Intent,process_id:str|None=None,qualification_guard=None):
    if intent not in {'overview','process_steps','roles','artifacts','interfaces','findings'}:raise ValueError('unsupported documentary intent')
    summary.recheck(ledger,qualification_guard=qualification_guard);p=summary.pack.contents
    findings=tuple(p.get('findings',()))
    caveats=tuple(f['text'] for f in findings)
    if p.get('coverage_state')=='partial':caveats+=('Reported operating coverage remains partial.',)
    if p.get('continuation'):caveats+=('This page does not represent the whole declared population.',)
    caveats=caveats+labeled_suggestions(findings)
    available={x['process_id'] for x in p.get('processes',())}
    if p['state']!='ready' or (intent!='overview' and process_id is None) or (process_id is not None and process_id not in available):
        return Answer(state='abstained',intent=intent,caveats=caveats+('No complete authorized pack for this request.',),artifact_hash=summary.pack.artifact_hash)
    flows=[x for x in p.get('workflows',()) if process_id is None or x['process_id']==process_id]
    if intent=='overview':records=tuple(p['processes'])
    elif intent=='interfaces':records=tuple(x for x in p['interfaces'] if process_id in (x['from_process'],x['to_process']))
    elif intent=='findings':records=findings
    else:records=tuple(x for w in flows for x in w.get({'process_steps':'steps','roles':'roles','artifacts':'artifacts'}[intent],()))
    citations=tuple(EvidenceRef.model_validate_json(json.dumps(x)) for x in p['citations'])
    return Answer(state='answered' if records and citations else 'abstained',intent=intent,records=records,findings=findings,citations=citations,caveats=caveats,artifact_hash=summary.pack.artifact_hash)
