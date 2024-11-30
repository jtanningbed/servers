from typing import Optional, List
from pydantic import BaseModel, AnyUrl
from datetime import datetime
from mcp.types import (
    Resource,
    ResourceTemplate,
    Prompt,
    GetPromptResult,
    PromptMessage,
    TextContent,
    Tool,
)
from mcp.server import Server
from neo4j import AsyncGraphDatabase, AsyncDriver
from dotenv import load_dotenv
import logging
import json
from .prompts import PROMPTS
from .resources import RESOURCES, RESOURCE_TEMPLATES
from .resources.schemas import (
    Facts,
    QueryParams,
    QueryResponse,
    ConnectionParams,
    ConnectionResponse,
    StoreFactsResponse,
    Relation,
    Fact,
    Entity, 
    Path,
    Neo4jError,
    ValidationError
)
from .queries import CypherQuery, QueryResponse as EnhancedQueryResponse
from .resources.schemas import (
    generate_schema_setup_queries,
    SchemaDefinition
)
from .resources.handlers import ResourceHandler
from .validation.schema_validator import SchemaValidator

load_dotenv()
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-server-neo4j")

EXAMPLE_SCHEMA = [
    "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
    "CREATE INDEX type IF NOT EXISTS FOR (e:Entity) ON (e.type)"
]
# server.py updates

from typing import Optional, List
from pydantic import BaseModel, AnyUrl
from datetime import datetime
from mcp.types import (
    Resource,
    ResourceTemplate,
    Prompt,
    GetPromptResult,
    PromptMessage,
    TextContent,
    Tool,
)
from mcp.server import Server
from neo4j import AsyncGraphDatabase, AsyncDriver
from .resources.schemas import (
    SchemaDefinition,
    SchemaSetupResponse,
    NodeLabelDefinition,
)
from .validation.schema_validator import SchemaValidator
from .tools.template_executor import TemplateExecutor


class Neo4jServer(Server):
    def __init__(self):
        super().__init__("mcp-server-neo4j")
        self.driver: Optional[AsyncDriver] = None
        self.resource_handler: Optional[ResourceHandler] = None

    async def initialize(self, uri: str, auth: tuple):
        """Initialize server components"""
        self.driver = AsyncGraphDatabase.driver(uri, auth=auth)

        # Initialize components
        schema_validator = SchemaValidator(self.driver)
        template_executor = TemplateExecutor(self.driver)

        # Initialize resource handler with components
        self.resource_handler = ResourceHandler(
            self.driver, schema_validator, template_executor
        )
        await self.resource_handler.initialize()

        logger.info("Server initialized")

    async def setup_schema(self, schema: SchemaDefinition) -> SchemaSetupResponse:
        """Set up the database schema"""
        return await self.resource_handler.setup_schema(schema)


async def serve(uri: str, username: str, password: str) -> None:
    """Initialize and serve the Neo4j MCP server"""
    logger.info("Starting Neo4j MCP Server...")

    server = Neo4jServer()
    try:
        # Initialize Neo4j driver
        await server.initialize(uri, (username, password))
        logger.info("Connected to Neo4j")

        # Set up schema with example definition
        schema_response = await server.setup_schema(EXAMPLE_SCHEMA)
        logger.info(f"Schema setup complete: {schema_response.model_dump_json()}")

        @server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """list available node types as resources"""
            return await server.resource_handler.list_resources()

        @server.list_resource_templates()
        async def handle_list_resource_templates() -> list[ResourceTemplate]:
            """list available resource templates"""
            return await server.resource_handler.list_resource_templates()

        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available graph operation tools"""
            return await server.resource_handler.list_tools()

        @server.read_resource()
        async def handle_read_resource(uri: AnyUrl) -> str | bytes:
            """ Read resource content"""
            uri_str = str(uri)
            return await server.resource_handler.read_resource(uri_str)

        @server.list_prompts()
        async def handle_list_prompts() -> list[Prompt]:
            """list available prompts"""
            return list(PROMPTS.values())

        @server.get_prompt()
        async def handle_get_prompt(
            name: str, arguments: dict[str, str] | None
        ) -> GetPromptResult:
            """Get prompt details for graph analysis"""
            return await server.resource_handler.get_prompt(name, arguments)

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
            """Handle tool invocation with proper response formatting"""
            return await server.resource_handler.handle_call_tool(name, arguments)


        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        await server.shutdown()
