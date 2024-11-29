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
from .schemas import (
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
class Neo4jServer(Server):
    def __init__(self):
        super().__init__("mcp-server-neo4j")
        self.driver: Optional[AsyncDriver] = None
        self.resource_handler: Optional[ResourceHandler] = None

    async def initialize(self, uri: str, auth: tuple):
        self.driver = AsyncGraphDatabase.driver(uri, auth=auth)
        self.resource_handler = ResourceHandler(self.driver)
        logger.info("Driver and handlers initialized")

    async def shutdown(self):
        if self.driver:
            logger.info("Driver shutting down...")
            await self.driver.close()
            logger.info("Driver shutdown complete")

    async def format_response(self, response: BaseModel) -> TextContent:
        """Format a Pydantic model response as TextContent"""
        return TextContent(type="text", text=response.model_dump_json(indent=2))

    async def format_error(self, error: Exception) -> TextContent:
        """Format an error as TextContent"""
        if isinstance(error, ValidationError):
            response = ValidationError(
                error="Validation Error", field=error.field, details=str(error)
            )
        else:
            response = Neo4jError(error=error.__class__.__name__, details=str(error))
        return TextContent(type="text", text=response.model_dump_json(indent=2))

    async def setup_schema(self, schema: SchemaDefinition) -> SchemaSetupResponse:
        """Set up the database schema based on the provided definition"""
        self.schema = schema
        setup_queries = await generate_schema_setup_queries(schema)
        response = SchemaSetupResponse()

        async with self.driver.session() as session:
            for query in setup_queries:
                try:
                    await session.run(query)
                    if "CONSTRAINT" in query:
                        response.created_constraints.append(query)
                    elif "INDEX" in query:
                        response.created_indexes.append(query)
                except Exception as e:
                    response.warnings.append(f"Error executing {query}: {str(e)}")

        # Create label nodes
        async with self.driver.session() as session:
            for label_def in schema.node_labels:
                try:
                    query = f"""
                    MERGE (l:NodeLabel {{name: $name}})
                    SET l.description = $description
                    """
                    await session.run(query, {
                        "name": label_def.label,
                        "description": label_def.description
                    })
                    response.created_labels.append(label_def.label)
                except Exception as e:
                    response.warnings.append(f"Error creating label node {label_def.label}: {str(e)}")

        return response

    async def execute_cypher(self, query: CypherQuery) -> EnhancedQueryResponse:
        """Execute a Cypher query with parameter binding"""
        async with self.driver.session() as session:
            try:
                result = await session.run(query.query, query.parameters or {})
                data = await result.data()

                # Get query plan if available
                plan = None
                try:
                    plan_result = await session.run(f"EXPLAIN {query.query}")
                    plan = await plan_result.consume()
                    plan = {
                        "args": plan.plan["args"],
                        "identifiers": plan.plan["identifiers"],
                        "operatorType": plan.plan["operatorType"]
                    }
                except:
                    pass  # Ignore plan errors

                return EnhancedQueryResponse(
                    results=data,
                    total_results=len(data),
                    query_details={"plan": plan} if plan else None,
                    timestamp=datetime.now()
                )
            except Exception as e:
                logger.error(f"Query execution error: {str(e)}")
                raise

    async def _ensure_context_schema(self, context: str, tx):
        """Ensure schema exists for given context"""
        await tx.run(
            """
       MERGE (c:Context {name: $context})
       """,
            context=context,
        )

    async def _store_facts(self, args: Facts) -> StoreFactsResponse:
        """Store facts in the knowledge graph.

        Args:
            args: Facts model containing:
                - context (optional): Context to store facts under
                - facts: list[Fact] of facts to store

        Returns:
            StoreFactsResponse object containing:
                - stored_facts: list[Fact] of stored fact metadata
                - context: The context used
                - total_stored: Number of facts stored
                - created_at: Datetime of when the facts were stored
        """
        context = args.context if args.context is not None else "default"
        created_at = datetime.now()
        stored_facts: list[Fact] = []

        async with self.driver.session() as session:
            async with await session.begin_transaction() as tx:
                await self._ensure_context_schema(context, tx)

                for fact in args.facts:
                    query = """
                    MERGE (s:Entity {name: $subject})
                    MERGE (o:Entity {name: $object})
                    CREATE (s)-[r:RELATES {
                        type: $predicate,
                        context: $context,
                        created_at: datetime()
                    }]->(o)
                    RETURN {
                        subject: s.name,
                        predicate: r.type,
                        object: o.name
                    } as fact
                    """

                    result = await tx.run(
                        query,
                        {
                            "subject": fact.subject,
                            "predicate": fact.predicate,
                            "object": fact.object,
                            "context": context,
                        },
                    )

                    fact_data = await result.single()
                    if fact_data:
                        stored_facts.append(
                            Fact(
                                subject=fact_data["fact"]["subject"],
                                predicate=fact_data["fact"]["predicate"],
                                object=fact_data["fact"]["object"],
                            )
                        )

                await tx.commit()

        return StoreFactsResponse(
            stored_facts=stored_facts,
            context=context,
            total_stored=len(stored_facts),
            created_at=created_at,
        )

    async def _query_knowledge(self, args: QueryParams) -> QueryResponse:
        """Query relationships in the knowledge graph"""
        context_filter = "WHERE r.context = $context" if args.context else ""

        query = f"""
        MATCH p=(s:Entity)-[r:RELATES]->(o:Entity)
        {context_filter}
        RETURN {{
            from_entity: {{ 
                name: s.name, 
                type: coalesce(s.type, 'Entity') 
            }},
            to_entity: {{ 
                name: o.name, 
                type: coalesce(o.type, 'Entity') 
            }},
            relation_type: r.type,
            context: r.context,
            created_at: r.created_at
        }} as relation
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"context": args.context})
            data = await result.data()

            relations = [
                Relation(
                    from_entity=Entity(**r["relation"]["from_entity"]),
                    to_entity=Entity(**r["relation"]["to_entity"]),
                    relation_type=r["relation"]["relation_type"],
                    context=r["relation"]["context"],
                    created_at=(
                        (
                            r["relation"]["created_at"].to_native()
                            if hasattr(r["relation"]["created_at"], "to_native")
                            else r["relation"]["created_at"]
                        )
                        if r["relation"]["created_at"]
                        else None
                    ),
                )
                for r in data
            ]

            return QueryResponse(
                relations=relations, context=args.context, total_found=len(relations)
            )

    async def _find_connections(self, args: ConnectionParams) -> ConnectionResponse:
        """Find paths between two entities in the knowledge graph"""
        # We need to interpolate max_depth directly since it can't be a parameter in shortestPath
        query = f"""
        MATCH path = shortestPath(
            (a:Entity {{name: $concept_a}})-[r:RELATES*1..{args.max_depth}]-(b:Entity {{name: $concept_b}})
        )
        RETURN {{
            entities: [n in nodes(path) | {{
                name: n.name,
                type: coalesce(n.type, 'Entity')
            }}],
            relations: [r in relationships(path) | {{
                relation_type: r.type,
                context: r.context,
                created_at: r.created_at,
                from_entity: {{
                    name: startNode(r).name,
                    type: coalesce(startNode(r).type, 'Entity')
                }},
                to_entity: {{
                    name: endNode(r).name,
                    type: coalesce(endNode(r).type, 'Entity')
                }}
            }}]
        }} as path
        """

        # Remove max_depth from parameters since it's now in the query string
        params = {"concept_a": args.concept_a, "concept_b": args.concept_b}

        async with self.driver.session() as session:
            result = await session.run(query, params)
            paths_data = await result.data()

            paths = []
            for p in paths_data:
                path_data = p["path"]
                entities = [Entity(**e) for e in path_data["entities"]]
                relations = []
                for r in path_data["relations"]:
                    # Convert Neo4j DateTime to Python datetime if needed
                    if r["created_at"]:
                        r["created_at"] = (
                            r["created_at"].to_native()
                            if hasattr(r["created_at"], "to_native")
                            else r["created_at"]
                        )
                    relations.append(Relation(**r))

                paths.append(
                    Path(entities=entities, relations=relations, length=len(relations))
                )

            return ConnectionResponse(
                paths=paths,
                start_entity=args.concept_a,
                end_entity=args.concept_b,
                total_paths=len(paths),
            )


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
