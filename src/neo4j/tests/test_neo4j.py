# tests/test_neo4j_server.py
import pytest
from pytest_asyncio import fixture as async_fixture
from neo4j import AsyncGraphDatabase
from mcp_server_neo4j.server import Neo4jServer


@async_fixture
async def server():
    server = Neo4jServer()
    await server.initialize("neo4j://localhost:7687", ("neo4j", "testpassword"))
    yield server
    await server.shutdown()


@pytest.mark.asyncio
async def test_store_facts(server):
    result = await server._store_facts(
        {"facts": ["Alice knows Bob"], "context": "test"}
    )
    assert "stored_facts" in result
