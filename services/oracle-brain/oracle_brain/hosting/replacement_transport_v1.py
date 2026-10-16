"""Private framing shared by fixed replacement handlers; no authority dispatch."""
import hashlib,ssl,time,math
from cryptography import x509
from cryptography.x509.oid import ExtensionOID
from .purpose_journey_v2 import _require

def fixed_request_length_v1(handler,*,path,content_type,maximum_bytes):
    _require(handler.path==path and handler.command=='POST'
        and handler.headers.get_all('Transfer-Encoding',[])==[],'fixed nonchunked replacement route required')
    lengths=handler.headers.get_all('Content-Length',[])
    types=handler.headers.get_all('Content-Type',[])
    _require(len(lengths)==1 and lengths[0].isascii() and lengths[0].isdigit()
        and len(types)==1 and types[0]==content_type
        and type(maximum_bytes) is int and 0<int(lengths[0])<=maximum_bytes,
        'exact bounded replacement request framing required')
    return int(lengths[0])

def read_request_body_v1(handler,length,*,absolute_monotonic_deadline):
    _require(type(length) is int and length>0 and type(absolute_monotonic_deadline) in (int,float) and math.isfinite(absolute_monotonic_deadline),
        'absolute replacement body bound required')
    remaining=length;chunks=[]
    while remaining:
        left=absolute_monotonic_deadline-time.monotonic()
        _require(left>0,'original replacement body deadline expired')
        handler.connection.settimeout(left)
        chunk=handler.rfile.read1(remaining)
        _require(type(chunk) is bytes and 0<len(chunk)<=remaining,'complete replacement request bytes required')
        chunks.append(chunk);remaining-=len(chunk)
    _require(time.monotonic()<absolute_monotonic_deadline,'replacement body completed late')
    return b''.join(chunks)

def peer_der_v1(connection,*,expected_uri,expected_der_sha256):
    _require(type(connection) is ssl.SSLSocket and connection.context.verify_mode==ssl.CERT_REQUIRED,
        'actual verified replacement mutual TLS socket required')
    peer=connection.getpeercert(binary_form=True)
    _require(type(peer) is bytes and hashlib.sha256(peer).hexdigest()==expected_der_sha256,
        'exact replacement peer fingerprint required')
    cert=x509.load_der_x509_certificate(peer)
    uris=cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value.get_values_for_type(x509.UniformResourceIdentifier)
    _require(uris==[expected_uri],'actual replacement peer URI differs')
    return peer
