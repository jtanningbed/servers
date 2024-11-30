# tests/test_neo4j_server.py

import pytest
import os
from datetime import datetime
from mcp_server_neo4j.server import Neo4jServer, EXAMPLE_SCHEMA
from mcp_server_neo4j.resources.schemas import (
    Facts,
    QueryParams,
    ConnectionParams,
    Fact,
    CypherQuery,
    SchemaDefinition,
    NodeLabelDefinition,
    PropertyType,
    RelationshipTypeDefinition,
    PropertyDefinition
)
from mcp_server_neo4j.validation.schema_validator import SchemaValidationError as ValidationError


@pytest.fixture
async def server():
    """Create and initialize a Neo4j server instance"""
    uri = "neo4j://localhost:7687"
    username = "neo4j"
    password = "testpassword"

    server = Neo4jServer()
    await server.initialize(uri, (username, password))
    yield server
    await server.shutdown()


@pytest.mark.asyncio
async def test_server_initialization(server):
    """Test server initialization and basic connectivity"""
    assert server.driver is not None
    assert server.resource_handler is not None

    # Test basic connectivity
    async with server.driver.session() as session:
        result = await session.run("RETURN 1 as test")
        data = await result.single()
        assert data["test"] == 1


@pytest.mark.asyncio
async def test_schema_setup(server):
    """Test schema setup and validation"""
    schema_response = await server.setup_schema(EXAMPLE_SCHEMA)

    # Check schema setup response
    assert len(schema_response.created_constraints) > 0
    assert len(schema_response.created_indexes) > 0
    assert len(schema_response.created_labels) > 0
    assert isinstance(schema_response.timestamp, datetime)

    # Verify schema was actually created
    async with server.driver.session() as session:
        # Check constraint
        result = await session.run("SHOW CONSTRAINTS")
        constraints = await result.data()
        assert any("entity_name" in constraint["name"] for constraint in constraints)

        # Check index
        result = await session.run("SHOW INDEXES")
        indexes = await result.data()
        assert any("type" in index["name"] for index in indexes)


@pytest.mark.asyncio
async def test_resource_listing(server):
    """Test resource listing functionality"""
    # Test resources
    resources = await server.resource_handler.list_resources()
    assert len(resources) > 0
    assert all(hasattr(r, "uri") for r in resources)
    assert all(hasattr(r, "description") for r in resources)

    # Test resource templates
    templates = await server.resource_handler.list_resource_templates()
    assert len(templates) > 0
    assert all(hasattr(t, "uri_template") for t in templates)


@pytest.mark.asyncio
async def test_core_tools(server):
    """Test core graph operation tools"""
    # Test store-facts
    facts = Facts(
        facts=[
            Fact(subject="Alice", predicate="KNOWS", object="Bob"),
            Fact(subject="Bob", predicate="WORKS_WITH", object="Charlie"),
        ]
    )
    result = await server.resource_handler.handle_call_tool(
        "store-facts", facts.model_dump()
    )
    assert len(result) == 1
    response = result[0]
    assert response.type == "text"

    # Test query-knowledge
    params = QueryParams(context=None)
    result = await server.resource_handler.handle_call_tool(
        "query-knowledge", params.model_dump()
    )
    assert len(result) == 1

    # Test find-connections
    params = ConnectionParams(concept_a="Alice", concept_b="Charlie", max_depth=2)
    result = await server.resource_handler.handle_call_tool(
        "find-connections", params.model_dump()
    )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_template_tools(server):
    """Test template-based tools"""
    # Test entity search template
    search_params = {
        "label": "Person",
        "property": "name",
        "operator": "=",
        "value": "Alice",
        "relationship_types": ["KNOWS", "WORKS_WITH"],
    }
    result = await server.resource_handler.handle_call_tool(
        "template.entity_search", search_params
    )
    assert len(result) == 1
    assert result[0].type == "text"

    # Test graph analytics template
    analytics_params = {"label": "Person", "limit": 10}
    result = await server.resource_handler.handle_call_tool(
        "template.graph_analytics", analytics_params
    )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_cypher_execution(server):
    """Test direct Cypher query execution"""
    query = CypherQuery(
        query="MATCH (n:Person) RETURN count(n) as count", parameters={}
    )
    result = await server.resource_handler.handle_call_tool(
        "execute-cypher", query.model_dump()
    )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_resource_reading(server):
    """Test resource reading functionality"""
    # Test schema resource
    schema_content = await server.resource_handler.read_resource("neo4j://schema/nodes")
    assert schema_content is not None

    # Test template resource
    template_content = await server.resource_handler.read_resource(
        "neo4j://templates/queries"
    )
    assert template_content is not None


@pytest.mark.asyncio
async def test_error_handling(server):
    """Test error handling in various scenarios"""
    # Test invalid tool
    with pytest.raises(ValueError):
        await server.resource_handler.handle_call_tool("invalid-tool", {})

    # Test invalid template
    with pytest.raises(ValueError):
        await server.resource_handler.handle_call_tool("template.invalid", {})

    # Test invalid parameters
    with pytest.raises(ValidationError):
        bad_facts = Facts(
            facts=[Fact(subject="", predicate="", object="")]  # Invalid empty values
        )
        await server.resource_handler.handle_call_tool(
            "store-facts", bad_facts.model_dump()
        )


@pytest.mark.asyncio
async def test_prompts(server):
    """Test prompt handling"""
    # List prompts
    prompts = await server.resource_handler.list_prompts()
    assert len(prompts) > 0

    # Get specific prompt
    result = await server.resource_handler.get_prompt(
        "graph-query", {"question": "Find all persons"}
    )
    assert result is not None
    assert len(result.messages) > 0


def test_schema_definition():
    """Test schema definition model"""
    schema = SchemaDefinition(
        node_labels=[
            NodeLabelDefinition(
                label="Person",
                description="A person node",
                properties=[
                    PropertyDefinition(
                        name="name",
                        type=PropertyType.STRING,
                        unique=True,  # Use unique instead of just required
                        indexed=True,
                        description="Person's name",
                    ),
                    PropertyDefinition(
                        name="age",
                        type=PropertyType.INTEGER,
                        indexed=True,
                        description="Person's age",
                    ),
                ],
            )
        ],
        relationship_types=[
            RelationshipTypeDefinition(
                type="KNOWS",
                source_labels=["Person"],
                target_labels=["Person"],
                properties=[
                    PropertyDefinition(
                        name="since",
                        type=PropertyType.DATETIME,
                        required=True,  # This is just for documentation now
                        description="When the relationship was established",
                    )
                ],
                description="Represents a connection between people",
            )
        ],
    )

    # Test node label structure
    assert len(schema.node_labels) == 1
    person_label = schema.node_labels[0]
    assert person_label.label == "Person"
    assert len(person_label.properties) == 2

    # Test property definitions
    name_prop = next(p for p in person_label.properties if p.name == "name")
    assert name_prop.type == PropertyType.STRING
    assert name_prop.unique is True
    assert name_prop.indexed is True

    age_prop = next(p for p in person_label.properties if p.name == "age")
    assert age_prop.type == PropertyType.INTEGER
    assert age_prop.indexed is True

    # Test relationship structure
    assert len(schema.relationship_types) == 1
    knows_rel = schema.relationship_types[0]
    assert knows_rel.type == "KNOWS"
    assert "Person" in knows_rel.source_labels
    assert "Person" in knows_rel.target_labels
    assert len(knows_rel.properties) == 1


async def clean_database(server):
    """Helper to clean the database between tests"""
    async with server.driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")


if __name__ == "__main__":
    pytest.main([__file__])
