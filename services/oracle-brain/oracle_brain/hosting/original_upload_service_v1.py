"""Fixed small-request chunk listener; whole-PDF listener remains unchanged."""
from datetime import datetime,timezone,timedelta
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading,time,ipaddress,socket
from cryptography import x509
from .gateway import MutualTLSServer,server_tls
from .original_intake_v1 import OriginalIntakeFactoryV1
from .original_upload_settings_v1 import load_original_upload_settings_v1,check_upload_spool_v1
from .original_upload_store_v1 import OriginalUploadStoreV1,parse_upload_request_v1,MAX_REQUEST
from .replacement_transport_v1 import fixed_request_length_v1,read_request_body_v1,peer_der_v1
from oracle_brain.operating_model.contracts import canonical_bytes

PATH='/v1/replacement/upload/chunks'


def protected_original_upload_chunks_server_v1(intake,peer_profile_path,expected_peer_profile_sha256):
    settings=load_original_upload_settings_v1(intake,peer_profile_path,expected_peer_profile_sha256)
    p=settings.profile;store=OriginalUploadStoreV1(settings,OriginalIntakeFactoryV1(intake));slot=threading.BoundedSemaphore(1)
    tls=server_tls(certfile=p.server_certificate_file,keyfile=p.server_key_file,cafile=p.client_ca_file)
    settings.current()
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.wall=datetime.now(timezone.utc);self.mono=time.monotonic();super().setup()
        def log_message(self,*args):pass
        def _deny(self,status=503):
            self.close_connection=True
            try:
                self.connection.settimeout(1);self.send_response(status);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers()
            except Exception:pass
        def send_error(self,*args):self._deny()
        def do_GET(self):self._deny(405)
        def _peer(self):
            der=peer_der_v1(self.connection,expected_uri=p.client_uri,expected_der_sha256=p.client_certificate_sha256)
            cert=x509.load_der_x509_certificate(der);now=datetime.now(timezone.utc)
            if not cert.not_valid_before_utc<=now<cert.not_valid_after_utc:raise PermissionError('expired upload peer')
            return cert.not_valid_after_utc
        def do_POST(self):
            acquired=False;started=False;self.close_connection=True
            try:
                if self.server.closing:raise PermissionError('upload listener closing')
                if any(self.headers.get_all(k,[]) for k in ('Content-Encoding','Range','If-Range','If-Match','If-None-Match','If-Modified-Since','If-Unmodified-Since','Expect')):raise PermissionError('fixed upload request required')
                length=fixed_request_length_v1(self,path=PATH,content_type='application/json',maximum_bytes=MAX_REQUEST)
                bound=min(self.wall+timedelta(seconds=30),settings.current(),self._peer());check_upload_spool_v1(settings)
                if not slot.acquire(blocking=False):raise PermissionError('upload action active')
                acquired=True
                raw=read_request_body_v1(self,length,absolute_monotonic_deadline=self.mono+max(0,(bound-self.wall).total_seconds()))
                request=parse_upload_request_v1(raw)
                if not datetime.now(timezone.utc)<request.caller_deadline<=bound:raise PermissionError('original upload deadline required')
                result=store.apply(request,peer_until=self._peer())
                end=min(result.valid_until,settings.current(),self._peer(),request.caller_deadline)
                remaining=min((end-datetime.now(timezone.utc)).total_seconds(),30-(time.monotonic()-self.mono))
                if end!=result.valid_until:raise PermissionError('upload reply scope narrowed after observation')
                if remaining<=0:raise PermissionError('upload reply lease elapsed')
                data=canonical_bytes(result.model_dump(mode='json'))
                if len(data)>16384:raise PermissionError('bounded upload response required')
                self.connection.settimeout(remaining);started=True;self.send_response(200)
                self.send_header('Connection','close');self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store, private');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
            except Exception:
                if not started:self._deny()
                else:self.close_connection=True
            finally:
                if acquired:slot.release()
    class UploadServer(MutualTLSServer):
        address_family=socket.AF_INET6 if ipaddress.ip_address(p.listen_host).version==6 else socket.AF_INET
        daemon_threads=False
        block_on_close=False
        def __init__(self):
            self.closing=False;self._active=set();self._active_condition=threading.Condition()
            super().__init__((p.listen_host,p.listen_port),Handler,tls=tls)
        def process_request(self,request,address):
            with self._active_condition:
                if self.closing or not self._connections.acquire(blocking=False):
                    self.shutdown_request(request);return
                self._active.add(request)
            try:ThreadingHTTPServer.process_request(self,request,address)
            except BaseException:
                self._connections.release()
                with self._active_condition:self._active.discard(request);self._active_condition.notify_all()
                raise
        def process_request_thread(self,request,address):
            try:super().process_request_thread(request,address)
            finally:
                with self._active_condition:self._active.discard(request);self._active_condition.notify_all()
        def server_close(self):
            with self._active_condition:self.closing=True
            super().server_close();end=time.monotonic()+40
            with self._active_condition:
                while self._active and time.monotonic()<end:self._active_condition.wait(max(0,end-time.monotonic()))
                if self._active:raise PermissionError('owned upload handlers remain active')
    server=UploadServer()
    try:
        settings.current();server.upload_store=store;return server
    except BaseException:
        server.server_close();raise
