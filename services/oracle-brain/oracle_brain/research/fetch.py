"""Guarded fetch: rejects private/link-local destinations and unsafe redirects. Transport is injected."""
from dataclasses import dataclass
import socket
from typing import Callable
from urllib.parse import urljoin, urlsplit
from .rights import RightsError, require_public_addresses

MAX_REDIRECTS = 5


class UnsafeDestination(ValueError):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = b''
    location: str | None = None


Resolver = Callable[[str], list[str]]
Transport = Callable[[str, str], Response]  # (url, pinned_ip) -> Response


def system_resolver(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


def check_destination(url: str, resolver: Resolver) -> str:
    try:
        if type(url) is not str or any(ord(c) <= 32 or ord(c) == 127 for c in url):
            raise ValueError('invalid destination')
        parts = urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.username
                or parts.password or parts.port not in (None, 443)):
            raise ValueError('invalid destination')
    except ValueError:
        raise UnsafeDestination('refused HTTPS destination') from None
    try:
        return require_public_addresses(resolver(parts.hostname))
    except RightsError as error:
        raise UnsafeDestination(str(error)) from None


def guarded_fetch(url: str, transport: Transport, resolver: Resolver = system_resolver) -> Response:
    """Every hop is re-validated; the transport must connect to the pinned address (no re-resolution)."""
    for _ in range(MAX_REDIRECTS + 1):
        pinned = check_destination(url, resolver)
        response = transport(url, pinned)
        if response.status in (301, 302, 303, 307, 308):
            if not response.location:
                raise UnsafeDestination('redirect without location')
            url = urljoin(url, response.location)
            continue
        return response
    raise UnsafeDestination('too many redirects')

# Private fixed installed-artifact owner. The general research helper above
# retains its original API; no arbitrary URL/key/redirect selector is added.
class _InstalledArtifactGET:
    def __init__(self,*,url,expected_sha256,byte_count,ca_file,ca_sha256,server_der_sha256,current):
        import re,ssl,hashlib
        from pathlib import Path
        from oracle_brain.hosting.original_intake_v1 import _pinned
        from oracle_brain.hosting.purpose_transport import _BoundedDNSResolver
        if not callable(current) or type(byte_count) is not int or not 0<byte_count<=1024*1024 or any(type(v) is not str or re.fullmatch('[a-f0-9]{64}',v) is None for v in (expected_sha256,ca_sha256,server_der_sha256)):raise UnsafeDestination('fixed artifact pins required')
        parts=urlsplit(url)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.fragment or parts.port not in (None,443) or not parts.path.startswith('/') or any(ord(c)<=32 or ord(c)==127 for c in url):raise UnsafeDestination('exact installed HTTPS artifact required')
        if not Path(ca_file).is_absolute():raise UnsafeDestination('fixed artifact CA required')
        self.url=url;self.parts=parts;self.expected_sha256=expected_sha256;self.byte_count=byte_count;self.ca_file=ca_file;self.ca_sha256=ca_sha256;self.server_der_sha256=server_der_sha256;self.current=current
        self._resolver=_BoundedDNSResolver(parts.hostname,443)
        self._tls=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);self._tls.minimum_version=ssl.TLSVersion.TLSv1_2
        self._tls.load_verify_locations(cadata=_pinned(ca_file,ca_sha256,131072).decode('utf-8'))
    def fetch(self,*,caller_deadline):
        import http.client,socket,threading,time,hashlib
        from datetime import datetime,timezone
        from oracle_brain.hosting.original_intake_v1 import _pinned
        from oracle_brain.research.rights import require_public_addresses
        from oracle_brain.hosting._protected_control_listener_v1 import request_remaining_v1
        original_remaining=request_remaining_v1(required=True)
        now=datetime.now(timezone.utc)
        if type(caller_deadline) is not datetime or caller_deadline.tzinfo is None or not 0<(caller_deadline-now).total_seconds()<=30:raise UnsafeDestination('original artifact deadline required')
        end=time.monotonic()+min(original_remaining,(caller_deadline-now).total_seconds())
        def remaining():
            request_remaining_v1(required=True)
            self.current()
            if hashlib.sha256(_pinned(self.ca_file,self.ca_sha256,131072)).hexdigest()!=self.ca_sha256:raise UnsafeDestination('artifact CA changed')
            value=min(request_remaining_v1(required=True),end-time.monotonic(),(caller_deadline-datetime.now(timezone.utc)).total_seconds())
            if value<=0:raise UnsafeDestination('artifact original horizon elapsed')
            return value
        remaining();addresses=self._resolver.resolve(end)
        # ALL answers must be public unicast, not only the chosen answer. No
        # re-resolution, fallback target, retry, proxy, auth header or redirects.
        require_public_addresses([row[4][0] for row in addresses])
        family,kind,protocol,_,target=addresses[0]
        if family not in (socket.AF_INET,socket.AF_INET6) or kind!=socket.SOCK_STREAM or target[1]!=443:raise UnsafeDestination('artifact DNS answer differs')
        active=socket.socket(family,kind,protocol);conn=None;timer=None
        try:
            active.settimeout(remaining());active.connect(target)
            active.settimeout(remaining());secure=self._tls.wrap_socket(active,server_hostname=self.parts.hostname,suppress_ragged_eofs=False);active=secure
            if hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest()!=self.server_der_sha256:raise UnsafeDestination('artifact TLS DER differs')
            return _read_artifact_http_v1(secure,self.parts.hostname,self.parts.path+('?' + self.parts.query if self.parts.query else ''),self.expected_sha256,self.byte_count,remaining)
        finally:
            if timer:timer.cancel()
            if conn:conn.close()
            active.close()


def _artifact_response_v1(secure,remaining,maximum,**kwargs):
    """One unbuffered view of the verified socket; HTTPResponse parses semantics.

    No header read may prefetch and silently discard undeclared extra plaintext.
    A bounded prefix tracks only the first exact header end and wire byte count.
    """
    import http.client,io
    class Wire(io.RawIOBase):
        def __init__(self):self.prefix=bytearray();self.header_length=None;self.count=0;self.chunks=[]
        def readable(self):return True
        def flush(self):pass  # Unbuffered read-only view; no pending output.
        def readinto(self,buffer):
            secure.settimeout(remaining());data=secure.recv(len(buffer))
            self.chunks.append(bytes(data[:max(0,16384+maximum-self.count)]))
            self.count+=len(data)
            if self.header_length is None:
                self.prefix.extend(data)
                end=self.prefix.find(b'\r\n\r\n')
                if end>=0:
                    self.header_length=end+4
                    if self.header_length>16384:raise UnsafeDestination('artifact header exceeds limit')
                    self.prefix.clear()
                elif len(self.prefix)>16384:raise UnsafeDestination('artifact header exceeds limit')
            if self.count>16384+maximum or (self.header_length is not None and self.count>self.header_length+maximum):raise UnsafeDestination('extra artifact wire bytes')
            buffer[:len(data)]=data;return len(data)
    wire=Wire()
    class View:
        def makefile(self,*_args,**_kwargs):return wire
    class Response(http.client.HTTPResponse):
        def _read_and_discard_trailer(self):
            # Closed wire profiles accept the terminal empty line only. No
            # discarded trailing field may masquerade as response metadata.
            if self.fp.readline(16385)!=b'\r\n':raise UnsafeDestination('response trailers refused')
    response=Response(View(),**kwargs)
    response._oracle_wire_v1=wire
    return response

class ResearchTransportUnknown(UnsafeDestination):
    """Bounded actual response prefix only; never request headers or credentials."""
    def __init__(self,wire=b''):
        super().__init__('research response UNKNOWN; network replay not authorized')
        self.wire=bytes(wire[:1064960])
        self.prior_responses=()
        self.failed_url=None


@dataclass(frozen=True)
class VerifiedResearchResponseV1:
    status:int
    headers:tuple[tuple[str,str],...]
    body:bytes
    wire:bytes


def _read_verified_public_http_v1(secure,hostname,path,maximum,remaining,*,allow_chunked=False,accept='application/json, text/vtt'):
    """ONE semantic HTTP parser on the SAME already verified socket.

    Both original-artifact and registered-public-research owners use this path.
    The latter may accept bounded chunked identity transfers; the original
    artifact's exact length/hash contract below remains unchanged.
    """
    import http.client,socket,threading,re
    if type(maximum) is not int or not 0<maximum<=1048576:raise UnsafeDestination('bounded response required')
    conn=None;timer=None;observed=[]
    try:
        class Connection(http.client.HTTPSConnection):
            def close(connection):
                connection.sock=None
                super().close()
        conn=Connection(hostname,443,timeout=remaining(),context=None);conn.sock=secure
        def response_class(sock,**kw):
            response=_artifact_response_v1(sock,remaining,maximum,**kw)
            observed.append(response)
            return response
        conn.response_class=response_class
        def stop():
            try:secure.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        timer=threading.Timer(remaining(),stop);timer.daemon=True;timer.start();remaining()
        conn.request('GET',path,headers={'Accept':accept,'Accept-Encoding':'identity','Connection':'close'})
        response=conn.getresponse();headers=response.getheaders();seen=set()
        for key,value in headers:
            key=key.lower()
            if key in seen:raise UnsafeDestination('duplicate artifact header')
            seen.add(key)
        if not 200<=response.status<=599 or response.headers.get('Content-Encoding') is not None:
            raise UnsafeDestination('closed identity response required')
        lengths=response.headers.get_all('Content-Length',[]);transfer=response.headers.get_all('Transfer-Encoding',[])
        if transfer:
            if not allow_chunked or transfer!=['chunked'] or lengths:raise UnsafeDestination('ambiguous transfer framing refused')
            expected=None
        else:
            if len(lengths)!=1 or re.fullmatch(r'0|[1-9][0-9]{0,6}',lengths[0]) is None or int(lengths[0])>maximum:
                raise UnsafeDestination('bounded exact response length required')
            expected=int(lengths[0])
        result=bytearray()
        while len(result)<=maximum:
            secure.settimeout(remaining());chunk=response.read(min(65536,maximum+1-len(result)))
            if not chunk:break
            result.extend(chunk)
            if len(result)>maximum:raise UnsafeDestination('decoded response exceeds limit')
        if expected is not None and len(result)!=expected:raise UnsafeDestination('truncated response')
        if not response.isclosed():response.close()
        secure.settimeout(remaining())
        extra=secure.recv(1)
        if extra:
            observed[-1]._oracle_wire_v1.chunks.append(extra)
            raise UnsafeDestination('extra artifact bytes')
        remaining()
        return VerifiedResearchResponseV1(response.status,tuple((k.lower(),v) for k,v in headers),bytes(result),b''.join(response._oracle_wire_v1.chunks))
    except Exception as exc:
        raw=b''.join(observed[-1]._oracle_wire_v1.chunks) if observed else b''
        raise ResearchTransportUnknown(raw) from exc
    finally:
        if timer:timer.cancel()
        for response in observed:response.close()
        if conn:conn.close()


def _read_artifact_http_v1(secure,hostname,path,expected_sha256,byte_count,remaining):
    import hashlib
    response=_read_verified_public_http_v1(secure,hostname,path,byte_count,remaining)
    lengths=[v for k,v in response.headers if k=='content-length']
    if response.status!=200 or lengths!=[str(byte_count)] or len(response.body)!=byte_count:
        raise UnsafeDestination('exact nonredirect artifact length required')
    if hashlib.sha256(response.body).hexdigest()!=expected_sha256:raise UnsafeDestination('artifact original hash differs')
    return response.body


class _InstalledResearchGET:
    """Registered generic public source, bounded retrieval with no credentials.

    Construction belongs solely to fixed research startup/SQL claim handling.
    This is not a source-rights issuer or a caller-selected fetch endpoint.
    All redirect destinations receive fresh public-address/TLS validation;
    no authorization/cookie header exists to forward to another origin.
    """
    def __init__(self,*,url,ca_file,ca_sha256,current):
        import ssl
        from .registry import Source
        from ..operating_model.protected_inputs_v1 import _pinned
        # Reuse the registered source's exact uncredentialed HTTPS policy.
        if type(url) is not str or not 1<=len(url)<=2048:raise UnsafeDestination('bounded research destination required')
        Source('transport-check','transport-check',url,'unknown','unknown','public','weekly')
        if not callable(current):raise UnsafeDestination('fixed source currentness owner required')
        self.url,self.ca_file,self.ca_sha256,self.current=url,ca_file,ca_sha256,current
        self._resolvers={}
        import threading
        self._operation_lock=threading.Lock()
        self._tls=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);self._tls.minimum_version=ssl.TLSVersion.TLSv1_2
        self._tls.load_verify_locations(cadata=_pinned(ca_file,ca_sha256,1000000).decode('utf-8'))

    def fetch(self,*,caller_deadline):
        import socket,time
        from datetime import datetime,timezone
        from ..operating_model.protected_inputs_v1 import _pinned
        from ..operating_model.request_deadline_v1 import request_remaining_v1
        from ..hosting.purpose_transport import _BoundedDNSResolver
        from .rights import require_public_addresses
        if not self._operation_lock.acquire(blocking=False):raise UnsafeDestination('one active source retrieval required')
        try:
            now=datetime.now(timezone.utc)
            if (type(caller_deadline) is not datetime or caller_deadline.tzinfo is None
                    or not 0<(caller_deadline-now).total_seconds()<=30):raise UnsafeDestination('original source deadline required')
            end=time.monotonic()+min(request_remaining_v1(),(caller_deadline-now).total_seconds())
            def remaining():
                _pinned(self.ca_file,self.ca_sha256,1000000)
                value=min(request_remaining_v1(),end-time.monotonic(),(caller_deadline-datetime.now(timezone.utc)).total_seconds())
                if value<=0:raise UnsafeDestination('source retrieval original window expired')
                return value
            url=self.url;trace=[]
            for hop in range(MAX_REDIRECTS+1):
                # Callback is statically wired by the installed research
                # factory to real SQL current claim checks, never from HTTP.
                self.current();remaining()
                from .registry import Source
                if type(url) is not str or not 1<=len(url)<=2048:raise UnsafeDestination('bounded research redirect destination required')
                Source('transport-check','transport-check',url,'unknown','unknown','public','weekly')
                parts=urlsplit(url)
                if parts.fragment:raise UnsafeDestination('fragment destination refused')
                if parts.hostname not in self._resolvers:
                    if len(self._resolvers)>=MAX_REDIRECTS+1:raise UnsafeDestination('installed source resolver bound reached')
                    self._resolvers[parts.hostname]=_BoundedDNSResolver(parts.hostname,443)
                addresses=self._resolvers[parts.hostname].resolve(end)
                require_public_addresses([row[4][0] for row in addresses])
                family,kind,protocol,_,target=addresses[0]
                if family not in(socket.AF_INET,socket.AF_INET6) or kind!=socket.SOCK_STREAM or target[1]!=443:
                    raise UnsafeDestination('source resolved target differs')
                active=socket.socket(family,kind,protocol)
                try:
                    active.settimeout(remaining());active.connect(target)
                    active.settimeout(remaining());active=self._tls.wrap_socket(active,server_hostname=parts.hostname,suppress_ragged_eofs=False)
                    # Actual hostname/CA-verified TLS precedes a fresh real SQL
                    # currentness check and every HTTP byte. No env proxy/DNS
                    # re-resolution, credential or arbitrary request header.
                    self.current();remaining()
                    response=_read_verified_public_http_v1(active,parts.hostname,(parts.path or '/') + ('?'+parts.query if parts.query else ''),
                        1048576,remaining,allow_chunked=True,accept='text/html, application/json, text/plain, application/pdf, */*;q=0.5')
                finally:active.close()
                trace.append((url,response))
                self.current();remaining()
                if response.status not in(301,302,303,307,308):return tuple(trace)
                locations=[value for key,value in response.headers if key=='location']
                if hop==MAX_REDIRECTS or len(locations)!=1:raise UnsafeDestination('bounded redirect destination required')
                url=urljoin(url,locations[0])
            raise UnsafeDestination('source redirect bound exceeded')
        except Exception as exc:
            failure=exc if type(exc) is ResearchTransportUnknown else ResearchTransportUnknown()
            failure.prior_responses=tuple(locals().get('trace',()))
            failure.failed_url=locals().get('url',self.url)
            if failure is exc:raise
            raise failure from exc
        finally:self._operation_lock.release()
