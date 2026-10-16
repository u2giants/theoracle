"""Fixed mTLS result consumer; no provider, raw-source or metadata-gateway route."""
import asyncio,hashlib,ssl,time,threading,concurrent.futures
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import ExtensionOID
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.model import BusinessOperatingModel
from oracle_brain.operating_model.observations import Observation
from oracle_brain.operating_model.findings import Finding
from oracle_brain.operating_model.summaries import serve_summary
from oracle_brain.operating_model.answer import answer_from_summary
from .purpose_journey_v2 import _worker_file,_require
from .custody import _durable_nonce
from .gateway import MutualTLSServer,server_tls
from .replacement_transport_v1 import fixed_request_length_v1,read_request_body_v1,peer_der_v1
from .paid_executor_v3 import build_paid_executor_projection_v3
from .replacement_result_settings_v1 import ProtectedReplacementResultSettingsV1
from .replacement_result_v1 import (parse_result_request_v1,ProtectedReplacementResultResponseV1,
    encode_result_response_v1,PROTOCOL)
from .replacement_public_view_v1 import (public_snapshot_v1,qualified_map_view_v1,documentary_answer_public_v1)

def _target_identity(target):
    return target.model_dump(mode='json',exclude={'checked_at','valid_until'})

class ProtectedReplacementResultServiceV1:
    def __init__(self,settings):
        _require(type(settings) is ProtectedReplacementResultSettingsV1,'actual fixed protected result settings required')
        self.settings=settings
        self._owned_closes={}
        self._cleanup_unknown=False

    async def _close_owned_projection(self,projection,deadline):
        # Cleanup has no authority to read/query/publish or renew the operation.
        task=asyncio.create_task(projection.connection.close(),name='result-owned-pool-close')
        self._owned_closes[task]=projection
        cancelled=False;cleanup_end=asyncio.get_running_loop().time()+5
        try:
            done,_=await asyncio.wait({task},timeout=max(0,cleanup_end-asyncio.get_running_loop().time()))
        except asyncio.CancelledError:
            cancelled=True
            try:done,_=await asyncio.wait({task},timeout=max(0,cleanup_end-asyncio.get_running_loop().time()))
            except asyncio.CancelledError:
                self._cleanup_unknown=True
                raise
        if not done:
            self._cleanup_unknown=True
            raise PermissionError('owned result connection cleanup remains unknown')
        try:task.result()
        except BaseException:
            self._cleanup_unknown=True
            raise PermissionError('owned result connection cleanup failed') from None
        del self._owned_closes[task]
        if cancelled:raise asyncio.CancelledError
        _require(datetime.now(timezone.utc)<deadline,'result completed after original deadline')

    async def handle_result_v1(self,peer_certificate,raw):
        s=self.settings;c=s.config;start=datetime.now(timezone.utc)
        _require(not self._cleanup_unknown,'owned result cleanup requires observation')
        # Called only by the fixed server using actual verified SSL socket DER.
        _require(type(peer_certificate) is bytes and hashlib.sha256(peer_certificate).hexdigest()==c.client_certificate_sha256,
            'exact authenticated result client required')
        cert=x509.load_der_x509_certificate(peer_certificate)
        uris=cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value.get_values_for_type(x509.UniformResourceIdentifier)
        _require(uris==[c.client_uri],'actual result peer identity differs')
        request=parse_result_request_v1(raw,now=start)
        before,current_until=s.current_target()
        _require((request.journey_id,request.expected_journey_revision,request.model_id,request.model_version,
            request.content_hash,request.projection_digest,request.ack_event_id,request.summary_artifact_id,
            request.summary_version,request.summary_content_hash)==(before.run_id,before.journey_revision,c.model_id,
            c.model_version,c.model_content_hash,c.projection_digest,c.ack_event_id,c.summary_artifact_id,
            c.summary_version,c.summary_content_hash),'current result selection changed')
        deadline=min(request.expires_at,current_until,c.expires_at,c.original_horizon)
        _require(datetime.now(timezone.utc)<deadline,'original result deadline expired')
        # Existing exclusive fsync primitive, preexisting exact appointment root;
        # no fake job, new queue, paid claim or automatic cleanup.
        _durable_nonce(Path(c.nonce_root),'result-v1-'+request.nonce,
            canonical_bytes({'request_sha256':hashlib.sha256(raw).hexdigest(),
                'journey_id':str(c.journey_id),'expires_at':request.expires_at.isoformat()}))
        projection=None
        try:
            async with asyncio.timeout(max(0,(deadline-datetime.now(timezone.utc)).total_seconds())):
                projection=build_paid_executor_projection_v3(s.executor)
                _require(datetime.now(timezone.utc)<deadline,'result startup exceeded original deadline')
                await projection.load(s.executor.ledger,c.workspace_id,c.model_id,c.model_version)
                manifest,payload=s.executor.read_target()
                # Actual graph load/coverage/current ACK completed before any ready body.
                models=payload.get('operating_models')
                _require(type(models) is list and len(models)==1,'exact qualified public model required')
                model=BusinessOperatingModel.model_validate_json(canonical_bytes(models[0]))
                observations=tuple(Observation.model_validate_json(canonical_bytes(o)) for o in payload['observations'])
                findings=tuple(Finding.model_validate_json(canonical_bytes(f)) for f in payload['findings'])
                view=qualified_map_view_v1(model,workflow_id=c.workflow_id,observations=observations,findings=findings)
                s.executor.read_summary(c.summary_artifact_id,c.summary_version)
                summary=serve_summary(s.executor.ledger,c.workspace_id,c.summary_artifact_id,c.summary_version,
                    qualification_guard=s.executor.guard)
                answer=documentary_answer_public_v1(answer_from_summary(s.executor.ledger,summary,intent='overview',
                    qualification_guard=s.executor.guard),tuple(s.executor.config.source_refs))
                # Fresh actual own-run/complete sources/semantic after graph and body.
                after,final_until=s.current_target()
                _require(_target_identity(before)==_target_identity(after),'result current target changed during serving')
                confirmation=after.current_confirmation
                badge=(dict(workflowId=confirmation.workflow_id,version=confirmation.version,
                    contentHash=confirmation.content_hash,current=True)
                    if confirmation is not None and confirmation.eligible and confirmation.workflow_id==c.workflow_id else None)
                state='answer_ready' if answer is not None else ('confirmed_for_scope' if badge else 'draft_ready')
                sources=[dict(workspaceId=str(r.workspace_id),sourceId=str(r.source_id),revision=r.revision,
                    originalSha256=r.original_sha256,readingSha256=r.reading_sha256,parserId=r.parser_id)
                    for r in s.executor.config.source_refs]
                snapshot=public_snapshot_v1(journey_id=str(c.journey_id),journey_revision=after.journey_revision,state=state,
                    sources=sources,model=dict(modelId=str(c.model_id),version=c.model_version,
                        contentHash=c.model_content_hash,ackEventId=str(c.ack_event_id)),confirmation=badge,
                    answer=answer.model_dump(mode='json') if answer else None,message='',map_view=view.model_dump(mode='json'))
                checked=datetime.now(timezone.utc);end=min(deadline,final_until)
                _require(checked<end,'result completed after original deadline')
                response=ProtectedReplacementResultResponseV1(schema_version=1,protocol=PROTOCOL,nonce=request.nonce,
                    request_sha256=hashlib.sha256(raw).hexdigest(),checked_at=checked,expires_at=end,snapshot=snapshot)
                encoded=encode_result_response_v1(response)
        finally:
            if projection is not None:
                await self._close_owned_projection(projection,deadline)
        _require(datetime.now(timezone.utc)<deadline,'result deadline expired before publication')
        return encoded


class _ResultOwnedLoopV1:
    """Only the fixed RESULT listener owns this bounded request/cleanup loop."""
    def __init__(self,service):
        _require(type(service) is ProtectedReplacementResultServiceV1,'exact owned result service required')
        self.service=service;self.requests=set();self.closing=False
        self.loop=asyncio.new_event_loop();self.ready=threading.Event()
        self.thread=threading.Thread(target=self._run,name='protected-result-owned-loop',daemon=False)
        self.thread.start();_require(self.ready.wait(5),'owned result loop did not start')

    def _run(self):
        asyncio.set_event_loop(self.loop);self.ready.set()
        self.loop.run_forever();self.loop.close()

    async def _request(self,peer,raw):
        _require(not self.closing and not self.service._cleanup_unknown and len(self.requests)<32,
            'owned result lifecycle unavailable')
        task=asyncio.current_task();self.requests.add(task)
        try:return await self.service.handle_result_v1(peer,raw)
        finally:self.requests.remove(task)

    def result(self,peer,raw):
        _require(not self.closing,'result listener is closing')
        future=asyncio.run_coroutine_threadsafe(self._request(peer,raw),self.loop)
        try:return future.result(timeout=35)
        except concurrent.futures.TimeoutError:
            # Do not cancel/drop actual work when its handler wait ends.
            self.loop.call_soon_threadsafe(setattr,self.service,'_cleanup_unknown',True)
            raise PermissionError('owned result request remains unknown') from None

    async def _observe(self):
        self.closing=True
        tasks=set(self.requests)|set(self.service._owned_closes)
        if tasks:
            _,pending=await asyncio.wait(tasks,timeout=5)
            _require(not pending,'owned result tasks remain pending')
        for task in tuple(self.service._owned_closes):
            try:task.result()
            except BaseException:raise PermissionError('owned result cleanup remains unknown') from None
            del self.service._owned_closes[task]
        _require(not self.requests,'owned result requests remain active')

    def close(self):
        if self.loop.is_closed() and not self.thread.is_alive():return
        self.closing=True
        # A refusal deliberately leaves this exact loop/thread owned and alive.
        future=asyncio.run_coroutine_threadsafe(self._observe(),self.loop)
        try:future.result(timeout=6)
        except concurrent.futures.TimeoutError:
            raise PermissionError('owned result lifecycle cleanup remains unknown') from None
        self.loop.call_soon_threadsafe(self.loop.stop);self.thread.join(timeout=5)
        _require(not self.thread.is_alive(),'owned result loop remains active')


def protected_replacement_result_server_v1(settings):
    """Only this listener supplies peer DER; no body actor or arbitrary handler."""
    _require(type(settings) is ProtectedReplacementResultSettingsV1,'actual fixed protected result settings required')
    settings.current_target();c=settings.config
    ca=_worker_file(c.client_ca_file,c.client_ca_sha256)
    certificate=_worker_file(c.server_certificate_file,c.server_certificate_sha256)
    key=_worker_file(c.server_key_file,c.server_key_sha256)
    context=server_tls(certfile=c.server_certificate_file,keyfile=c.server_key_file,cafile=c.client_ca_file)
    _require(_worker_file(c.server_certificate_file,c.server_certificate_sha256)==certificate
        and _worker_file(c.server_key_file,c.server_key_sha256)==key
        and _worker_file(c.client_ca_file,c.client_ca_sha256)==ca,'result server TLS changed')
    cert=x509.load_pem_x509_certificate(certificate)
    uris=cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value.get_values_for_type(x509.UniformResourceIdentifier)
    _require(uris==[c.server_uri],'result server certificate identity differs')
    settings.current_target()
    service=ProtectedReplacementResultServiceV1(settings)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                end=time.monotonic()+30
                length=fixed_request_length_v1(self,path='/v3/replacement/result',content_type='application/json',maximum_bytes=4096)
                peer=peer_der_v1(self.connection,expected_uri=c.client_uri,expected_der_sha256=c.client_certificate_sha256)
                raw=read_request_body_v1(self,length,absolute_monotonic_deadline=end)
                result=self.server.owned_result_loop.result(peer,raw)
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(result)));self.end_headers();self.wfile.write(result)
            except Exception:
                self.send_response(503);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers()
        def do_GET(self):
            self.send_response(404);self.send_header('Content-Length','0');self.end_headers()
    class ResultServer(MutualTLSServer):
        daemon_threads=False
        def __init__(self):
            super().__init__((c.listen_host,c.listen_port),Handler,tls=context)
            self.owned_result_loop=_ResultOwnedLoopV1(service)
        def server_close(self):
            # Existing non-daemon request handlers are joined by server_close.
            super().server_close()
            self.owned_result_loop.close()
    return ResultServer()
