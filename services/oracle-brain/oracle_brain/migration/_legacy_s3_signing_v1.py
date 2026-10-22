"""Private fixed empty-body S3 read signing, not JWT or operation authority.

Only the installed current-capture owner calls the closed HEAD/GET builder.
No credential discovery, URL/method/header callback, retries or network API.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import re
from urllib.parse import quote, unquote

_EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()


def _canonical_object_path_v1(bucket, key):
    if (type(bucket) is not str or re.fullmatch(r'[a-zA-Z0-9._-]{1,100}',bucket) is None or bucket in ('.','..')
            or type(key) is not str or not 1<=len(key)<=500 or '\0' in key
            or any(part in ('.','..') for part in key.split('/'))):
        raise PermissionError('exact finite source object locator required')
    # S3 object slashes are literal: do not collapse repeated slashes or decode
    # percent escapes from the actual database key. Encode its UTF8 exactly once.
    return '/storage/v1/s3/'+quote(bucket,safe='-_.~')+'/'+quote(key,safe='/-_.~',encoding='utf8',errors='strict')


def _strong_etag_v1(value):
    if type(value) is not str or re.fullmatch(r'"[\x21\x23-\x7e]{1,510}"',value) is None:
        raise PermissionError('exact bounded strong current ETag required')
    return value


def _signature_of_canonical_v1(canonical, timestamp, region, secret):
    """Internal HMAC arithmetic; official known vectors exercise this only.

    It sends nothing and selects no endpoint, key, identity or operation. The
    sole runtime caller below constructs the entire closed canonical request.
    """
    scope=timestamp[:8]+'/'+region+'/s3/aws4_request'
    string_to_sign='AWS4-HMAC-SHA256\n'+timestamp+'\n'+scope+'\n'+hashlib.sha256(canonical.encode('utf8')).hexdigest()
    key=('AWS4'+secret).encode('utf8')
    for item in (timestamp[:8],region,'s3','aws4_request'):
        key=hmac.new(key,item.encode('utf8'),hashlib.sha256).digest()
    return hmac.new(key,string_to_sign.encode('utf8'),hashlib.sha256).hexdigest()


def _s3_read_headers_v1(*,method,path,host,region,project_ref,anonymous_key,session_token,now,etag=None,port=443):
    if (method not in ('HEAD','GET') or type(path) is not str or not path.startswith('/storage/v1/s3/')
            or '?' in path or '#' in path or re.search(r'[\x00-\x20\x7f]',path)
            or re.fullmatch(r'[a-z0-9]{20}',project_ref) is None
            or host!=project_ref+'.storage.supabase.co'
            or type(port) is not int or not 1<=port<=65535
            or re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+){1,5}',region) is None
            or type(now) is not datetime or now.tzinfo is None or now.utcoffset()!=timedelta(0)
            or any(type(v) is not str or not 1<=len(v)<=16384 or re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',v) is None for v in (anonymous_key,session_token))
            or method=='GET' and etag is None):
        raise PermissionError('closed independently installed S3 read inputs required')
    try:
        if quote(unquote(path,encoding='utf8',errors='strict'),safe='/-_.~',encoding='utf8',errors='strict')!=path:
            raise ValueError('noncanonical path')
    except (ValueError,UnicodeError):
        raise PermissionError('exact canonical UTF8 object path required') from None
    stamp=now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    headers={'host':host if port==443 else host+':'+str(port),'x-amz-date':stamp,'x-amz-content-sha256':_EMPTY_SHA256,'x-amz-security-token':session_token}
    if etag is not None:
        headers['if-match']=_strong_etag_v1(etag)
    names=';'.join(sorted(headers))
    canonical=method+'\n'+path+'\n\n'+''.join(k+':'+headers[k]+'\n' for k in sorted(headers))+'\n'+names+'\n'+_EMPTY_SHA256
    signature=_signature_of_canonical_v1(canonical,stamp,region,anonymous_key)
    scope=stamp[:8]+'/'+region+'/s3/aws4_request'
    headers['authorization']='AWS4-HMAC-SHA256 Credential='+project_ref+'/'+scope+',SignedHeaders='+names+',Signature='+signature
    return headers
