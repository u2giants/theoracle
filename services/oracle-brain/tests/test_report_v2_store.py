"""Actual canonical Ledger/Postgres report-v2 fixture; invented local inputs only."""
from uuid import UUID,uuid4

import psycopg
import pytest

from test_operating_model_actions import prepared,execute_event
from test_report_v2_workflow import generate,writer
from oracle_brain.operating_model.consultant.process_analysis import ReportV2
from oracle_brain.operating_model.consultant.recommendations import recommendation_from_payload
from oracle_brain.operating_model.report_store import persist_report,serve_report
from oracle_brain.operating_model.retrieval import QueryPlan


def arguments(admin_url,tmp_path,*,measured=False):
    ledger,model,run,receipt=prepared(admin_url,tmp_path)
    with psycopg.connect(admin_url) as connection:
        model_id=connection.execute('SELECT artifact_id FROM oracle2.artifact_manifests WHERE workspace_id=%s AND kind=%s ORDER BY created_at DESC',
                                    (model.workspace_id,'operating_model')).fetchone()[0]
    params=dict(workspace_id=model.workspace_id,model_id=model_id,model_version=1,
        report_id=uuid4(),report_version=1,
        plan=QueryPlan(view='process_local',process_ids=('p1',),question='invented recommendations',max_bytes=131072,page=0,page_size=25),
        generate=generate,synthetic=True,permission_digest='a'*64,compiler_digest='b'*64,report_schema_version=2)
    if measured:
        event=execute_event(admin_url,run,model.workspace_id,ledger,True)
        params.update(event_id=UUID(event['import_id']),event_version=1)
    return ledger,params


def test_real_ledger_v2_documentary_roundtrip_uses_existing_report_kind_and_exact_evidence(admin_url,tmp_path):
    ledger,args=arguments(admin_url,tmp_path)
    result=persist_report(ledger,**args)
    assert result['state']=='ready' and result['calls']==4
    report=serve_report(ledger,args['workspace_id'],args['report_id'],1)
    assert type(report) is ReportV2 and report.schema_version==2
    manifest,payload=ledger.read_with_manifest(args['workspace_id'],args['report_id'],1)
    assert manifest.kind=='report' and payload['synthetic'] is True
    recommendation=recommendation_from_payload(report.recommendations[0])
    assert recommendation.evidence.revision_id==recommendation.evidence.evidence_seal
    assert all(ref.startswith('citation:') for ref in recommendation.evidence.evidence_refs)
    assert recommendation.scope_note and report.actual_data_acceptance=='synthetic'


def test_real_ledger_measured_v2_seals_exact_event_and_retains_source_lineage(admin_url,tmp_path):
    ledger,args=arguments(admin_url,tmp_path,measured=True)
    result=persist_report(ledger,**args)
    assert result['state']=='ready'
    report=serve_report(ledger,args['workspace_id'],args['report_id'],1)
    recommendation=recommendation_from_payload(report.recommendations[0])
    assert recommendation.evidence.evidence_refs[-1]=='event:'+report.event_artifact_hash
    assert report.variant=='measured' and report.measurements['cases']['total']==1
    with psycopg.connect(admin_url) as connection:
        dependencies=connection.execute("SELECT upstream_id,upstream_revision FROM oracle2.artifact_dependencies WHERE workspace_id=%s AND artifact_id=%s AND version=1 AND upstream_kind='artifact'",
            (args['workspace_id'],args['report_id'])).fetchall()
    assert (str(args['model_id']),'1') in dependencies and (str(args['event_id']),'1') in dependencies


def test_current_source_revocation_denies_v2_before_opening_a_private_blob(admin_url,tmp_path,monkeypatch):
    ledger,args=arguments(admin_url,tmp_path);persist_report(ledger,**args)
    ledger.can_read=lambda *_:False
    reads=[]
    monkeypatch.setattr(ledger.blobs,'read',lambda *_:reads.append(1) or pytest.fail('revoked blob must stay closed'))
    with pytest.raises(PermissionError):serve_report(ledger,args['workspace_id'],args['report_id'],1)
    assert reads==[]


def test_changed_writer_binding_cannot_persist_report_v2(admin_url,tmp_path):
    ledger,args=arguments(admin_url,tmp_path)
    def changed(role,inputs):
        result=generate(role,inputs)
        if role=='writer':result['recommendations'][0]['evidence']['evidence_seal']='f'*64
        return result
    result=persist_report(ledger,**{**args,'generate':changed})
    assert result['state']=='limited'
    with psycopg.connect(admin_url) as connection:
        assert connection.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',
            (args['workspace_id'],args['report_id'])).fetchone()[0]==0


def test_access_revoked_after_generation_refuses_before_report_write(admin_url,tmp_path):
    ledger,args=arguments(admin_url,tmp_path)
    def revoked(role,inputs):
        result=generate(role,inputs)
        if role=='writer':ledger.can_read=lambda *_:False
        return result
    with pytest.raises(PermissionError):persist_report(ledger,**{**args,'generate':revoked})
    with psycopg.connect(admin_url) as connection:
        assert connection.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',
            (args['workspace_id'],args['report_id'])).fetchone()[0]==0


def test_return_boundary_rechecks_after_real_report_persistence(admin_url,tmp_path,monkeypatch):
    ledger,args=arguments(admin_url,tmp_path)
    original=ledger.read
    def revoked(workspace,artifact,version,**kwargs):
        if artifact==args['report_id']:ledger.can_read=lambda *_:False
        return original(workspace,artifact,version,**kwargs)
    monkeypatch.setattr(ledger,'read',revoked)
    with pytest.raises(PermissionError):persist_report(ledger,**args)
