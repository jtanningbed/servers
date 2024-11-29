from typing import Any, Optional
from datetime import datetime
from mcp.types import (
    Resource,
    Prompt,
    PromptArgument,
    GetPromptResult,
    PromptMessage,
    TextContent,
    Tool,
)
from mcp.server import Server
from pydantic import BaseModel, AnyUrl, field_validator
from neo4j import AsyncGraphDatabase, AsyncDriver
from dotenv import load_dotenv
import logging
import os

load_dotenv()
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-server-neo4j")


# Input Models
class QueryParams(BaseModel):
    """Parameters for querying the knowledge graph"""
    context: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "examples": [{
                "context": "technology",
            }]
        }
    }


class ConnectionParams(BaseModel):
    """Parameters for finding connections between entities"""
    concept_a: str
    concept_b: str
    max_depth: int = 3

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "concept_a": "Alice",
                "concept_b": "Bob",
                "max_depth": 3
            }]
        }
    }


class Fact(BaseModel):
    """A single fact represented as a subject-predicate-object triple"""
    subject: str
    predicate: str
    object: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "subject": "Alice",
                    "predicate": "KNOWS",
                    "object": "Bob"
                },
                {
                    "subject": "Neural Networks",
                    "predicate": "IS_TYPE_OF",
                    "object": "Machine Learning"
                },
                {
                    "subject": "Python",
                    "predicate": "USED_FOR",
                    "object": "Data Science"
                }
            ]
        }
    }


class Facts(BaseModel):
    """A collection of facts with optional context"""
    context: Optional[str] = None
    facts: list[Fact]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "context": "tech_skills",
                    "facts": [
                        {
                            "subject": "Alice",
                            "predicate": "SKILLED_IN",
                            "object": "Python"
                        },
                        {
                            "subject": "Python",
                            "predicate": "USED_IN",
                            "object": "Data Science"
                        }
                    ]
                }
            ]
        }
    }


# Output Models
class Entity(BaseModel):
    name: str
    type: str
    observations: list[str] = []


class Relation(BaseModel):
    from_entity: Entity
    to_entity: Entity
    relation_type: str
    context: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "from_entity": {"name": "Alice", "type": "Person"},
                    "to_entity": {"name": "Bob", "type": "Person"},
                    "relation_type": "KNOWS",
                    "context": "social",
                    "created_at": "2024-01-01T00:00:00"
                }
            ]
        }
    }


class StoreFactsResponse(BaseModel):
    """Response from storing facts in the knowledge graph"""
    stored_facts: list[Fact]
    context: str
    total_stored: int
    created_at: datetime


class QueryResponse(BaseModel):
    """Response from querying the knowledge graph"""
    relations: list[Relation]
    context: Optional[str] = None
    total_found: int = 0


class Path(BaseModel):
    """A path between two entities"""
    entities: list[Entity]
    relations: list[Relation]
    length: int


class ConnectionResponse(BaseModel):
    """Response from finding connections between entities"""
    paths: list[Path]
    start_entity: str
    end_entity: str
    total_paths: int


SCHEMA_SETUP = [
    "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
    "CREATE INDEX type IF NOT EXISTS FOR (e:Entity) ON (e.type)"
]


class Neo4jServer(Server):
    def __init__(self):
        super().__init__("mcp-server-neo4j")
        self.driver: Optional[AsyncDriver] = None

    async def initialize(self, uri: str, auth: tuple):
        self.driver = AsyncGraphDatabase.driver(uri, auth=auth)
        logger.info("Driver initialized")

    async def shutdown(self):
        if self.driver:
            logger.info("Driver shutting down...")
            await self.driver.close()
            logger.info("Driver shutdown complete")

    async def format_response(self, response: BaseModel) -> TextContent:
        """Format a Pydantic model response as TextContent"""
        return TextContent(
            type="text",
            text=response.model_dump_json(indent=2)
        )
        
    async def format_error(self, error: Exception) -> TextContent:
        """Format an error as TextContent"""
        if isinstance(error, ValidationError):
            response = ValidationError(
                error="Validation Error",
                field=error.field,
                details=str(error)
            )
        else:
            response = Neo4jError(
                error=error.__class__.__name__,
                details=str(error)
            )
        return TextContent(
            type="text",
            text=response.model_dump_json(indent=2)
        )
        
    async def _ensure_context_schema(self, context: str, tx):
        """Ensure schema exists for given context"""
        await tx.run(
            f"""
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
                    created_at=(r["relation"]["created_at"].to_native() 
                              if hasattr(r["relation"]["created_at"], "to_native") 
                              else r["relation"]["created_at"]) if r["relation"]["created_at"] else None,
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
        params = {
            "concept_a": args.concept_a,
            "concept_b": args.concept_b
        }

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
                        r["created_at"] = (r["created_at"].to_native() 
                                         if hasattr(r["created_at"], "to_native") 
                                         else r["created_at"])
                    relations.append(Relation(**r))

                paths.append(
                    Path(
                        entities=entities,
                        relations=relations,
                        length=len(relations)
                    )
                )

            return ConnectionResponse(
                paths=paths,
                start_entity=args.concept_a,
                end_entity=args.concept_b,
                total_paths=len(paths),
            )


async def serve(uri: str = "neo4j://localhost:7687",
    username: str = "neo4j",
    password: str = "testpassword"
) -> None:
    """Initialize and serve the Neo4j MCP server"""
    logger.info("Starting Neo4j MCP Server...")

    server = Neo4jServer()
    try:
        # Initialize Neo4j driver
        await server.initialize(uri, (username, password))
        logger.info("Connected to Neo4j")

        # Initialize schema
        async with server.driver.session() as session:
            for statement in SCHEMA_SETUP:
                await session.run(statement)

        @server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """list available node types as resources"""
            logger = logging.getLogger(__name__)

            try:
                async with server.driver.session() as session:
                    # Query for all node labels
                    result = await session.run("""
                        MATCH (n)
                        WITH labels(n) as labels
                        UNWIND labels as label
                        RETURN DISTINCT label
                        ORDER BY label
                    """)

                    labels = await result.data()
                    logger.info(f"Found labels: {labels}")

                    if not labels:
                        logger.info("No labels found in database")
                        return []

                    return [
                        Resource(
                            uri=AnyUrl(f"neo4j://{label['label']}", scheme="neo4j"),
                            name=f"Node type: {label['label']}",
                            description=f"Access nodes of type {label['label']}",
                            mimeType="application/json",
                        )
                        for label in labels
                    ]
            except Exception as e:
                logger.error(f"Error listing resources: {e}")
                raise

        @server.read_resource()
        async def handle_read_resource(uri: AnyUrl) -> str:
            """Read nodes of a specific type"""
            if uri.scheme != "neo4j":
                raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

            label = uri.host
            async with server.driver.session() as session:
                result = await session.run(f"MATCH (n:{label}) RETURN n")
                nodes = await result.data()
            return str(nodes)

        @server.list_prompts()
        async def handle_list_prompts() -> list[Prompt]:
            """list available analysis prompts"""
            return [
                Prompt(
                    name="analyze-graph",
                    description="Analyze relationships in the knowledge graph",
                    arguments=[
                        PromptArgument(
                            name="context",
                            description="Optional context to filter analysis",
                            required=False,
                        )
                    ],
                )
            ]

        @server.get_prompt()
        async def handle_get_prompt(
            name: str, arguments: dict[str, str] | None
        ) -> GetPromptResult:
            """Get prompt details for graph analysis"""
            if name != "analyze-graph":
                raise ValueError(f"Unknown prompt: {name}")

            context = (arguments or {}).get("context", "")
            context_clause = f"WHERE r.context = '{context}'" if context else ""

            async with server.driver.session() as session:
                result = await session.run(
                    f"""
                    MATCH (n)-[r]->(m)
                    {context_clause}
                    RETURN n.name as source, type(r) as relationship, m.name as target
                    """
                )
                relationships = await result.data()

            return GetPromptResult(
                description="Analyze the knowledge graph structure",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"Analyze these relationships:\n{str(relationships)}",
                        ),
                    )
                ],
            )

        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available graph operation tools"""
            return [
                Tool(
                    name="store-facts",
                    description="""Store new facts in the knowledge graph. 
                    Facts are represented as subject-predicate-object triples,
                    optionally grouped under a context.""",
                    inputSchema=Facts.model_json_schema(),
                ),
                Tool(
                    name="query-knowledge",
                    description="Query relationships in the knowledge graph by context",
                    inputSchema=QueryParams.model_json_schema(),
                ),
                Tool(
                    name="find-connections",
                    description="Find paths between two entities in the knowledge graph",
                    inputSchema=ConnectionParams.model_json_schema(),
                ),
            ]

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
            """Handle tool invocation with proper response formatting"""
            try:
                tool_handlers = {
                    "store-facts": server._store_facts,
                    "query-knowledge": server._query_knowledge,
                    "find-connections": server._find_connections,
                }

                handler = tool_handlers.get(name)
                if not handler:
                    raise ValueError(f"Unknown tool: {name}")

                # Validate input
                model_map = {
                    "store-facts": Facts,
                    "query-knowledge": QueryParams,
                    "find-connections": ConnectionParams
                }

                input_model = model_map[name]
                try:
                    validated_args = input_model(**(arguments or {}))
                except ValidationError as e:
                    return [await server.format_error(e)]

                # Execute handler
                try:
                    result = await handler(validated_args)
                    return [await server.format_response(result)]
                except Exception as e:
                    logger.error(f"Tool execution error: {e}")
                    return [await server.format_error(e)]

            except Exception as e:
                logger.error(f"Unexpected error in tool handler: {e}")
                return [await server.format_error(e)]

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
