"""Bounded current-source packs with required caveats, never original-text answer fallback."""
import json
from uuid import UUID
from typing import Literal
from pydantic import Field
from .source_receipts import _StrictModel
from .contracts import canonical_bytes,digest
from .findings import Finding,answer_eligible

class QueryPlan(_StrictModel):
    schema_version:Literal[1]=1
    view:Literal['process_local','connected_interfaces','company_overview']
    process_ids:tuple[str,...]=()
    question:str=Field(max_length=4000)
    max_bytes:int=Field(strict=True,ge=1024,le=128*1024)
    page:int=Field(strict=True,ge=0)
    page_size:int=Field(strict=True,ge=1,le=25)


def build_pack(payload:dict,plan:QueryPlan,*, reviewer_scopes:frozenset[str]=frozenset()) -> dict:
    models=payload.get('operating_models',[])
    processes=[p for model in models for p in model['processes']]
    available={p['process_id'] for p in processes}
    if any(p not in available for p in plan.process_ids):raise LookupError('unknown process; no fuzzy identity fallback')
    selected=set(plan.process_ids)
    if plan.view=='connected_interfaces':
        seeds=frozenset(selected)
        for model in models:
            for interface in model['interfaces']:
                if interface['from_process'] in seeds or interface['to_process'] in seeds:
                    selected.update((interface['from_process'],interface['to_process']))
    if plan.view=='company_overview':
        ordered=sorted(available)
        selected=set(ordered[plan.page*plan.page_size:(plan.page+1)*plan.page_size])
    elif not selected:raise ValueError('process-scoped pack requires explicit process IDs')
    selected_processes=[p for p in processes if p['process_id'] in selected]
    workflows=[w for w in payload.get('workflows',[]) if w['process_id'] in selected]
    scopes={p['scope'] for p in selected_processes}
    observation_ids={oid for p in selected_processes for oid in p['observation_ids']}
    interfaces=[]
    for model in models:
        for interface in model['interfaces']:
            if interface['from_process'] in selected or interface['to_process'] in selected:
                interfaces.append(interface);observation_ids.update(interface['support']['observation_ids'])
    observations=[o for o in payload.get('observations',[]) if o['observation_id'] in observation_ids]
    findings=[];quarantine=[]
    for raw in payload.get('findings',[]):
        f=Finding.model_validate_json(json.dumps(raw))
        if f.process_id in selected or f.scope in scopes:
            if answer_eligible(f):findings.append(raw)
            elif f.origin=='legacy_unverified' and f.scope in reviewer_scopes:quarantine.append(raw)
    citations={}
    for observation in observations:
        for e in observation['evidence']:citations[digest(e)]=e
    for f in findings:
        for e in f['evidence_refs']:citations[digest(e)]=e
    selected_sources={e['ref']['source_id'] for e in citations.values()}
    originals={r['original_sha256'] for r in payload['source_refs'] if r['source_id'] in selected_sources}
    continuation=None
    if plan.view=='company_overview' and (plan.page+1)*plan.page_size<len(available):
        continuation={'page':plan.page+1,'page_size':plan.page_size,'artifact_hash':digest(payload),'view':plan.view}
    pack={'schema_version':1,'state':'ready','artifact_hash':digest(payload),'view':plan.view,
          'declared_population':[m['declared_population'] for m in models],
          'processes':selected_processes,'workflows':workflows,'interfaces':interfaces,
          'observations':observations,'findings':findings,'reviewer_quarantine':quarantine,
          'citations':list(citations.values()),'distinct_original_count':len(originals),
          'continuation':continuation,'declared_population_fully_paged':plan.view=='company_overview' and continuation is None and plan.page==0,
          'coverage_state':'partial' if any(p['completeness']!='complete' for p in selected_processes) else 'represented'}
    if len(canonical_bytes(pack))>plan.max_bytes:
        return {'schema_version':1,'state':'coverage_incomplete','artifact_hash':digest(payload),
                'reason':'Required process controls and caveats exceed this evidence budget.',
                'process_ids':sorted(selected),'required_bytes':len(canonical_bytes(pack)),
                'max_bytes':plan.max_bytes,'continuation':continuation}
    return pack

class Retrieval:
    def __init__(self,ledger,projection):self.ledger,self.projection=ledger,projection
    async def retrieve(self,*,workspace_id:UUID,artifact_id:UUID,version:int,plan:QueryPlan,reviewer_scopes:frozenset[str]=frozenset()):
        payload=await self.projection.load(self.ledger,workspace_id,artifact_id,version)
        # Actual stock SDK paths contribute candidates; ledger coverage adds mandatory material.
        candidates=await self.projection.rag.retrieve(plan.question)
        pack=build_pack(payload,plan,reviewer_scopes=reviewer_scopes)
        if self.ledger.read(workspace_id,artifact_id,version)!=payload:raise PermissionError('source access changed before serving pack')
        pack['sdk_candidate_count']=len(candidates.items)
        return pack
    def recheck_before_serve(self,workspace_id:UUID,artifact_id:UUID,version:int,pack:dict):
        if digest(self.ledger.read(workspace_id,artifact_id,version))!=pack['artifact_hash']:
            raise PermissionError('pack is no longer current and authorized')
        return pack
