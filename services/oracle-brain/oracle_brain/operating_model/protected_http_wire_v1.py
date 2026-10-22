"""Single neutral unbuffered HTTP wire parser; no URL, identity or authority.

Exact source extraction from the existing research transport owner. Fixed
consumers retain their independent endpoint, TLS, rights and original window.
"""
class UnsafeDestination(ValueError):
    pass


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
