"""Actual owned SQL/history/private reference composition, injected semantic wires.

The source documents precede full canonical capture and assessment. No real
publisher, company data, native review or business acceptance is claimed.
"""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID,uuid4
import time
import pytest
import psycopg
from test_hosting_boundary import certificates
from test_purpose_transport import bound_tls
from test_consolidation_sql_v1 import sql_qualified_v3,prepared_qualified_model,history_actor,adapter
from qualified_source_fixture_v1 import qualified_two_source_fixture_v1
from test_research_durable_sql import installed_research_fixture_v1,pending,installed_fetcher,installed_reader
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from oracle_brain.operating_model.industry_reference_v1 import (
    IndustryReferenceEvidenceV1,CompanyDecisionContextEvidenceV1,REFERENCE_PREDICATE,CONTEXT_PREDICATE)
from oracle_brain.research.qualified_brief_v1 import QualifiedIndustryBriefV1


def prepared_brief(admin_url,sql_qualified_v3,tmp_path,certificates,monkeypatch):
    import test_research_public_wire as wire
    workspace=sql_qualified_v3['wire']['context'].job.workspace_id
    registration=uuid4();decision=uuid4();reference_ids=(uuid4(),uuid4())
    publication=(datetime.now(timezone.utc)-timedelta(days=2)).date();effective=(datetime.now(timezone.utc)-timedelta(days=1)).date()
    source_text='Publication '+publication.isoformat()+'; effective '+effective.isoformat()+'; Invented Publisher; version-1; public reuse authorized. US home-decor retail section applies to US. EU home-decor retail section applies only to EU.'
    body=source_text.encode('utf8');monkeypatch.setattr(wire,'BODY',body)
    research=installed_research_fixture_v1(admin_url,SimpleNamespace(param=None),workspace=workspace,source=registration)
    fetcher,storage=installed_fetcher(research,tmp_path/'fetch',certificates);posts=[]
    def owned_fetch(**kwargs):
        posts.append(1)
        return ((research['definition']['url'],wire.read_owned(certificates,'chunked')),)
    monkeypatch.setattr(fetcher._transport,'fetch',owned_fetch)
    run=UUID(pending(research)['run_id'])
    with _request_fence_v1(float(time.monotonic()+25)):
        assert fetcher.execute_v1(run,deadline=datetime.now(timezone.utc)+timedelta(seconds=25))['state']=='observed'
    reviewed=datetime.now(timezone.utc)
    context_text='Invented decision '+str(decision)+' is for US home-decor retail. Independent invented reference review observed '+reviewed.isoformat()+'; next review '+(reviewed+timedelta(days=7)).isoformat()+'.'
    fresh=qualified_two_source_fixture_v1(monkeypatch,(context_text,source_text),original_bytes=(context_text.encode(),body))
    def assertions(ctx):
        observations=[e.payload['observations'][0]['observation_id'] for e in ctx.extractions]
        context=CompanyDecisionContextEvidenceV1(purpose='qualified-company-decision-context-v1',decision_id=decision,
            jurisdiction='US',product_scope='home-decor',channel_scope='retail')
        values=[(context,CONTEXT_PREDICATE,'canonical-decision-context-v1',[observations[0]])]
        for ident,jurisdiction in zip(reference_ids,('US','EU'),strict=True):
            value=IndustryReferenceEvidenceV1(purpose='qualified-industry-reference-evidence-v1',reference_id=ident,
                registered_source_id=registration,original=ctx.receipts[1].ref,source_version='version-1',
                publication_date=(reviewed-timedelta(days=2)).date(),effective_date=(reviewed-timedelta(days=1)).date(),
                jurisdiction=jurisdiction,product_scope='home-decor',channel_scope='retail',
                license_permission='public reuse authorized',reviewed_at=reviewed,review_due=reviewed+timedelta(days=7))
            values.append((value,REFERENCE_PREDICATE,'canonical-industry-reference-v1',observations))
        return [dict(assertion_id=str(uuid4()),revision=1,subject_id=str(uuid4()),predicate=predicate,
            value=canonical_bytes(value.model_dump(mode='json')).decode(),unit=unit,provenance='documented_process',
            scope={k:{'mode':'all','identities':[]} for k in ('process','customer','product','region')},
            valid_time='evidenced',valid_from=reviewed.isoformat(),supporting_observations=support,
            temporal_observations=[observations[0]]) for value,predicate,unit,support in values]
    prepared=prepared_qualified_model(admin_url,fresh,tmp_path,return_fixture=True,assertion_factory=assertions)
    # Independent fixture issuer installs a separate history LOGIN for the SAME
    # reference recipient. Research read privilege does not issue model access.
    from test_connected_answer_sql_v1 import own_history
    h,authority=own_history(admin_url,prepared['f'],principal=research['actors']['read'])
    authority=ConsolidationAuthorityV1(h['url'],binding=replace(authority.binding,
        retained_semantic_admissions=prepared['q']['trusted_admission_hashes']),
        delivery_capability_body_hashes=authority.delivery_capability_body_hashes)
    reader=installed_reader(research,tmp_path/'reader',storage)
    return dict(authority=authority,reader=reader,decision=decision,research=research,posts=posts,prepared=prepared,history=h)


async def exercise_brief(f,tmp_path,certificates,bound_tls):
    import os
    from urllib.parse import urlsplit,urlunsplit
    from graphrag_sdk import ConnectionConfig
    from psycopg.types.json import Jsonb
    from dev.oracle2.test_readonly_graph_fixture import processing_writer,processing_reader_scope,owned_target
    from dev.oracle2.test_graph_tls_fixture import owned_graph_tls,verify_graph_tls_peer
    from oracle_brain.operating_model.sdk_projection import PaidConsolidationSDKProjectionV1,ConsolidatedMetadataSDKProjectionV1
    from oracle_brain.operating_model.paid_sdk_embeddings_v3 import PaidProjectionEmbedderV3,verify_paid_sdk_embedding_v3
    from oracle_brain.operating_model.projection_delivery import signature
    from test_paid_sdk_embeddings_v3 import paid_case_for
    from test_consolidation_sql_v1 import RUNTIME,REGISTRY
    from test_purpose_transport import SERVER
    from test_hosting_boundary import WORKER
    state=f['prepared'];m=state['manifest'];payload=state['q']['payload'];original=state['f']
    graph=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL'];container=os.environ['COMPOSE_PROJECT_NAME']+'-falkor-candidate-1'
    owned_target(container,graph);generation=uuid4();tls,_=bound_tls
    name=f'oracle_processing_v1_{m.workspace_id.hex}_{m.artifact_id.hex}_{m.version}_{generation.hex}'
    def config(url):
        return ConnectionConfig.from_url(url,graph_name=name,ssl=True,ssl_check_hostname=True,ssl_cert_reqs='required',
            ssl_ca_certs=str(certificates/'ca.pem'),ssl_certfile=str(certificates/'worker.pem'),ssl_keyfile=str(certificates/'worker.key'),
            query_timeout_ms=3000,retry_count=1,pool_timeout=1)
    with processing_writer(container,graph,tmp_path/'writer',workspace_id=m.workspace_id,artifact_id=m.artifact_id,version=m.version,generation=generation) as writer:
      with owned_graph_tls(container,graph,server_context=tls,expected_client_uri=WORKER) as port:
        verify_graph_tls_peer(port,ca_file=certificates/'ca.pem',certificate_file=certificates/'worker.pem',key_file=certificates/'worker.key',expected_server_uri=SERVER)
        def tls_url(url):
            parsed=urlsplit(url);return urlunsplit(('rediss',parsed.netloc.rsplit('@',1)[0]+'@localhost:'+str(port),'','',''))
        writable=tls_url(writer.environment['ORACLE2_TEST_PROCESSING_WRITER_GRAPH_URL'])
        projection=PaidConsolidationSDKProjectionV1(writable,workspace_id=m.workspace_id,artifact_id=m.artifact_id,artifact_version=m.version,
            generation=generation,embedder=PaidProjectionEmbedderV3(verify_paid_sdk_embedding_v3(**paid_case_for(payload,m))),
            qualification_guard=state['guard'],connection_config=config(writable))
        try:
            built=await projection.build(state['ledger'],m.workspace_id,m.artifact_id,m.version)
            with psycopg.connect(original['url']) as c:
                c.execute("SET LOCAL statement_timeout='5s'")
                lease=c.execute('SELECT oracle2.lease_processing_projection(%s,%s,%s,30)',(m.workspace_id,RUNTIME,REGISTRY)).fetchone()[0]
            body=dict(schema_version=3,event_id=lease['event_id'],workspace_id=str(m.workspace_id),artifact_id=str(m.artifact_id),version=m.version,
                content_hash=m.content_hash,source_digest=m.source_digest,permission_digest=m.permission_digest,graph_name=name,
                record_digest=built['record_digest'],sdk_version='1.4.0',projector_id='invented-industry-actual-SDK-proof',
                lease_role=original['login'],lease_token=lease['lease_token'],lease_attempt=lease['attempts'],lease_until=lease['lease_until'],
                projection_schema=built['projection_schema'],projection_digest=built['projection_digest'],embedding_protocol='paid-sdk-embedding-v3',
                **{k:v for k,v in built['paid_embedding'].items() if k not in ('schema_version','embedding_protocol')})
            secret=b'invented-readonly-graph-fixture-signature-key';seal=signature(secret,body)
            with psycopg.connect(original['url']) as c:
                c.execute("SET LOCAL statement_timeout='5s'")
                assert c.execute('SELECT oracle2.ack_processing_projection(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (lease['event_id'],m.workspace_id,lease['lease_token'],lease['attempts'],Jsonb(body),seal,RUNTIME,REGISTRY,datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]['receipt']==body
            def current(event):
                actual=state['source'].projection_receipt_v3(m.workspace_id,m.artifact_id,m.version)
                assert str(actual.receipt.event_id)==str(event)
                return actual.receipt.model_dump(mode='json')|{'signature':actual.signature}
            with processing_reader_scope(container,graph,tmp_path/'graph-reader',receipt=body|{'signature':seal},secret=secret,current_delivery=current) as reader:
                readonly=tls_url(reader['ORACLE2_TEST_PROCESSING_READONLY_GRAPH_URL'])
                with _request_fence_v1(float(time.monotonic()+29)):
                    deadline=datetime.now(timezone.utc)+timedelta(seconds=28)
                    served=ConsolidatedMetadataSDKProjectionV1(readonly,authority=f['authority'],blobs=FileBlobStore(state['blobs'].root),
                        model_id=m.artifact_id,version=m.version,generation=generation,connection_config=config(readonly),deadline=deadline)
                    try:
                        return await QualifiedIndustryBriefV1(served,(f['reader'],)).brief_v1(decision_id=f['decision'],deadline=deadline)
                    finally:await served.close()
        finally:await projection.close()


def test_actual_qualified_company_context_and_original_reference_produce_distinct_comparisons(admin_url,sql_qualified_v3,tmp_path,certificates,bound_tls,monkeypatch):
    f=prepared_brief(admin_url,sql_qualified_v3,tmp_path,certificates,monkeypatch)
    import asyncio
    result=asyncio.run(exercise_brief(f,tmp_path,certificates,bound_tls))
    assert [r['comparison']['state'] for r in result['references']]==['APPLICABLE','INAPPLICABLE']
    assert all(r['evidence'] and r['retained_receipt_event_id'] for r in result['references'])
    assert result['context_evidence'] and result['company_policy'] is result['business_accepted'] is False
    assert result['graph_delivery_verified'] is True and f['posts']==[1]
    assert datetime.fromisoformat(result['checked_at'])<datetime.fromisoformat(result['valid_until'])


def test_actual_reference_revocation_withholds_brief_without_refetch(admin_url,sql_qualified_v3,tmp_path,certificates,bound_tls,monkeypatch):
    f=prepared_brief(admin_url,sql_qualified_v3,tmp_path,certificates,monkeypatch)
    with psycopg.connect(admin_url) as c:
        c.execute('INSERT INTO oracle2.research_admission_revocations_v1(admission_id) VALUES(%s)',(f['reader']._authority.settings.config.admission_id,))
    import asyncio
    with pytest.raises(PermissionError):asyncio.run(exercise_brief(f,tmp_path,certificates,bound_tls))
    assert f['posts']==[1]
