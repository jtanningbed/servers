# test_integration.py

import pytest
import pytest_asyncio
from mcp_server_neo4j.server import Neo4jServer, StoreFactsResponse, QueryResponse, ConnectionResponse, Relation, Facts, Fact, ConnectionParams, QueryParams, Path
from mcp.types import Resource

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
        facts = Facts(
            context="test",
            facts=[
                Fact(subject="Alice", predicate="KNOWS", object="Bob"),
                Fact(subject="Bob", predicate="WORKS_WITH", object="Charlie"),
                Fact(subject="Charlie", predicate="REPORTS_TO", object="David"),
            ],
        )

        result = await server._store_facts(facts)
        assert isinstance(result, StoreFactsResponse)
        assert len(result.stored_facts) == 3

        # 2. Query knowledge
        query_result = await server._query_knowledge(
            QueryParams(query="test", context="test")
        )
        assert isinstance(query_result, QueryResponse)
        assert len(query_result.relations) == 3

        # 3. Find connections
        connections = await server._find_connections(
            ConnectionParams(concept_a="Alice", concept_b="David", max_depth=3)
        )

        assert isinstance(connections, ConnectionResponse)
        assert len(connections.paths) == 1
        path = connections.paths[0]
        assert isinstance(path, Path)
        assert len(path.entities) == 4  # Alice -> Bob -> Charlie -> David

    @pytest.mark.asyncio
    async def test_context_isolation(self, server, clean_database):
        """Test that different contexts don't interfere"""
        # Store facts in context A
        facts_a = Facts(
            context="context_a",
            facts=[Fact(subject="Alice", predicate="KNOWS", object="Bob")],
        )
        result_a_store = await server._store_facts(facts_a)
        assert isinstance(result_a_store, StoreFactsResponse)

        # Store facts in context B
        facts_b = Facts(
            context="context_b",
            facts=[Fact(subject="Charlie", predicate="KNOWS", object="David")],
        )
        result_b_store = await server._store_facts(facts_b)
        assert isinstance(result_b_store, StoreFactsResponse)

        # Query context A
        result_a = await server._query_knowledge(
            QueryParams(context="context_a")
        )
        assert isinstance(result_a, QueryResponse)
        assert len(result_a.relations) == 1
        assert isinstance(result_a.relations[0], Relation)
        assert result_a.relations[0].from_entity.name == "Alice"

        # Query context B
        result_b = await server._query_knowledge(
            QueryParams(context="context_b")
        )
        assert isinstance(result_b, QueryResponse)
        assert len(result_b.relations) == 1
        assert isinstance(result_b.relations[0], Relation)
        assert result_b.relations[0].from_entity.name == "Charlie"

    @pytest.mark.asyncio
    async def test_resource_listing(self, server, clean_database):
        """Test that resources are correctly listed after data is added"""
        # Add some data
        facts = Facts(
            context="test",
            facts=[Fact(subject="Alice", predicate="KNOWS", object="Bob")],
        )
        result = await server._store_facts(facts)
        assert isinstance(result, StoreFactsResponse)

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
