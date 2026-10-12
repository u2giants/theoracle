import pytest
from test_operating_model_summaries import prepared
from oracle_brain.operating_model.answer import answer_from_summary

def test_documentary_overview_retains_current_processes_and_partial_caveat(admin_url,tmp_path):
    l,m,s=prepared(admin_url,tmp_path)
    a=answer_from_summary(l,s,intent='overview')
    assert a.state=='answered' and a.records and a.citations
    assert {r['process_id'] for r in a.records}=={'p1','p2'}
    assert 'Reported operating coverage remains partial.' in a.caveats

def test_outside_process_abstains_without_claims(admin_url,tmp_path):
    l,m,s=prepared(admin_url,tmp_path)
    a=answer_from_summary(l,s,intent='interfaces',process_id='unknown')
    assert a.state=='abstained' and not a.records and not a.citations

def test_answer_rechecks_current_authority(admin_url,tmp_path):
    l,m,s=prepared(admin_url,tmp_path);l.can_read=lambda *_:False
    with pytest.raises(PermissionError):answer_from_summary(l,s,intent='overview')

def test_arbitrary_question_intent_not_admitted(admin_url,tmp_path):
    l,m,s=prepared(admin_url,tmp_path)
    with pytest.raises(ValueError):answer_from_summary(l,s,intent='recommend company changes')
