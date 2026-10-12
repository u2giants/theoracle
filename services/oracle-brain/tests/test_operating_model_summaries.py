from uuid import uuid4
import pytest
from test_operating_model_pipeline import inputs,call
from oracle_brain.operating_model.retrieval import QueryPlan
from oracle_brain.operating_model.summaries import summarize_from_ledger,persist_summary,serve_summary

def prepared(admin_url,tmp_path):
    l,m,ex,ob,rec=inputs(admin_url,tmp_path);aid=uuid4();call(l,m,ex,ob,rec,aid)
    plan=QueryPlan(view='company_overview',process_ids=(),question='reported interfaces',max_bytes=131072,page=0,page_size=25)
    summary=summarize_from_ledger(l,m.workspace_id,aid,1,plan)
    return l,m,summary

def test_summary_real_ledger_persists_distinct_id_and_lineage(admin_url,tmp_path):
    l,m,s=prepared(admin_url,tmp_path);sid=uuid4()
    manifest=persist_summary(l,s,summary_id=sid,summary_version=1,permission_digest='a'*64,compiler_digest='b'*64)
    restored=serve_summary(l,m.workspace_id,sid,1)
    assert manifest.kind=='summary' and restored==s
    assert len(restored.pack.contents['processes'])==2 and restored.pack.contents['objects']

def test_summary_revocation_denies_serving(admin_url,tmp_path):
    l,m,s=prepared(admin_url,tmp_path);sid=uuid4()
    persist_summary(l,s,summary_id=sid,summary_version=1,permission_digest='a'*64,compiler_digest='b'*64)
    l.can_read=lambda *_:False
    with pytest.raises(PermissionError):serve_summary(l,m.workspace_id,sid,1)

def test_summary_tampered_pack_cannot_be_persisted(admin_url,tmp_path):
    l,m,s=prepared(admin_url,tmp_path)
    s.pack.contents['processes']=[]
    with pytest.raises(ValueError):persist_summary(l,s,summary_id=uuid4(),summary_version=1,permission_digest='a'*64,compiler_digest='b'*64)
