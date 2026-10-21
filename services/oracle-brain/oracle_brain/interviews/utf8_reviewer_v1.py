"""Separately appointed incremental UTF8 byte reviewer; no semantic acceptance."""
import codecs

def review_exact_utf8_v1(data,reading):
    if type(data) is not bytes or not 1<=len(data)<=32768 or type(reading) is not str:raise ValueError('bounded original and retained reading required')
    decoder=codecs.getincrementaldecoder('utf-8')(errors='strict')
    parts=[decoder.decode(data[n:n+127],final=False) for n in range(0,len(data),127)]
    parts.append(decoder.decode(b'',final=True));observed=''.join(parts)
    if not observed.strip() or '\x00' in observed or observed!=reading or observed.encode('utf-8')!=data:raise ValueError('independent original byte review differs')
    return observed
