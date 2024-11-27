# tests/test_neo4j.py
import pytest
from pytest_asyncio import fixture
from unittest.mock import AsyncMock
from neo4j import AsyncGraphDatabase
from mcp_server_neo4j.server import Neo4jServer, Fact


@fixture
async def mock_result():
    """Mock a Neo4j result with async data() method"""
    result = AsyncMock()
    # Make data() return a value when awaited
    result.data.return_value = [
        {
            "relation": {
                "from": {"name": "Alice", "type": "Person"},
                "relation": "KNOWS",
                "to": {"name": "Bob", "type": "Person"},
            }
        }
    ]
    return result


@fixture
async def mock_transaction(mock_result):
    """Mock a Neo4j transaction with async run() method"""
    tx = AsyncMock()
    # Make run() return our mock_result when awaited
    tx.run.return_value = mock_result
    return tx


@fixture
async def mock_session(mock_transaction):
    class MockAsyncSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, tb):
            pass

        async def begin_transaction(self):  # Keep it async
            class TransactionContextManager:
                async def __aenter__(self):
                    return mock_transaction

                async def __aexit__(self, exc_type, exc_val, tb):
                    pass

            return TransactionContextManager()

        async def run(self, *args, **kwargs):
            return await mock_transaction.run(*args, **kwargs)

    return MockAsyncSession()


@fixture
async def mock_driver(mock_session):
    """Mock a Neo4j driver with sync session() and async close()"""

    class MockDriver:
        def __init__(self, session):
            self._session = session

        def session(self):
            # session() is synchronous
            return self._session

        async def close(self):
            # close() is async
            pass

    return MockDriver(mock_session)


@fixture
async def server(mock_driver):
    """Set up server with mock driver"""
    server = Neo4jServer()
    server.driver = mock_driver
    yield server
    await server.shutdown()


@pytest.mark.asyncio
async def test_store_facts(server, mock_transaction, mock_result):
    # Configure specific result for store_facts
    mock_result.data.return_value = [{"stored": True}]

    result = await server._store_facts(
        {"facts": ["Alice knows Bob"], "context": "test"}
    )
    assert "stored_facts" in result
    assert len(result["stored_facts"]) == 1


@pytest.mark.asyncio
async def test_query_knowledge(server, mock_transaction, mock_result):
    # Uses default mock_result setup from fixture
    result = await server._query_knowledge({"query": "test query", "context": "test"})
    assert "relations" in result
    assert len(result["relations"]) > 0


@pytest.mark.asyncio
async def test_find_connections(server, mock_transaction, mock_result):
    # Configure specific result for find_connections
    mock_result.data.return_value = [
        {
            "nodes": [
                {"name": "Alice", "type": "Person"},
                {"name": "Bob", "type": "Person"},
            ],
            "relations": ["KNOWS"],
        }
    ]

    result = await server._find_connections({"concept_a": "Alice", "concept_b": "Bob"})
    assert "connections" in result
    assert len(result["connections"]) > 0


@pytest.mark.asyncio
async def test_store_facts_validation(server):
    with pytest.raises(Exception):
        await server._store_facts({})

    with pytest.raises(Exception):
        await server._store_facts({"facts": []})


# Optional: Helper to verify our mock structure
@pytest.mark.asyncio
async def test_mock_structure(mock_driver):
    """Test that our mock hierarchy works as expected"""
    session = mock_driver.session()
    async with session as s:
        async with await s.begin_transaction() as tx:
            result = await tx.run("TEST")
            data = await result.data()
            assert isinstance(data, list)
