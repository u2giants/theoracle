from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.consultant.challenge import validate_report
from oracle_brain.operating_model.consultant.process_analysis import Report, SupportedClause
from oracle_brain.operating_model.workflows.process_consult import consult

def pack():
    e={'ref':{'source_id':str(uuid4()),'revision':1},'start':0,'end':4,'quote':'word'}
    return {'state':'ready','artifact_hash':'a'*64,'citations':[e],'findings':[{'finding_id':'f','status':'unresolved'}]}
def report(p, **kw):
    data=dict(variant='documentary',state='ready',model_artifact_hash=p['artifact_hash'],clauses=(SupportedClause(text='documented',citation_ids=(digest(p['citations'][0]),)),),finding_ids=('f',),actual_data_acceptance='unavailable'); data.update(kw); return Report(**data)

def test_challenger_rejects_invented_savings():
    p=pack(); bad=report(p, clauses=(SupportedClause(text='ROI savings',citation_ids=(digest(p['citations'][0]),)),))
    with pytest.raises(ValueError,match='savings'): validate_report(bad,p)

def test_unresolved_conflict_must_be_in_report():
    p=pack(); p['findings']=[{'finding_id':'conflict','status':'unresolved'}]
    with pytest.raises(ValueError,match='disagreement'): validate_report(report(p),p)

def test_writer_metric_change_is_limited():
    p=pack(); result=consult(p,generate=lambda role, _: ({'supported':True} if role=='challenger' else {'operations':['documentary_map']} if role=='planner' else Report(variant='measured',state='ready',model_artifact_hash=p['artifact_hash'],event_artifact_hash='b'*64,measurements={'median':2},clauses=(),finding_ids=('f',),actual_data_acceptance='synthetic').model_dump(mode='json')),synthetic=True,metrics={'median':1},event_artifact_hash='b'*64)
    assert result['state']=='limited'

def test_policy_acceptance_is_rejected():
    p=pack()
    with pytest.raises(Exception): Report(variant='documentary',state='ready',model_artifact_hash=p['artifact_hash'],clauses=(),finding_ids=(),established_policy=True,actual_data_acceptance='unavailable')

def test_company_report_denied_before_callbacks():
    calls=[]
    with pytest.raises(PermissionError): consult(pack(),generate=lambda *_: calls.append(1),synthetic=False)
    assert calls==[]

def test_failed_challenge_is_limited_with_four_calls():
    p=pack()
    def generate(role, _):
        if role=='planner': return {'operations':['documentary_map']}
        if role=='challenger': return {'supported':False}
        return report(p).model_dump(mode='json')
    result=consult(p,generate=generate,synthetic=True)
    assert result['state']=='limited' and result['calls']==4

def test_successful_measured_report_preserves_metrics_and_event_provenance():
    p=pack(); metrics={'median':2}; event='c'*64
    def generate(role, _):
        if role=='planner': return {'operations':['describe_metrics']}
        if role=='challenger': return {'supported':True}
        if role=='analyst': return {'notes':'measured'}
        return Report(variant='measured',state='ready',model_artifact_hash=p['artifact_hash'],event_artifact_hash=event,measurements=metrics,clauses=(),finding_ids=('f',),actual_data_acceptance='synthetic').model_dump(mode='json')
    result=consult(p,generate=generate,synthetic=True,metrics=metrics,event_artifact_hash=event)
    assert result['state']=='ready' and result['calls']==4 and result['report']['measurements']==metrics and result['report']['event_artifact_hash']==event
