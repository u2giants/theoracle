"""Independent source-obligation accounting; graph counts cannot substitute for it."""
from typing import Literal
from pydantic import Field
from .source_receipts import _StrictModel,EvidenceRef
from .contracts import digest

class Obligation(_StrictModel):
    obligation_id:str
    priority:Literal['essential','detail']
    expected:Literal['represented','unresolved','unsupported','not_applicable','quarantined']
    evidence:EvidenceRef
    reason:str=Field(min_length=1)

class CoverageRecord(_StrictModel):
    obligation_id:str
    disposition:Literal['represented','unresolved','unsupported','not_applicable','quarantined']
    object_ids:tuple[str,...]
    reason:str=Field(min_length=1)

def validate_coverage(obligations:tuple[Obligation,...],records:tuple[CoverageRecord,...],*, object_evidence:dict[str,tuple[EvidenceRef,...]],independent_inventory_hash:str) -> dict:
    if digest({'obligations':[o.model_dump(mode='json') for o in obligations]})!=independent_inventory_hash:raise ValueError('independent inventory changed')
    wanted={o.obligation_id:o for o in obligations};actual={r.obligation_id:r for r in records}
    if len(wanted)!=len(obligations) or len(actual)!=len(records) or wanted.keys()!=actual.keys():raise ValueError('unclassified, missing or duplicate obligation')
    represented=unresolved=0
    for oid,o in wanted.items():
        r=actual[oid]
        if o.priority=='essential' and o.expected!=r.disposition:raise ValueError('explicit essential obligation omitted or falsely reclassified')
        if r.disposition in {'represented','unresolved','quarantined'}:
            if not r.object_ids or any(i not in object_evidence for i in r.object_ids):raise ValueError('obligation maps to absent model/projection object')
            if not any(e.ref==o.evidence.ref and e.start<=o.evidence.start and e.end>=o.evidence.end and e.quote[o.evidence.start-e.start:o.evidence.end-e.start]==o.evidence.quote for i in r.object_ids for e in object_evidence[i]):raise ValueError('mapped object lacks exact obligation support')
        if o.priority=='essential':
            represented+=r.disposition=='represented';unresolved+=r.disposition=='unresolved'
    return {'inventory_hash':independent_inventory_hash,'essential_total':sum(o.priority=='essential' for o in obligations),'essential_represented':represented,'essential_unresolved':unresolved,'complete_accounting':True}
