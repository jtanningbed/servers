# tests/integration/test_neo4j_integration.py
import pytest
import asyncio
from datetime import datetime
from typing import AsyncGenerator
from mcp_server_neo4j.server import Neo4jServer


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def neo4j_server() -> AsyncGenerator[Neo4jServer, None]:
    """Create a server instance connected to test Neo4j database."""
    server = Neo4jServer()
    await server.initialize("neo4j://localhost:7687", ("neo4j", "testpassword"))
    yield server
    await server.shutdown()


@pytest.mark.integration
class TestNeo4jIntegration:
    @pytest.mark.asyncio
    async def test_basic_fact_workflow(self, neo4j_server):
        """Test storing and querying a simple fact."""
        # Store a fact
        store_result = await neo4j_server._store_facts(
            {"facts": ["Alice works at Acme"], "context": "test"}
        )
        assert "stored_facts" in store_result

        # Query the knowledge
        query_result = await neo4j_server._query_knowledge({"context": "test"})
        assert "relations" in query_result
        relations = query_result["relations"]
        assert len(relations) > 0
        assert any(r["from_entity"] == "Alice" for r in relations)

    @pytest.mark.asyncio
    async def test_multi_fact_connections(self, neo4j_server):
        """Test storing multiple related facts and finding connections."""
        # Store multiple related facts
        await neo4j_server._store_facts(
            {
                "facts": [
                    "Bob manages Engineering",
                    "Carol works in Engineering",
                    "Dave reports to Bob",
                ],
                "context": "org",
            }
        )

        # Find connections
        connections = await neo4j_server._find_connections(
            {"concept_a": "Carol", "concept_b": "Bob", "max_depth": 2}
        )

        assert "connections" in connections
        assert len(connections["connections"]) > 0
        # Verify we can find path between Carol and Bob through Engineering

    @pytest.mark.asyncio
    async def test_concurrent_access(self, neo4j_server):
        """Test concurrent fact storage and querying."""

        async def store_facts(facts, context):
            return await neo4j_server._store_facts({"facts": facts, "context": context})

        # Store facts concurrently
        tasks = [
            store_facts(["X" + str(i) + " knows Y" + str(i)], "concurrent")
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        assert all("stored_facts" in r for r in results)

        # Query all stored facts
        query_result = await neo4j_server._query_knowledge({"context": "concurrent"})
        assert len(query_result["relations"]) >= 5

    @pytest.mark.asyncio
    async def test_context_isolation(self, neo4j_server):
        """Test that different contexts don't interfere."""
        # Store facts in different contexts
        await neo4j_server._store_facts(
            {"facts": ["Alice likes pizza"], "context": "food"}
        )
        await neo4j_server._store_facts(
            {"facts": ["Alice writes code"], "context": "work"}
        )

        # Query each context separately
        food_result = await neo4j_server._query_knowledge({"context": "food"})
        work_result = await neo4j_server._query_knowledge({"context": "work"})

        assert len(food_result["relations"]) > 0
        assert len(work_result["relations"]) > 0
        assert food_result != work_result

    @pytest.mark.asyncio
    async def test_error_handling(self, neo4j_server):
        """Test error handling for various failure scenarios."""
        # Test invalid fact format
        with pytest.raises(Exception):
            await neo4j_server._store_facts(
                {"facts": ["Invalid fact without proper structure"], "context": "test"}
            )

        # Test connection interruption (would need to simulate Neo4j being down)
        # Test transaction rollback
        # Test timeout handling

    @pytest.mark.asyncio
    async def test_large_dataset(self, neo4j_server):
        """Test handling of larger datasets."""
        # Generate a larger set of facts
        large_facts = [f"User{i} follows User{i+1}" for i in range(100)]

        # Time the storage operation
        start_time = datetime.now()
        store_result = await neo4j_server._store_facts(
            {"facts": large_facts, "context": "large_test"}
        )
        duration = datetime.now() - start_time

        assert "stored_facts" in store_result
        assert duration.total_seconds() < 30  # Reasonable timeout

        # Test querying the large dataset
        query_result = await neo4j_server._query_knowledge({"context": "large_test"})
        assert len(query_result["relations"]) >= 100
