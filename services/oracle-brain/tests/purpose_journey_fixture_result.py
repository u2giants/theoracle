"""Owned synthetic same-journey result mTLS proof; no actual issuer or install."""
from datetime import datetime,timedelta,timezone
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path
from threading import Thread
from uuid import uuid4
import hashlib,json,socket
import psycopg
from psycopg.types.json import Jsonb
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.purpose_transport import PurposeTLSBindingV2,_FixedTLSClientV2
from oracle_brain.hosting.replacement_result_v1 import ProtectedReplacementResultRequestV1,ProtectedReplacementResultResponseV1,PROTOCOL,MAX_RESULT_BYTES
from oracle_brain.hosting.replacement_result_service_v1 import protected_replacement_result_server_v1
from oracle_brain.hosting.custody import _durable_nonce
from purpose_journey_fixture_models import PRIVATE_MARKERS

REQUESTER_URI='spiffe://oracle/purpose/invented-requester'
RESULT_URI='spiffe://oracle/purpose/invented-result'


def prepare_result_service_fixture(admin_url,executor,job,manifest,summary,root,certificates):
    from purpose_journey_fixture_executor import executor_certificate
    from test_replacement_result_settings_v1 import make_protected_result_fixture_settings_v1
    root.mkdir(mode=0o700);c=executor.config;refs=[r.model_dump(mode='json') for r in c.source_refs]
    targets=[dict(schema_version=1,summary_artifact_id=str(summary.artifact_id),summary_version=summary.version,
        summary_content_hash=summary.content_hash,qualified_parent_id=str(manifest.artifact_id),
        qualified_parent_version=manifest.version,qualified_parent_content_hash=manifest.content_hash)]
    seal=executor.resolver.projection_delivery_seal(c.workspace_id,manifest.artifact_id,manifest.version)
    # These are explicitly invented OWNER fixture appointments. Runtime has no
    # table write or authority to appoint itself, and never receives admin_url.
    with psycopg.connect(admin_url) as conn:
        conn.execute("INSERT INTO oracle2.runs(run_id,workspace_id,actor_id,source_id,question,status) VALUES(%s,%s,%s,%s,'invented current human journey','completed')",
            (job.journey_id,c.workspace_id,c.actor_id,c.source_refs[0].source_id))
        conn.execute("INSERT INTO oracle2.processing_journey_runs_v1(run_id,workspace_id,actor_id,journey_revision,population_sha256,original_population,summary_targets,current_model_id,current_model_version,current_model_content_hash,current_ack_event_id,state,answer_hold) VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,'delivered',false)",
            (job.journey_id,c.workspace_id,c.actor_id,digest({'source_refs':refs}),Jsonb(refs),Jsonb(targets),manifest.artifact_id,manifest.version,manifest.content_hash,seal.event_id))
        conn.execute('INSERT INTO oracle2.hosting_replacement_executor_runs_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (c.expected_session_role,job.journey_id,c.workspace_id,c.actor_id,c.runtime_hash,c.source_registry_hash,digest({'source_refs':refs}),manifest.artifact_id,manifest.version,manifest.content_hash,seal.event_id,seal.projection_digest,digest(targets),min(c.expires_at,c.original_horizon)))
    client,key=executor_certificate(certificates,root,identity=REQUESTER_URI,name='requester')
    server,server_key=executor_certificate(certificates,root,identity=RESULT_URI,name='result',server=True)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));listen_port=reservation.getsockname()[1]
    settings=make_protected_result_fixture_settings_v1(executor,root/'settings',journey_id=job.journey_id,
        workflow_id='art-flow',summary_artifact_id=summary.artifact_id,summary_version=summary.version,
        client_certificate_file=client,client_uri=REQUESTER_URI,server_certificate_file=server,server_key_file=server_key,
        client_ca_file=certificates/'ca.pem',server_uri=RESULT_URI,listen_port=listen_port)
    return _ResultProof(settings,root,certificates,client,key,admin_url)


class _ResultProof:
    def __init__(self,settings,root,certificates,client,key,admin_url):
        self.settings,self.root,self.certificates,self.client,self.key=settings,root,certificates,client,key
        self.admin_url=admin_url  # TEST OWNER only, never passed to the service.
        self.projections=[];self.requests=[]

    @contextmanager
    def opened(self):
        import oracle_brain.hosting.replacement_result_service_v1 as actual
        actual_build=actual.build_paid_executor_projection_v3
        actual_handle=actual.ProtectedReplacementResultServiceV1.handle_result_v1
        def observed_build(*args,**kwargs):
            projection=actual_build(*args,**kwargs);self.projections.append(projection);return projection
        async def observed_handle(service,peer,raw):
            self.requests.append(hashlib.sha256(raw).hexdigest())
            return await actual_handle(service,peer,raw)
        with patch.object(actual,'build_paid_executor_projection_v3',side_effect=observed_build),patch.object(actual.ProtectedReplacementResultServiceV1,'handle_result_v1',observed_handle):
            self.server=protected_replacement_result_server_v1(self.settings)
            # TEST instance only: server_close tracks/joins actual handlers.
            self.server.daemon_threads=False
            self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
            self.transport=_FixedTLSClientV2(PurposeTLSBindingV2('localhost',self.server.server_address[1],RESULT_URI,REQUESTER_URI,
                self.certificates/'ca.pem',self.client,self.key,timeout=30))
            try:yield self
            finally:
                self.server.shutdown();self.thread.join(timeout=5);self.server.server_close();assert not self.thread.is_alive()

    def request(self):
        c=self.settings.config;target,horizon=self.settings.current_target();now=datetime.now(timezone.utc)
        return ProtectedReplacementResultRequestV1(schema_version=1,protocol=PROTOCOL,journey_id=c.journey_id,
            expected_journey_revision=target.journey_revision,model_id=c.model_id,model_version=c.model_version,
            content_hash=c.model_content_hash,projection_digest=c.projection_digest,ack_event_id=c.ack_event_id,
            summary_artifact_id=c.summary_artifact_id,summary_version=c.summary_version,summary_content_hash=c.summary_content_hash,
            nonce=uuid4().hex+uuid4().hex,expires_at=min(now+timedelta(seconds=30),horizon,c.expires_at,c.original_horizon))

    def verify_positive(self,stage):
        c=self.settings.config;request=self.request()
        raw=self.transport._post('/v3/replacement/result',request.model_dump(mode='json'),MAX_RESULT_BYTES,valid_until=request.expires_at)
        response=ProtectedReplacementResultResponseV1.model_validate_json(raw)
        assert response.nonce==request.nonce and response.request_sha256==hashlib.sha256(canonical_bytes(request.model_dump(mode='json'))).hexdigest()
        snapshot=response.snapshot.model_dump(mode='json')
        assert snapshot['state']=='answer_ready' and snapshot['answer']['citations'] and snapshot['mapView']
        assert snapshot['model']['ackEventId']==str(c.ack_event_id)
        assert all(marker not in raw.decode() for marker in PRIVATE_MARKERS)
        assert not any(k in raw.decode() for k in ('private_object_key','receipt_secret','raw_wire_hash','native_job_hash'))
        assert self.requests==[response.request_sha256] and len(self.projections)==1
        _durable_nonce(self.root,'actual-result-roundtrip.json',canonical_bytes(dict(schema_version=1,synthetic=True,
            installation=False,client_uri=REQUESTER_URI,server_uri=RESULT_URI,request_sha256=response.request_sha256,
            response_sha256=hashlib.sha256(raw).hexdigest(),journey_id=str(c.journey_id),model_id=str(c.model_id),ack_event_id=str(c.ack_event_id))))
        stage('protected_result_mtls_current_map_summary_cited_answer_verified')
        return response

    def assert_projection_disjoint(self,direct):
        assert len(self.projections)==1
        actual=self.projections[0]
        assert direct is not actual and direct.connection is not actual.connection

    def verify_held(self,stage):
        from oracle_brain.hosting.gateway import GatewayDenied
        import pytest
        # Fresh, distinct observational RPC under the unchanged original horizon.
        denied=self.request();c=self.settings.config;before=len(self.requests)
        with psycopg.connect(self.admin_url) as owner:
            owner.execute('UPDATE oracle2.processing_journey_runs_v1 SET answer_hold=true WHERE run_id=%s',(c.journey_id,))
        try:
            with patch.object(type(self.settings.executor.ledger.blobs),'read',side_effect=AssertionError('held result reached private qualified bytes')) as blob:
                with pytest.raises(GatewayDenied):self.transport._post('/v3/replacement/result',denied.model_dump(mode='json'),MAX_RESULT_BYTES,valid_until=denied.expires_at)
                assert blob.call_count==0 and len(self.requests)==before+1 and len(self.projections)==1
        finally:
            with psycopg.connect(self.admin_url) as owner:
                owner.execute('UPDATE oracle2.processing_journey_runs_v1 SET answer_hold=false WHERE run_id=%s',(c.journey_id,))
        stage('held_result_mtls_denied_before_private_bytes')
