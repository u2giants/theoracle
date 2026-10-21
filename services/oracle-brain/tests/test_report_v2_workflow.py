"""Server-derived complete upstream seals and bounded invented four-role report flow."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest

from test_report_v2_codec import advice,report_payload
from oracle_brain.operating_model.contracts import ArtifactManifest,digest
from oracle_brain.operating_model.consultant.process_analysis import parse_report
from oracle_brain.operating_model.consultant.challenge import validate_report
from oracle_brain.operating_model.consultant.recommendations import (
    EvidenceRevision,evidence_revision_from_payload,recommendation_to_payload,
)
from oracle_brain.operating_model.report_store import derive_report_evidence,persist_report
from oracle_brain.operating_model.retrieval import QueryPlan
from oracle_brain.operating_model.workflows.process_consult import consult


def upstream():
    workspace,model_id=uuid4(),uuid4()
    source={'workspace_id':str(workspace),'source_id':str(uuid4()),'revision':1,
            'original_sha256':'1'*64,'reading_sha256':'2'*64,'parser_id':'invented','schema_version':1}
    payload={'source_refs':[source]}
    manifest=ArtifactManifest(workspace_id=workspace,artifact_id=model_id,version=1,kind='operating_model',
        input_digest='a'*64,source_digest=digest({'refs':[source]}),permission_digest='c'*64,
        compiler_digest='d'*64,dependency_digest='e'*64,content_hash=digest(payload),
        private_object_key='invented-unopened',state='ready')
    pack={'state':'ready','artifact_hash':manifest.content_hash,
          'citations':[{'ref':source,'start':0,'end':4,'quote':'word'}],
          'findings':[{'finding_id':'conflict','status':'unresolved'}]}
    plan=QueryPlan(view='process_local',process_ids=('p',),question='invented',max_bytes=131072,page=0,page_size=25)
    return dict(workspace_id=workspace,model_id=model_id,model_version=1,
                model_manifest=manifest,model_payload=payload,plan=plan,pack=pack)


def writer(inputs):
    expected=evidence_revision_from_payload(inputs['expected_evidence_revision'])
    result=report_payload(advice(expected));result['model_artifact_hash']=inputs['pack']['artifact_hash']
    result['finding_ids']=[item['finding_id'] for item in inputs['pack']['findings']]
    if inputs['event_artifact_hash'] is not None:
        result.update(variant='measured',event_artifact_hash=inputs['event_artifact_hash'],measurements=inputs['metrics'])
    return result


def generate(role,inputs):
    if role=='planner':return {'operations':['documentary_map']}
    if role=='challenger':return {'supported':True}
    if role=='analyst':return {'notes':'invented only'}
    return writer(inputs)


def test_expected_evidence_uses_root_namespace_full_upstream_seal_and_no_report_hash():
    args=upstream();expected=derive_report_evidence(**args)
    assert expected.evidence_refs==tuple('citation:'+digest(c) for c in args['pack']['citations'])
    assert expected.revision_id==expected.evidence_seal and len(expected.revision_id)==64
    assert expected==derive_report_evidence(**args)
    for changed in ({'plan':args['plan'].model_copy(update={'question':'different bounded scope'})},
                    {'model_manifest':args['model_manifest'].model_copy(update={'permission_digest':'f'*64})},
                    {'pack':{**args['pack'],'coverage_state':'partial'}}):
        assert derive_report_evidence(**{**args,**changed})!=expected


def test_ordered_citation_and_full_source_commitments_change_the_seal():
    args=upstream();second={**args['pack']['citations'][0],'start':5,'end':9,'quote':'next'}
    first={**args,'pack':{**args['pack'],'citations':args['pack']['citations']+[second]}}
    reversed_args={**first,'pack':{**first['pack'],'citations':list(reversed(first['pack']['citations']))}}
    assert derive_report_evidence(**first)!=derive_report_evidence(**reversed_args)
    wrong={**args,'workspace_id':uuid4()}
    with pytest.raises(ValueError,match='manifest identity'):derive_report_evidence(**wrong)


def test_measured_binding_includes_exact_event_identity_payload_permission_and_metrics():
    args=upstream();event_id=uuid4();event_payload={'source_refs':args['model_payload']['source_refs'],'data':'invented'}
    event_manifest=args['model_manifest'].model_copy(update={'artifact_id':event_id,'kind':'event_import',
        'content_hash':digest(event_payload)})
    measured={**args,'event_id':event_id,'event_version':1,'event_manifest':event_manifest,
              'event_payload':event_payload,'metrics':{'retained':1}}
    expected=derive_report_evidence(**measured)
    assert expected.evidence_refs[-1]=='event:'+digest(event_payload)
    assert derive_report_evidence(**{**measured,'metrics':{'retained':2}})!=expected
    assert derive_report_evidence(**{**measured,'event_manifest':event_manifest.model_copy(update={'permission_digest':'f'*64})})!=expected
    with pytest.raises(ValueError):derive_report_evidence(**{**measured,'event_version':2})


def test_v2_four_roles_consume_explicit_expected_evidence_and_keep_unknowns_and_conflicts():
    args=upstream();expected=derive_report_evidence(**args);calls=[]
    def record(role,inputs):calls.append(role);return generate(role,inputs)
    result=consult(args['pack'],generate=record,synthetic=True,report_schema_version=2,expected_evidence=expected)
    assert result['state']=='ready' and result['calls']==4
    assert calls==['planner','analyst','challenger','writer']
    parsed=parse_report(result['report']);validate_report(parsed,args['pack'],expected_evidence=expected)
    assert parsed.finding_ids==('conflict',)
    assert parsed.recommendations[0]['options'][0]['downstream_costs']==[dict(kind='missing',measure=None)]


@pytest.mark.parametrize('mutation',['evidence','namespace','conflict','schema','savings','causal'])
def test_writer_cannot_change_server_identity_drop_findings_or_claim_unsupported_benefit(mutation):
    args=upstream();expected=derive_report_evidence(**args)
    def changed(role,inputs):
        if role!='writer':return generate(role,inputs)
        result=writer(inputs)
        if mutation=='evidence':result['recommendations'][0]['evidence']['evidence_seal']='f'*64
        elif mutation=='namespace':result['recommendations'][0]['evidence']['evidence_refs']=['source:invented']
        elif mutation=='conflict':result['finding_ids']=[]
        elif mutation=='schema':result['schema_version']=1;result.pop('recommendations')
        elif mutation=='savings':result['recommendations'][0]['scope_note']='Guaranteed savings'
        else:result['recommendations'][0]['options'][1]['title']='This causes faster production'
        return result
    result=consult(args['pack'],generate=changed,synthetic=True,report_schema_version=2,expected_evidence=expected)
    assert result['state']=='limited' and result['calls']==4


def test_company_pause_and_absent_expected_evidence_refuse_before_any_callback():
    args=upstream();calls=[]
    with pytest.raises(PermissionError):consult(args['pack'],generate=lambda *_:calls.append(1),synthetic=False,
                                               report_schema_version=2,expected_evidence=None)
    with pytest.raises(PermissionError):consult(args['pack'],generate=lambda *_:calls.append(1),synthetic=True,
                                               report_schema_version=2,expected_evidence=None)
    with pytest.raises(PermissionError):persist_report(None,workspace_id=uuid4(),model_id=uuid4(),model_version=1,
        report_id=uuid4(),report_version=1,plan=None,generate=lambda *_:calls.append(1),synthetic=False,
        permission_digest='a'*64,compiler_digest='b'*64,report_schema_version=2)
    assert calls==[]
