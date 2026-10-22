"""Official AWS arithmetic vector and independent fixed-read verification.

No actual credential, service, JWT issuance, company object or network call.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import pytest
from oracle_brain.migration._legacy_s3_signing_v1 import (
    _signature_of_canonical_v1,_canonical_object_path_v1,_s3_read_headers_v1,_strong_etag_v1,
)


def test_official_AWS_S3_GET_known_signature_vector():
    # Official AWS example (public toy key), not a live credential:
    # https://docs.aws.amazon.com/AmazonS3/latest/developerguide/sig-v4-header-based-auth.html
    empty=hashlib.sha256(b'').hexdigest()
    canonical='GET\n/test.txt\n\nhost:examplebucket.s3.amazonaws.com\nrange:bytes=0-9\nx-amz-content-sha256:'+empty+'\nx-amz-date:20130524T000000Z\n\nhost;range;x-amz-content-sha256;x-amz-date\n'+empty
    assert hashlib.sha256(canonical.encode()).hexdigest()=='7344ae5b7ee6c3e7e6b0fe0640412a37625d1fbfff95c48bbb2dc43964946972'
    assert _signature_of_canonical_v1(canonical,'20130524T000000Z','us-east-1','wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')=='f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41'


def arguments(**changes):
    out=dict(method='GET',path='/storage/v1/s3/invented/a%20file.pdf',host='a'*20+'.storage.supabase.co',region='us-east-1',
        project_ref='a'*20,anonymous_key='invented.anon.key',session_token='invented.ordinary.session',
        now=datetime(2026,10,22,tzinfo=timezone.utc),etag='"actual-opaque-current"')
    return out|changes


@pytest.mark.parametrize('method',['HEAD','GET'])
def test_independently_reconstructed_fixture_verifies_closed_request(method):
    a=arguments(method=method)
    headers=_s3_read_headers_v1(**a)
    algorithm,parts=headers['authorization'].split(' ',1)
    fields=dict(piece.split('=',1) for piece in parts.split(','))
    assert algorithm=='AWS4-HMAC-SHA256'
    signed=fields['SignedHeaders'].split(';')
    assert signed==sorted(signed) and 'if-match' in signed and 'x-amz-security-token' in signed
    # Independent test verifier reconstructs from actual transmitted fields.
    raw='\n'.join((method,a['path'],'',''.join(k+':'+headers[k]+'\n' for k in signed),fields['SignedHeaders'],hashlib.sha256(b'').hexdigest()))
    day,region,service,terminal=fields['Credential'].split('/')[1:]
    key=('AWS4'+a['anonymous_key']).encode()
    for chunk in (day,region,service,terminal):key=hmac.digest(key,chunk.encode(),'sha256')
    string='\n'.join((algorithm,headers['x-amz-date'],'/'.join((day,region,service,terminal)),hashlib.sha256(raw.encode()).hexdigest()))
    assert hmac.digest(key,string.encode(),'sha256').hex()==fields['Signature']
    assert headers['x-amz-security-token']==a['session_token']


@pytest.mark.parametrize('key,expected',[('a b.pdf','a%20b.pdf'),('中文.pdf','%E4%B8%AD%E6%96%87.pdf'),('literal%2F.pdf','literal%252F.pdf'),('a//b.pdf','a//b.pdf'),('a?x=1#v.pdf','a%3Fx%3D1%23v.pdf')])
def test_UTF8_percent_query_bytes_are_exact_object_key_not_URL_selector(key,expected):
    assert _canonical_object_path_v1('invented',key)=='/storage/v1/s3/invented/'+expected


@pytest.mark.parametrize('change',[{'method':'PUT'},{'method':'POST'},{'path':'/storage/v1/s3/x?list=true'},
    {'path':'https://other.invalid/object'},{'host':'other.invalid'},{'project_ref':'bad'},
    {'session_token':'injected\r\nHeader: x'},{'anonymous_key':'sb_secret_invented'},{'etag':None},
    {'now':datetime(2026,10,22)},{'region':'us-east-1\nHeader:x'}])
def test_no_generic_signing_target_method_headers_credential_discovery_or_unconditional_GET(change):
    with pytest.raises(PermissionError):_s3_read_headers_v1(**arguments(**change))


@pytest.mark.parametrize('etag',['W/"weak"','unquoted','"injected\r\n"','"white space"','"'+('x'*511)+'"'])
def test_opaque_ETag_is_strong_bounded_precondition_never_body_hash(etag):
    with pytest.raises(PermissionError):_strong_etag_v1(etag)


@pytest.mark.parametrize('bucket,key',[('../x','a'),('x','a/../b'),('x','./a'),('x','nul\0.pdf')])
def test_source_locator_cannot_escape_fixed_storage_operation(bucket,key):
    with pytest.raises(PermissionError):_canonical_object_path_v1(bucket,key)
