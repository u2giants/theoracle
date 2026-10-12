from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.retrieval import QueryPlan, build_pack, Retrieval

def payload(n=1):
    refs=[]; obs=[]; processes=[]
    for i in range(n):
        sid=str(uuid4()); refs.append({'workspace_id':str(uuid4()),'source_id':sid,'revision':1,'original_sha256':('a' if i==0 else 'b')*64,'reading_sha256':'c'*64,'parser_id':'p'})
        oid=f'o{i}'; obs.append({'observation_id':oid,'ref':refs[-1],'evidence':[{'ref':refs[-1],'start':0,'end':1,'quote':'x'}],'value':'x','scope':'s','kind':'process','occurrence_key':str(i)})
        processes.append({'process_id':f'p{i}','scope':'s','completeness':'complete','observation_ids':[oid]})
    return {'source_refs':refs,'observations':obs,'findings':[],'workflows':[],'operating_models':[{'declared_population':'all','processes':processes,'interfaces':[]}]}
def plan(view='process_local', ids=('p0',), size=4096, page=0): return QueryPlan(view=view,process_ids=ids,question='q',max_bytes=size,page=page,page_size=1)

def test_mandatory_findings_survive_pack_budget():
    p=payload(); p['findings']=[{'finding_id':'f','kind':'missing_information','workspace_id':p['source_refs'][0]['workspace_id'],'source_refs':[p['source_refs'][0]],'scope':'s','text':'missing','origin':'source_reported','evidence_refs':[p['observations'][0]['evidence'][0]]}]
    assert build_pack(p,plan())['findings'][0]['finding_id']=='f'

def test_oversize_returns_incomplete_without_truncation():
    result=build_pack(payload(),plan(size=1024)); assert result['state']=='coverage_incomplete' and 'observations' not in result

def test_unknown_process_rejected():
    with pytest.raises(LookupError): build_pack(payload(),plan(ids=('missing',)))

def test_overview_pagination_continuation_bounded():
    result=build_pack(payload(2),plan(view='company_overview',ids=(),page=0)); assert result['continuation']['page']==1

def test_permission_revoked_between_pack_and_serve_denies_result():
    class Ledger:
        def __init__(self): self.allowed=True
        def read(self,*_):
            if not self.allowed: raise PermissionError('source access revoked')
            return payload()
    ledger=Ledger(); pack_result=build_pack(payload(),plan()); ledger.allowed=False
    with pytest.raises(PermissionError): Retrieval(ledger, None).recheck_before_serve(uuid4(),uuid4(),1,pack_result)

def test_cross_source_aggregate_requires_access_to_every_dependency():
    p=payload(2); plan_result=plan(ids=('p0','p1'))
    with pytest.raises(LookupError):
        build_pack({**p, 'operating_models':[{'declared_population':'all','processes':p['operating_models'][0]['processes'][:1],'interfaces':[]}]}, plan_result)
