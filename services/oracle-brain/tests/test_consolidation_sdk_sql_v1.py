"""Actual SQL + SDK/TLS graph proof with explicitly invented native vectors.

This exercises installed source contracts, not a provider, deployment or full-D
qualification. No successful graph build may stand in for its missing SQL ACK.
"""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from uuid import uuid4

import psycopg
import pytest
from graphrag_sdk import ConnectionConfig

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.paid_sdk_embeddings_v3 import PaidProjectionEmbedderV3,verify_paid_sdk_embedding_v3
from oracle_brain.operating_model.sdk_projection import PaidConsolidationSDKProjectionV1
from test_consolidation_sql_v1 import sql_qualified_v3,prepared_qualified_model
from test_paid_sdk_embeddings_v3 import paid_case_for
from test_purpose_transport import bound_tls,certificates,SERVER
from test_hosting_boundary import WORKER


def test_actual_consolidation_sql_paid_sdk_graph_keeps_assertions_and_rebuilds_without_ack(admin_url,sql_qualified_v3,tmp_path,bound_tls,certificates):
    from dev.oracle2.test_readonly_graph_fixture import processing_writer,owned_target
    from dev.oracle2.test_graph_tls_fixture import owned_graph_tls,verify_graph_tls_peer
    state=prepared_qualified_model(admin_url,sql_qualified_v3,tmp_path,return_fixture=True)
    manifest=state['manifest'];ledger=state['ledger'];payload=state['q']['payload']
    graph=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL']
    container=os.environ['COMPOSE_PROJECT_NAME']+'-falkor-candidate-1'
    owned_target(container,graph)
    data=verify_paid_sdk_embedding_v3(**paid_case_for(payload,manifest))
    tls,_=bound_tls

    async def exercise():
        built_graphs=[]
        for attempt in range(2):
            generation=uuid4()
            with processing_writer(container,graph,tmp_path/('writer-'+str(attempt)),workspace_id=manifest.workspace_id,
                    artifact_id=manifest.artifact_id,version=manifest.version,generation=generation) as writer:
                with owned_graph_tls(container,graph,server_context=tls,expected_client_uri=WORKER) as port:
                    verify_graph_tls_peer(port,ca_file=certificates/'ca.pem',certificate_file=certificates/'worker.pem',key_file=certificates/'worker.key',expected_server_uri=SERVER)
                    parsed=urlsplit(writer.environment['ORACLE2_TEST_PROCESSING_WRITER_GRAPH_URL'])
                    url=urlunsplit(('rediss',parsed.netloc.rsplit('@',1)[0]+'@localhost:'+str(port),'','',''))
                    name='oracle_processing_v1_'+manifest.workspace_id.hex+'_'+manifest.artifact_id.hex+'_1_'+generation.hex
                    config=ConnectionConfig.from_url(url,graph_name=name,ssl=True,ssl_check_hostname=True,ssl_cert_reqs='required',
                        ssl_ca_certs=str(certificates/'ca.pem'),ssl_certfile=str(certificates/'worker.pem'),ssl_keyfile=str(certificates/'worker.key'),
                        query_timeout_ms=3000,retry_count=1,pool_timeout=1)
                    options=dict(workspace_id=manifest.workspace_id,artifact_id=manifest.artifact_id,artifact_version=manifest.version,
                        generation=generation,embedder=PaidProjectionEmbedderV3(data),qualification_guard=state['guard'],connection_config=config)
                    class UnappointedProjection(PaidConsolidationSDKProjectionV1):pass
                    # Inheritance must not admit a third execution profile.
                    with pytest.raises(PermissionError):
                        unappointed=UnappointedProjection(url,**options)
                        try:await unappointed.build(ledger,manifest.workspace_id,manifest.artifact_id,manifest.version)
                        finally:await unappointed.close()
                    projection=PaidConsolidationSDKProjectionV1(url,**options)
                    try:
                        receipt=await projection.build(ledger,manifest.workspace_id,manifest.artifact_id,manifest.version)
                        assert receipt['content_hash']==manifest.content_hash and receipt['paid_embedding']
                        records=(await projection.connection.query("MATCH (n:OperatingModelRecord) WHERE n.kind='temporal_assertion' RETURN n.id,n.payload_hash")).result_set
                        expected={('assertion:'+a['assertion_id']+':'+str(a['revision'])):a for a in payload['consolidation_core']['assertions']}
                        assert len(records)==len(expected)
                        for identifier,seal in records:
                            assert seal==digest(expected[identifier])
                        chunks=(await projection.connection.query('MATCH (c:Chunk) RETURN c.text')).result_set
                        assert chunks and all(json.loads(row[0])['qualified_consolidation_core']==payload['consolidation_core'] for row in chunks)
                        sealed=(await projection.connection.query('MATCH (s:OperatingModelSnapshot) RETURN s.content_hash,s.finalized')).result_set
                        assert sealed==[[manifest.content_hash,True]]
                        await projection.verify(payload)
                        built_graphs.append(projection.graph_name)
                    finally:await projection.close()
                    # A fresh reader cannot adopt a completed graph or a local
                    # build receipt as an actual committed projection delivery.
                    fresh=PaidConsolidationSDKProjectionV1(url,**(options|{'embedder':PaidProjectionEmbedderV3(data)}))
                    try:
                        with pytest.raises(PermissionError,match='prior committed'):
                            await fresh.load(ledger,manifest.workspace_id,manifest.artifact_id,manifest.version)
                    finally:await fresh.close()
        assert len(set(built_graphs))==2
    asyncio.run(exercise())
    with psycopg.connect(admin_url) as connection:
        assert connection.execute('SELECT count(*) FROM oracle2.operating_projection_receipts WHERE workspace_id=%s',(manifest.workspace_id,)).fetchone()==(0,)
        assert connection.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND delivered_at IS NOT NULL',(manifest.workspace_id,)).fetchone()==(0,)
