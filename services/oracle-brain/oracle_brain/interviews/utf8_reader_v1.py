"""Deterministic original UTF8 reader program; no semantic/model acceptance."""
def read_exact_utf8_v1(data):
    if type(data) is not bytes or not 1<=len(data)<=1024*1024:raise ValueError('bounded original bytes required')
    text=data.decode('utf-8',errors='strict')
    if not text.strip() or '\x00' in text or text.encode('utf-8')!=data:raise ValueError('original UTF8 roundtrip differs')
    return text
