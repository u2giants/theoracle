"""Injected wire/context fixtures prove bindings, never appoint a live consumer."""
import copy,hashlib,json
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from test_assembly_qualification import qualified
from test_assembly_context import context
from test_native_factory import job
from purpose_journey_fixture_models import embedding_response
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.sdk_projection import ProcessingSDKProjection
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.operating_model.purpose_context import source_population_digest
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.operating_model.purpose_profiles_v2 import DerivedEmbeddingContextV2,DerivedSDKEmbeddingContextV3,PurposePrivateContextV2
from oracle_brain.operating_model.paid_sdk_embeddings_v3 import (processing_embedding_inventory_v3,
    PaidSDKEmbeddingPinsV3,verify_paid_sdk_embedding_v3,PaidProjectionEmbedderV3)

@pytest.fixture
def paid_case(qualified):
    payload=qualified['payload'];view=ProcessingSDKProjection.projection_view(payload)
    inv=processing_embedding_inventory_v3(payload)
    ctx=DerivedSDKEmbeddingContextV3(actor_id=uuid4(),workspace_id=qualified['manifest'].workspace_id,
        runtime_hash='a'*64,permission_hash='b'*64,qualified_artifact_id=qualified['manifest'].artifact_id,
        qualified_artifact_version=1,qualified_content_hash=digest(payload),projection_digest=digest(view),
        source_refs=tuple(SourceRef.model_validate_json(canonical_bytes(r)) for r in view['source_refs']),
        projection=view,qualified_payload=payload,inventory=inv)
    j=job();j=j.model_copy(update={'workspace_id':ctx.workspace_id,'artifact_id':ctx.qualified_artifact_id,
        'permission_hash':ctx.permission_hash,'request':ctx.request(),'request_hash':digest(ctx.request()),
        'pricing':j.pricing.model_copy(update={'model':'openai/text-embedding-3-small'})})
    private=PurposePrivateContextV2(phase='embedding',job=j,embedding=ctx)
    raw=canonical_bytes(embedding_response(len(inv.inputs)));sha=hashlib.sha256(raw).hexdigest();reservation=str(uuid4())
    record={'dispatch_id':str(j.dispatch_id),'reservation_id':reservation,'failed':False,'raw_response':raw.decode(),
        'request_hash':j.request_hash,'permission_hash':j.permission_hash,'job_hash':digest(j.model_dump(mode='json')),
        'register_hash':j.register_hash,'pricing_hash':digest(j.pricing.model_dump(mode='json')),
        'key_fingerprint':'1'*64,'ledger_identity_hash':'2'*64,'raw_response_hash':sha}
    record['wire_custody']={**{k:record[k] for k in ('dispatch_id','reservation_id','request_hash','permission_hash','job_hash','key_fingerprint','ledger_identity_hash')},
        'raw_sha256':sha,'captured_bytes':len(raw),'complete':True,'truncated':False}
    at=datetime.now(timezone.utc)
    commit=PhaseResponseCommitV2(phase='embedding',operation='embedding',processing_purpose='source-extraction',
        dispatch_id=j.dispatch_id,workspace_id=ctx.workspace_id,actor_id=ctx.actor_id,provider_login='embedding_fixture',
        actual_caller_login='embedding_fixture',runtime_hash=ctx.runtime_hash,descriptor_hash='3'*64,
        operation_approval_hash='4'*64,population_digest=source_population_digest(ctx.source_refs),source_refs=ctx.source_refs,
        context_hash=digest(private.model_dump(mode='json')),parent_registry_hash='5'*64,current_proof_hash='6'*64,
        parent_witness_hash='7'*64,account_policy_hash=digest({k:v for k,v in j.processing_request.model_dump(mode='json').items() if k!='terms_hash'}),
        model=ctx.request()['model'],valid_until=at+timedelta(minutes=1),job_hash=record['job_hash'],request_hash=j.request_hash,
        permission_hash=j.permission_hash,budget_identity_hash='8'*64,raw_response_hash=sha,native_custody_receipt_hash=digest(record),committed_at=at)
    pins=PaidSDKEmbeddingPinsV3(context_hash=commit.context_hash,commit_hash=digest(commit.model_dump(mode='json')),
        native_receipt_hash=digest(record),descriptor_hash=commit.descriptor_hash,operation_approval_hash=commit.operation_approval_hash,
        parent_registry_hash=commit.parent_registry_hash,allocation_hash=commit.budget_identity_hash,population_digest=commit.population_digest,
        ledger_identity_hash=record['ledger_identity_hash'],key_fingerprint=record['key_fingerprint'])
    return dict(private=private,commit=commit,native_record=record,raw=raw,pins=pins)


def test_exact_inventory_mirrors_pinned_sdk_names_facts_chunks_and_probe(paid_case):
    c=paid_case['private'].embedding;inv=c.inventory
    assert c.schema_version==3 and c.request()['input']==[i.text for i in inv.inputs]
    keys=[key for i in inv.inputs for key in i.usage_keys]
    assert {'probe','chunk','entity'}<={k.split(':')[0] for k in keys}
    assert inv==processing_embedding_inventory_v3(c.qualified_payload)
    old=DerivedEmbeddingContextV2.model_validate({k:v for k,v in c.model_dump(mode='python').items() if k!='inventory'}|{'schema_version':2})
    assert len(old.request()['input'])==len(c.source_refs)<len(c.request()['input'])
    changed=copy.deepcopy(c.inventory.model_dump(mode='python'));changed['inputs']=tuple(reversed(changed['inputs']))
    with pytest.raises(PermissionError):DerivedSDKEmbeddingContextV3.model_validate(c.model_dump(mode='python')|{'inventory':changed})


def test_authenticated_paid_vectors_reused_exactly_and_unknown_sdk_text_never_dispatched(paid_case):
    data=verify_paid_sdk_embedding_v3(**paid_case);adapter=PaidProjectionEmbedderV3(data)
    for index,item in enumerate(data.inventory.inputs):
        vector=adapter.embed_query(item.text)
        assert tuple(vector)==data.vectors[index]
        vector[0]=999
        assert adapter.embed_query(item.text)[0]!=999
    adapter.assert_observed(tuple(k for item in data.inventory.inputs for k in item.usage_keys))
    with pytest.raises(PermissionError,match='outside exact'):adapter.embed_query('unadmitted employee query')
    with pytest.raises(PermissionError,match='swallowed'):adapter.assert_no_denials()


@pytest.mark.parametrize('field',list(PaidSDKEmbeddingPinsV3.model_fields))
def test_every_external_paid_custody_pin_is_required(paid_case,field):
    pins=paid_case['pins'].model_copy(update={field:'f'*64})
    with pytest.raises((PermissionError,ValueError)):verify_paid_sdk_embedding_v3(**(paid_case|{'pins':pins}))


@pytest.mark.parametrize('damage',('missing','index','reorder','dimension','zero','nonfinite','model','failed','incomplete','request','commit-root'))
def test_malformed_or_substituted_paid_wire_never_becomes_sdk_vectors(paid_case,damage):
    case=dict(paid_case);record=copy.deepcopy(case['native_record']);response=json.loads(case['raw'])
    if damage=='missing':response['data'].pop()
    elif damage=='index':response['data'][0]['index']=1
    elif damage=='reorder':response['data'].reverse()
    elif damage=='dimension':response['data'][0]['embedding'].pop()
    elif damage=='zero':response['data'][0]['embedding']=[0.0]*256
    elif damage=='nonfinite':response['data'][0]['embedding'][0]=float('inf')
    elif damage=='model':response['model']='wrong'
    elif damage=='failed':record['failed']=True
    elif damage=='incomplete':record['wire_custody']['complete']=False
    elif damage=='request':record['request_hash']='f'*64
    elif damage=='commit-root':
        case['commit']=case['commit'].model_copy(update={'parent_registry_hash':'f'*64})
    if damage not in ('failed','incomplete','request','commit-root'):
        raw=json.dumps(response).encode();record['raw_response']=raw.decode();sha=hashlib.sha256(raw).hexdigest()
        record['raw_response_hash']=sha;record['wire_custody'].update(raw_sha256=sha,captured_bytes=len(raw));case['raw']=raw
        case['commit']=case['commit'].model_copy(update={'raw_response_hash':sha})
    # These synthetic malformed payloads are authored before their fixture pins,
    # so failures exercise the actual wire validators rather than only hash drift.
    if damage!='commit-root':
        case['commit']=case['commit'].model_copy(update={'native_custody_receipt_hash':digest(record)})
        case['pins']=case['pins'].model_copy(update={'native_receipt_hash':digest(record),
            'commit_hash':digest(case['commit'].model_dump(mode='json'))})
    case['native_record']=record
    with pytest.raises((PermissionError,ValueError)):verify_paid_sdk_embedding_v3(**case)


def test_sdk_relation_fact_texts_are_deduplicated_with_every_usage_key(paid_case):
    payload=copy.deepcopy(paid_case['private'].embedding.qualified_payload)
    model=payload['operating_models'][0];process=model['processes'][0]
    oid=payload['observations'][0]['observation_id'];support={'observation_ids':[oid]}
    workflow={'workflow_id':'fixture-flow','process_id':process['process_id'],'steps':[
        {'step_id':'a','label':'Start ART','support':support},{'step_id':'b','label':'Receive ART','support':support}],
        'gateways':[],'conditions':[],'transitions':[{'transition_id':'edge','from_id':'a','to_id':'b','support':support}]}
    # Pure inventory transformation only: this changed packet is not admitted or
    # persisted as a qualified model. Actual runtime must validate its real seal.
    payload['workflows']=[workflow]
    inv=processing_embedding_inventory_v3(payload)
    facts=[i for i in inv.inputs if any(k.startswith('relation:') for k in i.usage_keys)]
    assert len(facts)==1 and facts[0].text=='Reported transition a → b'
    assert len(facts[0].usage_keys)==2


def test_actual_sdk_float32_storage_rule_is_exact_without_epsilon_or_normalization():
    from oracle_brain.operating_model.paid_sdk_embeddings_v3 import sdk_float32_vector
    import struct
    vector=[0.1]+[0.0]*255
    stored=sdk_float32_vector(vector)
    assert stored[0]==struct.unpack('!f',struct.pack('!f',0.1))[0] and stored[0]!=0.1
    assert stored[1:]==tuple(vector[1:])
    for bad in ([1e100]+[0.0]*255,[1e-100]*256,[float('nan')]*256):
        with pytest.raises(ValueError):sdk_float32_vector(bad)
    changed=list(stored);changed[0]=0.10001
    assert tuple(changed)!=stored


def test_actual_sdk_graph_uses_exact_paid_vectors_and_rejects_mutation_and_swallowed_unknown(admin_url,processing,tmp_path):
    """Real SDK/SQL component, injected paid packet; NOT full native journey."""
    import asyncio,os,re
    from dev.oracle2.test_readonly_graph_fixture import owned_target
    from test_processing_documentary_journey import qualified_journey,assert_no_uncited_originals
    from oracle_brain.operating_model.sdk_projection import PaidProcessingSDKProjectionV3
    from oracle_brain.operating_model.paid_sdk_embeddings_v3 import sdk_float32_vector
    q=qualified_journey(admin_url,processing,tmp_path);m=q['manifest'];payload=q['ledger'].read(m.workspace_id,m.artifact_id,m.version)
    data=verify_paid_sdk_embedding_v3(**paid_case_for(payload,m));adapter=PaidProjectionEmbedderV3(data)
    graph_url=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL'];project=os.environ['COMPOSE_PROJECT_NAME']
    container=project+'-falkor-candidate-1';owned_target(container,graph_url)
    generation=uuid4()
    async def exercise():
        p=PaidProcessingSDKProjectionV3(graph_url,workspace_id=m.workspace_id,artifact_id=m.artifact_id,
            artifact_version=m.version,generation=generation,embedder=adapter,qualification_guard=q['guard'])
        assert p.graph_name==f'oracle_processing_v1_{m.workspace_id.hex}_{m.artifact_id.hex}_{m.version}_{generation.hex}'
        try:
            result=await p.build(q['ledger'],m.workspace_id,m.artifact_id,m.version)
            proof=await p.paid_projection_proof(payload)
            assert proof.embedding_wire_hash==data.witness.raw_response_hash
            assert result['paid_embedding']==proof.model_dump(mode='json')
            nodes=(await p.connection.query('MATCH (n) RETURN n')).result_set
            for row in nodes:
                for node in row:assert_no_uncited_originals(node.properties)
            first=(await p.connection.query('MATCH (c:Chunk) RETURN c.id,c.embedding LIMIT 1')).result_set[0]
            assert first[1] and len(first[1])==256
            wrong=[1.0]+[0.0]*255
            await p.connection.query('MATCH (c:Chunk {id:$id}) SET c.embedding=vecf32($v)',params={'id':first[0],'v':wrong})
            with pytest.raises(PermissionError,match='paid response'):await p.paid_projection_proof(payload)
            await p.connection.query('MATCH (c:Chunk {id:$id}) SET c.embedding=vecf32($v)',params={'id':first[0],'v':first[1]})
            await p.paid_projection_proof(payload)
            # SDK may swallow this exception; independent pre-ACK proof MUST NOT.
            with pytest.raises(PermissionError):adapter.embed_query('unappointed SDK text')
            with pytest.raises(PermissionError,match='swallowed'):await p.paid_projection_proof(payload)
            fresh=PaidProcessingSDKProjectionV3(graph_url,workspace_id=m.workspace_id,artifact_id=m.artifact_id,
                artifact_version=m.version,generation=generation,embedder=PaidProjectionEmbedderV3(data),qualification_guard=q['guard'])
            try:
                with pytest.raises(PermissionError,match='prior committed'):await fresh.load(q['ledger'],m.workspace_id,m.artifact_id,m.version)
            finally:await fresh.close()
        finally:
            # Re-prove exact own candidate target; remove ONLY this UUID graph.
            owned_target(container,graph_url)
            await p.connection.delete_graph();await p.close()
    asyncio.run(exercise())


def test_paid_supported_sdk_tls_config_keeps_exact_target_and_every_tls_option():
    from dataclasses import replace
    from graphrag_sdk import ConnectionConfig
    from oracle_brain.operating_model.sdk_projection import paid_tls_connection_config_v3
    uri='rediss://scope_user:protected%40password@graph.example.invalid:6380'
    cfg=ConnectionConfig(host='graph.example.invalid',port=6380,username='scope_user',password='protected@password',
        graph_name='exact_owned_graph',query_timeout_ms=30000,ssl=True,ssl_check_hostname=True,ssl_cert_reqs='required',
        ssl_ca_certs='/protected/ca.pem',ssl_certfile='/protected/client.pem',ssl_keyfile='/protected/client.key')
    selected=paid_tls_connection_config_v3(uri,'exact_owned_graph',cfg)
    assert selected==cfg and selected is not cfg
    assert paid_tls_connection_config_v3(uri,'exact_owned_graph',replace(selected,query_timeout_ms=100,pool_timeout=0.1)).query_timeout_ms==100
    cfg.ssl=False
    assert selected.ssl is True
    for field,value in [('host','other'),('port',6379),('username','admin'),('password','other'),('graph_name','other'),
        ('ssl',False),('ssl_check_hostname',False),('ssl_cert_reqs','none'),('ssl_ca_certs',None),('ssl_certfile',None),
        ('ssl_keyfile',None),('query_timeout_ms',None),('pool_timeout',float('inf'))]:
        with pytest.raises(PermissionError):paid_tls_connection_config_v3(uri,'exact_owned_graph',replace(selected,**{field:value}))
    with pytest.raises(PermissionError):paid_tls_connection_config_v3(uri.replace('rediss:','redis:'),'exact_owned_graph',selected)


def test_metadata_coverage_needs_no_paidwire_and_matches_compiler_actual_vector_digest(paid_case):
    from oracle_brain.operating_model.paid_sdk_embeddings_v3 import graph_vector_coverage_v3,sdk_float32_vector
    data=verify_paid_sdk_embedding_v3(**paid_case);rows={'chunks':[],'entities':[],'relations':[]}
    for i,item in enumerate(data.inventory.inputs):
        vector=list(sdk_float32_vector(data.vectors[i]))
        for key in item.usage_keys:
            kind,identifier=key.split(':',1)
            if kind=='chunk':rows['chunks'].append([item.text,vector])
            elif kind=='entity':rows['entities'].append([identifier,item.text,vector])
            elif kind=='relation':rows['relations'].append([identifier,item.text,vector])
    compiler=graph_vector_coverage_v3(data.inventory,**rows,paid_data=data)
    assert graph_vector_coverage_v3(data.inventory,**rows)==compiler
    damaged=copy.deepcopy(rows);damaged['chunks'][0][1][1]=0.0
    changed=graph_vector_coverage_v3(data.inventory,**damaged)
    assert changed[0]!=compiler[0]  # Executor MUST compare current authenticated ACK.
    with pytest.raises(PermissionError):graph_vector_coverage_v3(data.inventory,**damaged,paid_data=data)
    with pytest.raises(PermissionError):graph_vector_coverage_v3(data.inventory,**(rows|{'chunks':rows['chunks'][:-1]}))
