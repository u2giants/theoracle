"""Fixed public fixture does not accept arbitrary text, role or executable SQL."""
import base64
from datetime import datetime,timedelta,timezone
from oracle_brain.hosting.synthetic_seed import compile_seed
from oracle_brain.hosting.synthetic_fixture import fixture,graph_acl_users,WORKSPACE,SOURCES
from oracle_brain.operating_model.contracts import canonical_bytes,digest
import pytest

def parameters():
    enc=lambda b:base64.b64encode(b).decode()
    verifier='SCRAM-SHA-256$4096:'+enc(b'public-invented-salt')+'$'+enc(b'k'*32)+':'+enc(b's'*32)
    return {'runtime_hash':'a'*64,'source_role_registry_hash':'b'*64,'review_hash':'c'*64,
            'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'gateway_scram':verifier,'projector_scram':verifier,'executor_scram':verifier}


def test_fixed_sources_manifest_and_public_seed():
    sql,manifest,payload,release=compile_seed(parameters())
    assert len(payload['source_refs'])==len(SOURCES)==2
    assert manifest.content_hash==digest(payload)==release.artifact_content_hash
    assert 'GRANT SELECT,INSERT,UPDATE,DELETE' not in sql
    assert 'oracle2_documentary_executor' in sql and 'oracle2_gateway_metadata' in sql
    assert 'oracle2_candidate_compiler TO oracle_synthetic_executor' not in sql
    assert 'CREATE TABLE oracle2.synthetic_hosting_marker' in sql
    assert 'source-role' not in release.model_dump_json() # distinct registry remains bootstrap-owned

@pytest.mark.parametrize('field,value',[('runtime_hash','bad'),('gateway_scram',"'; SELECT 1; --"),('role_name','admin'),('expires_at','2000-01-01T00:00:00+00:00')])
def test_only_fixed_reviewed_parameters(field,value):
    data=parameters();data[field]=value
    with pytest.raises(PermissionError):compile_seed(data)

@pytest.mark.parametrize('graph,password', [('foreign','d'*64), ('oracle_*','d'*64), (None,'d'*64), ('fixed','bad')])
def test_graph_acl_refuses_nonliteral_artifact_or_credential(graph,password):
    if graph is None:graph=fixture('a'*64,'c'*64)[-1].graph_name+'*'
    with pytest.raises(PermissionError):graph_acl_users(graph,password,'e'*64)

def test_native_ontology_namespace_drift_requires_requalification(monkeypatch):
    from graphrag_sdk.storage.ontology_store import OntologyStore
    graph=fixture('a'*64,'c'*64)[-1].graph_name
    monkeypatch.setattr(OntologyStore,'ONTOLOGY_GRAPH_SUFFIX','_different')
    with pytest.raises(PermissionError):graph_acl_users(graph,'d'*64,'e'*64)
