import json,base64
from uuid import UUID,uuid4
import pytest,psycopg
from test_operating_model_actions import prepared,execute_event
from oracle_brain.operating_model.report_store import persist_report,serve_report
from oracle_brain.operating_model.consultant.process_analysis import Report
from oracle_brain.operating_model.retrieval import QueryPlan

def test_real_measured_report_persists_both_lineages_and_revocation_denies(admin_url,tmp_path):
    ledger,model,run,receipt=prepared(admin_url,tmp_path);result=execute_event(admin_url,run,model.workspace_id,ledger,True)
    with psycopg.connect(admin_url) as c:model_id=c.execute('SELECT artifact_id FROM oracle2.artifact_manifests WHERE workspace_id=%s AND kind=%s ORDER BY created_at DESC',(model.workspace_id,'operating_model')).fetchone()[0]
    calls=[]
    def generate(role,inputs):
        calls.append(role)
        if role=='planner':return {'operations':['describe_metrics']}
        if role=='analyst':return {'notes':'invented events only'}
        if role=='challenger':return {'supported':True}
        return Report(variant='measured',state='ready',model_artifact_hash=inputs['pack']['artifact_hash'],event_artifact_hash=inputs['event_artifact_hash'],measurements=inputs['metrics'],clauses=(),finding_ids=tuple(f['finding_id'] for f in inputs['pack']['findings']),actual_data_acceptance='synthetic',limitations=('Invented event fixture; no actual-data acceptance.',)).model_dump(mode='json')
    report_id=uuid4();out=persist_report(ledger,workspace_id=model.workspace_id,model_id=model_id,model_version=1,report_id=report_id,report_version=1,
        plan=QueryPlan(view='process_local',process_ids=('p1',),question='invented measurements',max_bytes=131072,page=0,page_size=25),generate=generate,synthetic=True,permission_digest='a'*64,compiler_digest='b'*64,event_id=UUID(result['import_id']),event_version=1)
    assert out['state']=='ready' and calls==['planner','analyst','challenger','writer']
    report=serve_report(ledger,model.workspace_id,report_id,1)
    assert report.actual_data_acceptance=='synthetic' and report.measurements['cases']['total']==1
    ledger.can_read=lambda *_:False
    with pytest.raises(PermissionError):serve_report(ledger,model.workspace_id,report_id,1)

def test_private_report_denied_before_read_or_callback():
    calls=[]
    with pytest.raises(PermissionError):persist_report(None,workspace_id=uuid4(),model_id=uuid4(),model_version=1,report_id=uuid4(),report_version=1,plan=None,generate=lambda *_:calls.append(1),synthetic=False,permission_digest='a'*64,compiler_digest='b'*64)
    assert not calls
