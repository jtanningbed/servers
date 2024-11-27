# tests/test_neo4j.py
import pytest
from pytest_asyncio import fixture
from unittest.mock import AsyncMock
from neo4j import AsyncGraphDatabase
from mcp_server_neo4j.server import Neo4jServer, Fact


@fixture
async def mock_result():
    result = AsyncMock()
    # Make data() return a normal value instead of a coroutine
    result.data = AsyncMock(
        return_value=[
            {
                "relation": {
                    "from": {"name": "Alice", "type": "Person"},
                    "relation": "KNOWS",
                    "to": {"name": "Bob", "type": "Person"},
                }
            }
        ]
    )
    return result


@fixture
async def mock_transaction(mock_result):
    tx = AsyncMock()
    # Make run() return our mock_result
    tx.run = AsyncMock(return_value=mock_result)
    tx.commit = AsyncMock()
    return tx


@fixture
async def mock_session(mock_transaction):
    session = AsyncMock()

    # Set up the context manager behavior
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    # Make begin_transaction() return our mock_transaction
    session.begin_transaction = AsyncMock(return_value=mock_transaction)
    return session


@fixture
async def mock_driver(mock_session):
    driver = AsyncMock()
    # Make session() return our mock_session
    driver.session = AsyncMock(return_value=mock_session)
    return driver


@fixture
async def server(mock_driver):
    server = Neo4jServer()
    server.driver = mock_driver
    yield server
    await server.shutdown()


@pytest.mark.asyncio
async def test_store_facts(server, mock_transaction, mock_result):
    # Set up specific return value for store_facts
    mock_result.data = AsyncMock(return_value=[{"stored": True}])

    result = await server._store_facts(
        {"facts": ["Alice knows Bob"], "context": "test"}
    )
    assert "stored_facts" in result


@pytest.mark.asyncio
async def test_query_knowledge(server, mock_transaction, mock_result):
    # Use default mock_result setup from fixture
    result = await server._query_knowledge({"query": "test query", "context": "test"})
    assert "relations" in result
    assert len(result["relations"]) > 0


@pytest.mark.asyncio
async def test_find_connections(server, mock_transaction, mock_result):
    # Set up specific return value for find_connections
    mock_result.data = AsyncMock(
        return_value=[
            {
                "nodes": [
                    {"name": "Alice", "type": "Person"},
                    {"name": "Bob", "type": "Person"},
                ],
                "relations": ["KNOWS"],
            }
        ]
    )

    result = await server._find_connections({"concept_a": "Alice", "concept_b": "Bob"})
    assert "connections" in result
    assert len(result["connections"]) > 0


@pytest.mark.asyncio
async def test_fact_validation():
    valid_fact = Fact(facts=["Alice knows Bob"], context="test")
    assert valid_fact.facts == ["Alice knows Bob"]
    assert valid_fact.context == "test"

    with pytest.raises(ValueError):
        Fact(facts=[])


@pytest.mark.asyncio
async def test_store_facts_validation(server):
    with pytest.raises(Exception):  # Adjust the exception type based on your validation
        await server._store_facts({})

    with pytest.raises(Exception):  # Adjust the exception type based on your validation
        await server._store_facts({"facts": []})
