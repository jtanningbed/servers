# test_integration.py

import pytest
import pytest_asyncio
from mcp_server_neo4j.server import Neo4jServer


class TestNeo4jServerIntegration:
    @pytest_asyncio.fixture
    async def server(self, neo4j_connection):
        """Initialize server with real Neo4j connection"""
        server = Neo4jServer()
        server.driver = neo4j_connection
        return server

    @pytest.mark.asyncio
    async def test_full_knowledge_workflow(self, server, clean_database):
        """Test complete workflow of storing and querying knowledge"""
        # 1. Store facts
        facts = {
            "context": "test",
            "facts": [
                {"subject": "Alice", "predicate": "KNOWS", "object": "Bob"},
                {"subject": "Bob", "predicate": "WORKS_WITH", "object": "Charlie"},
                {"subject": "Charlie", "predicate": "REPORTS_TO", "object": "David"},
            ],
        }

        result = await server._store_facts(facts)
        assert len(result["stored_facts"]) == 3

        # 2. Query knowledge
        query_result = await server._query_knowledge(
            {"query": "test", "context": "test"}
        )
        assert len(query_result["relations"]) == 3

        # 3. Find connections
        connections = await server._find_connections(
            {"concept_a": "Alice", "concept_b": "David", "max_depth": 3}
        )

        assert len(connections["connections"]) == 1
        path = connections["connections"][0]
        assert len(path["entities"]) == 4  # Alice -> Bob -> Charlie -> David

    @pytest.mark.asyncio
    async def test_context_isolation(self, server, clean_database):
        """Test that different contexts don't interfere"""
        # Store facts in context A
        facts_a = {
            "context": "context_a",
            "facts": [{"subject": "Alice", "predicate": "KNOWS", "object": "Bob"}],
        }
        await server._store_facts(facts_a)

        # Store facts in context B
        facts_b = {
            "context": "context_b",
            "facts": [{"subject": "Charlie", "predicate": "KNOWS", "object": "David"}],
        }
        await server._store_facts(facts_b)

        # Query context A
        result_a = await server._query_knowledge(
            {"query": "test", "context": "context_a"}
        )
        assert len(result_a["relations"]) == 1
        assert result_a["relations"][0]["from_entity"] == "Alice"

        # Query context B
        result_b = await server._query_knowledge(
            {"query": "test", "context": "context_b"}
        )
        assert len(result_b["relations"]) == 1
        assert result_b["relations"][0]["from_entity"] == "Charlie"

    @pytest.mark.asyncio
    async def test_resource_listing(self, server, clean_database):
        """Test that resources are correctly listed after data is added"""
        # Add some data
        facts = {
            "context": "test",
            "facts": [{"subject": "Alice", "predicate": "KNOWS", "object": "Bob"}],
        }
        await server._store_facts(facts)

        # List resources
        @server.list_resources()
        async def handle_list_resources():
            async with server.driver.session() as session:
                result = await session.run(
                    "MATCH (n) RETURN DISTINCT labels(n) as labels"
                )
                labels = await result.data()
                return [
                    Resource(
                        uri=f"neo4j://{label}",
                        name=f"Node type: {label}",
                        description=f"Access nodes of type {label}",
                        mimeType="application/json",
                    )
                    for label_set in labels
                    for label in label_set["labels"]
                ]

        resources = await handle_list_resources()
        assert len(resources) > 0
        assert any(r.name == "Node type: Entity" for r in resources)
