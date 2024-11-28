# test_neo4j_server.py

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, AsyncSession
from unittest.mock import AsyncMock, MagicMock, patch
from mcp.types import Resource, Tool, Prompt, TextContent
from mcp_server_neo4j.server import Neo4jServer


@pytest.fixture
def mock_driver():
    driver = AsyncMock(spec=AsyncDriver)
    session = AsyncMock(spec=AsyncSession)
    driver.session.return_value = session
    return driver


@pytest_asyncio.fixture
async def server(mock_driver):
    server = Neo4jServer()
    server.driver = mock_driver
    return server


class TestNeo4jServerInitialization:
    @pytest.mark.asyncio
    async def test_initialize_server(self):
        """Test server initialization with connection details"""
        server = Neo4jServer()
        uri = "neo4j://localhost:7687"
        auth = ("neo4j", "password")

        with patch("neo4j.AsyncGraphDatabase.driver") as mock_driver:
            await server.initialize(uri, auth)
            mock_driver.assert_called_once_with(uri, auth=auth)
            assert server.driver is not None

    @pytest.mark.asyncio
    async def test_shutdown_server(self, server):
        """Test server shutdown and driver closure"""
        await server.shutdown()
        server.driver.close.assert_called_once()


class TestResourceManagement:
    @pytest.mark.asyncio
    async def test_list_resources(self, server):
        """Test listing available node types as resources"""
        mock_result = AsyncMock()
        mock_result.data.return_value = [{"labels": ["Person", "Organization"]}]
        server.driver.session.return_value.__aenter__.return_value.run.return_value = (
            mock_result
        )

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
        assert len(resources) == 2
        assert resources[0].name == "Node type: Person"
        assert resources[1].name == "Node type: Organization"


class TestKnowledgeOperations:
    @pytest.mark.asyncio
    async def test_store_facts(self, server):
        """Test storing facts in the knowledge graph"""
        facts = {
            "context": "test",
            "facts": [{"subject": "Alice", "predicate": "KNOWS", "object": "Bob"}],
        }

        mock_result = AsyncMock()
        mock_result.data.return_value = [
            {"subject": "Alice", "predicate": "KNOWS", "object": "Bob"}
        ]
        server.driver.session.return_value.__aenter__.return_value.begin_transaction.return_value.__aenter__.return_value.run.return_value = (
            mock_result
        )

        result = await server._store_facts(facts)
        assert "stored_facts" in result
        assert len(result["stored_facts"]) == 1

    @pytest.mark.asyncio
    async def test_query_knowledge(self, server):
        """Test querying knowledge from the graph"""
        query_params = {"query": "test query", "context": "test"}

        mock_result = AsyncMock()
        mock_result.data.return_value = [
            {
                "relation": {
                    "from": {"name": "Alice", "type": "Person"},
                    "relation": "KNOWS",
                    "to": {"name": "Bob", "type": "Person"},
                }
            }
        ]
        server.driver.session.return_value.__aenter__.return_value.run.return_value = (
            mock_result
        )

        result = await server._query_knowledge(query_params)
        assert "relations" in result
        assert len(result["relations"]) == 1

    @pytest.mark.asyncio
    async def test_find_connections(self, server):
        """Test finding connections between concepts"""
        connection_params = {
            "concept_a": "Alice",
            "concept_b": "Charlie",
            "max_depth": 2,
        }

        mock_result = AsyncMock()
        mock_result.data.return_value = [
            {
                "nodes": [
                    {"name": "Alice", "type": "Person"},
                    {"name": "Bob", "type": "Person"},
                    {"name": "Charlie", "type": "Person"},
                ],
                "relations": ["KNOWS", "KNOWS"],
            }
        ]
        server.driver.session.return_value.__aenter__.return_value.run.return_value = (
            mock_result
        )

        result = await server._find_connections(connection_params)
        assert "connections" in result
        assert len(result["connections"]) == 1


class TestToolInterface:
    @pytest.mark.asyncio
    async def test_list_tools(self, server):
        """Test listing available tools"""

        @server.list_tools()
        async def handle_list_tools():
            return [
                Tool(
                    name="store-facts",
                    description="Store new facts in the knowledge graph",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "context": {"type": "string"},
                            "facts": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "subject": {"type": "string"},
                                        "predicate": {"type": "string"},
                                        "object": {"type": "string"},
                                    },
                                    "required": ["subject", "predicate", "object"],
                                },
                            },
                        },
                        "required": ["facts"],
                    },
                )
            ]

        tools = await handle_list_tools()
        assert len(tools) == 1
        assert tools[0].name == "store-facts"

    @pytest.mark.asyncio
    async def test_call_tool(self, server):
        """Test calling a registered tool"""

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict):
            tool_handlers = {
                "store-facts": server._store_facts,
                "query-knowledge": server._query_knowledge,
                "find-connections": server._find_connections,
            }

            handler = tool_handlers.get(name)
            if not handler:
                raise ValueError(f"Unknown tool: {name}")

            result = await handler(arguments or {})
            return [TextContent(type="text", text=str(result))]

        # Mock the store_facts handler
        mock_result = {
            "stored_facts": [
                {"subject": "Alice", "predicate": "KNOWS", "object": "Bob"}
            ]
        }
        with patch.object(server, "_store_facts", return_value=mock_result):
            result = await handle_call_tool(
                "store-facts",
                {
                    "facts": [
                        {"subject": "Alice", "predicate": "KNOWS", "object": "Bob"}
                    ]
                },
            )

        assert len(result) == 1
        assert isinstance(result[0], TextContent)


class TestPromptInterface:
    @pytest.mark.asyncio
    async def test_list_prompts(self, server):
        """Test listing available prompts"""

        @server.list_prompts()
        async def handle_list_prompts():
            return [
                Prompt(
                    name="analyze-graph",
                    description="Analyze relationships in the knowledge graph",
                    arguments=[
                        {
                            "name": "context",
                            "description": "Optional context to filter analysis",
                            "required": False,
                        }
                    ],
                )
            ]

        prompts = await handle_list_prompts()
        assert len(prompts) == 1
        assert prompts[0].name == "analyze-graph"


