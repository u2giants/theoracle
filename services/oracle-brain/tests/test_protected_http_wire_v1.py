"""Exact neutral extraction preserves old class, parser and HEAD kwargs."""
import ast
import hashlib
import inspect

import pytest
from oracle_brain.operating_model import protected_http_wire_v1 as core
from oracle_brain.research import fetch


@pytest.mark.parametrize('name,expected',[
    ('UnsafeDestination','ec3240e67fd24f0f118937302db650715c17e38df1648230b34da27fac3aaa88'),
    ('_artifact_response_v1','443762782e2f45d40acf0235de420afec5b0dc6c7dfa2c731f1231569adb5eb2'),
])
def test_reviewed_existing_body_AST_unchanged_and_alias_is_exact_same_object(name,expected):
    moved=getattr(core,name)
    assert getattr(fetch,name) is moved
    node=ast.parse(inspect.getsource(moved)).body[0]
    assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()==expected
    assert moved.__module__==core.__name__


def test_old_exception_catches_remain_same_class():
    with pytest.raises(fetch.UnsafeDestination):
        raise core.UnsafeDestination('invented neutral wire refusal')
    assert issubclass(fetch.ResearchTransportUnknown,core.UnsafeDestination)


@pytest.mark.parametrize('method,body',[('GET',b'invented'),('HEAD',b'')])
def test_neutral_parser_retains_existing_method_kwargs_and_actual_unbuffered_bounds(method,body):
    payload=b'HTTP/1.1 200 OK\r\nContent-Length: 8\r\nETag: "invented"\r\nConnection: close\r\n\r\n'+body
    class Socket:
        def __init__(self):self.remaining=payload;self.timeouts=[]
        def settimeout(self,value):self.timeouts.append(value)
        def recv(self,count):
            result=self.remaining[:count];self.remaining=self.remaining[count:];return result
    socket=Socket()
    response=core._artifact_response_v1(socket,lambda:.5,64,method=method)
    response.begin()
    assert response.status==200 and response.getheader('ETag')=='"invented"'
    assert response.read()==body
    assert socket.timeouts and socket.remaining==b''
    response.close()


def test_neutral_parser_does_not_gain_network_or_authority_imports():
    tree=ast.parse(inspect.getsource(core))
    imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
    assert all(isinstance(n,ast.Import) and {a.name for a in n.names}<={'http.client','io'} for n in imports)
