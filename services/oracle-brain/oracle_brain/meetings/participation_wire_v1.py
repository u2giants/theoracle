"""Bounded raw-wire facts only, never TLS/provider identity or send authority."""
from hashlib import sha256
import re

MAX_RESPONSE_WIRE_V1=1048576+16384
_ERRORS=frozenset({'network','timeout','framing','expired','unknown'})


def observed_participation_wire_v1(raw, *, error=None):
    if type(raw) is not bytes or len(raw)>MAX_RESPONSE_WIRE_V1 or error is not None and error not in _ERRORS:
        raise ValueError('bounded exact provider wire observation required')
    facts=dict(complete=False,http_status=None,response_sha256=sha256(raw).hexdigest(),response_byte_count=len(raw),
               error=error or 'framing')
    if error is not None:
        return facts
    try:
        boundary=raw.index(b'\r\n\r\n')+4
        if boundary>16384:raise ValueError()
        lines=raw[:boundary-4].split(b'\r\n')
        first=re.fullmatch(rb'HTTP/1\.[01] ([2-5][0-9]{2}) [\x20-\x7e]*',lines[0])
        if not first:raise ValueError()
        headers={}
        for line in lines[1:]:
            name,separator,value=line.partition(b':')
            if (separator!=b':' or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+",name)
                    or any(c<32 and c!=9 or c==127 for c in value)):
                raise ValueError()
            name=name.lower()
            if name in headers:raise ValueError()
            headers[name]=value.strip(b' \t')
        length=headers.get(b'content-length',b'')
        if (not re.fullmatch(rb'(0|[1-9][0-9]{0,6})',length) or int(length)>1048576
                or b'transfer-encoding' in headers or b'content-encoding' in headers
                or len(raw)!=boundary+int(length)):
            raise ValueError()
        facts.update(complete=True,http_status=int(first[1]),error=None)
    except (ValueError,IndexError):
        pass
    return facts
