"""Native read-only command boundary, preserving the pinned SDK driver."""
import asyncio
from types import SimpleNamespace
import pytest
from oracle_brain.operating_model.sdk_projection import ReadOnlyConnection,SDKProjection

def test_readonly_delegates_native_decoder_and_timeout():
    calls=[]
    class Graph:
        async def ro_query(self,cypher,**kwargs):calls.append((cypher,kwargs));return 'native-result'
    native=SimpleNamespace(graph=Graph(),config=SimpleNamespace(query_timeout_ms=30000))
    connection=ReadOnlyConnection(native)
    assert asyncio.run(connection.query('MATCH (n) RETURN n',{'id':'invented'}))=='native-result'
    assert calls==[('MATCH (n) RETURN n',{'params':{'id':'invented'},'timeout':30000})]
    assert connection.config is native.config

def test_readonly_build_denied_before_any_store_read():
    projection=object.__new__(SDKProjection);projection.read_only=True
    with pytest.raises(PermissionError,match='read-only projection cannot build'):
        asyncio.run(projection.build(None,None,None,1))

def test_native_readonly_acl_when_owned_fixture_available():
    import os
    from graphrag_sdk import ConnectionConfig,FalkorDBConnection
    url=os.environ.get('ORACLE2_TEST_READONLY_GRAPH_URL')
    if not url:pytest.fail('owned namespace-scoped native graph fixture required')
    graph_name=os.environ.get('ORACLE2_TEST_READONLY_GRAPH_NAME')
    other_name=os.environ.get('ORACLE2_TEST_READONLY_OTHER_GRAPH_NAME')
    assert graph_name and other_name,'sealed owned fixture graph identities required'
    async def check():
        native=FalkorDBConnection(ConnectionConfig.from_url(url,graph_name=graph_name,retry_count=1))
        try:
            ro=ReadOnlyConnection(native)
            assert (await ro.query('MATCH (n) RETURN count(n)')).result_set==[[1]]
            with pytest.raises(Exception):await native.query('CREATE (:Forbidden)')
            with pytest.raises(Exception):await ro.query('CREATE (:Forbidden)')
        finally:await native.close()
        other=FalkorDBConnection(ConnectionConfig.from_url(url,graph_name=other_name,retry_count=1))
        try:
            with pytest.raises(Exception):await ReadOnlyConnection(other).query('MATCH (n) RETURN count(n)')
        finally:await other.close()
    asyncio.run(check())
