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
    ReadResourceResult,
)
from mcp.server import Server
from pydantic import BaseModel, AnyUrl, field_validator
from neo4j import AsyncGraphDatabase, AsyncDriver
from dotenv import load_dotenv
import logging
import os
from .prompts import PROMPTS
from .resources import RESOURCES

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
            """
       MERGE (c:Context {name: $context})
       """,
            context=context
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
            return RESOURCES["contents"]

        @server.read_resource()
        async def read_resource(uri: AnyUrl) -> str | bytes:
            uri_str = str(uri)
            async with server.driver.session() as session:
                # Schema resources
                if uri_str == "neo4j://schema/nodes":
                    result = await session.run("""
                        CALL db.schema.nodeTypeProperties()
                        YIELD nodeType, propertyName, propertyTypes
                        RETURN collect({
                            label: nodeType,
                            property: propertyName,
                            types: propertyTypes
                        }) as schema
                    """)
                    return json.dumps(result)

                elif uri_str == "neo4j://schema/relationships":
                    result = await server.driver.run(
                        """
                        CALL db.schema.relationshipTypeProperties()
                        YIELD relationshipType, propertyName, propertyTypes
                        RETURN collect({
                            type: relationshipType,
                            property: propertyName,
                            types: propertyTypes
                        }) as schema
                    """
                    )
                    return json.dumps(result)

                elif uri_str == "neo4j://schema/indexes":
                    result = await session.run("""
                        SHOW INDEXES
                        YIELD name, labelsOrTypes, properties, type
                        RETURN collect({
                            name: name,
                            labels: labelsOrTypes,
                            properties: properties,
                            type: type
                        }) as indexes
                    """)
                    return json.dumps(result)

                # Query resources
                elif uri_str == "neo4j://queries/active":
                    result = await session.run(
                        """
                        SHOW TRANSACTIONS
                        YIELD transactionId, currentQueryId, currentQuery, status, elapsedTime
                        WHERE currentQueryId <> $currentQueryId
                        RETURN collect({
                            id: queryId,
                            query: query,
                            params: parameters,
                            runtime: runtime,
                            elapsedMs: elapsedTime
                        }) as queries
                    """,
                        {"currentQueryId": "current-query-id"},
                    )
                    return json.dumps(result)

                elif uri_str == "neo4j://queries/slow":
                    # Assuming we have a method to fetch slow query logs
                    logger.info("Not implemented yet.")
                    return ""

                # Statistics resources
                elif uri_str == "neo4j://stats/memory":
                    result = await session.run("""
                        CALL dbms.memory.detailed() 
                        YIELD name, bytes
                        RETURN collect({
                            name: name,
                            bytes: bytes
                        }) as memory
                    """)
                    return json.dumps(result)

                elif uri_str == "neo4j://stats/transactions":
                    result = await session.run("""
                        CALL dbms.queryStatistics()
                        YIELD activeTransactions, peakTransactions, 
                            totalTransactions, currentReadTransactions,
                            currentWriteTransactions
                        RETURN {
                            active: activeTransactions,
                            peak: peakTransactions,
                            total: totalTransactions,
                            currentRead: currentReadTransactions,
                            currentWrite: currentWriteTransactions
                        } as stats
                    """)
                    return json.dumps(result)

                # Template resources handling
                elif uri_str.startswith("neo4j://nodes/") and uri_str.endswith("/count"):
                    label = uri_str.split("/")[-2]
                    result = await session.run(
                        "MATCH (n:`" + label + "`) RETURN count(n) as count"
                    )
                    return str(result["count"])

                elif uri_str.startswith("neo4j://relationships/") and uri_str.endswith("/count"):
                    rel_type = uri_str.split("/")[-2]
                    result = await session.run(
                        "MATCH ()-[r:`" + rel_type + "`]->() RETURN count(r) as count"
                    )
                    return str(result["count"])

            raise ValueError(f"Resource not found: {uri_str}")

        async def _fetch_resource_content(uri: AnyUrl):
            """Fetch the content for a specific resource"""
            if uri == "neo4j://schema/nodes":
                # Query for node schema
                result = await self.graph_db.run("""
                    CALL db.schema.nodeTypeProperties()
                    YIELD nodeType, propertyName, propertyTypes
                    RETURN collect({
                        label: nodeType,
                        property: propertyName,
                        types: propertyTypes
                    }) as schema
                """)
                return result.json()

            elif uri.path == "schema/relationships":
                # Query for relationship schema
                result = await session.run("""
                    CALL db.schema.relationshipTypeProperties()
                    YIELD relationshipType, propertyName, propertyTypes
                    RETURN collect({
                        type: relationshipType,
                        property: propertyName,
                        types: propertyTypes
                    }) as schema
                """)
                return ReadResourceResult(contents=[await r.data() for r in result])

            elif uri.path == "schema/indexes":
                # Query for indexes
                result = await session.run("""
                    SHOW INDEXES
                    YIELD name, labelsOrTypes, properties, type
                    RETURN collect({
                        name: name,
                        labels: labelsOrTypes,
                        properties: properties,
                        type: type
                    }) as indexes
                """)
                return ReadResourceResult(contents=[await r.data() for r in result])

            elif uri.path == "queries/active":
                # Query for active queries
                result = await session.run("""
                    CALL dbms.listQueries()
                    YIELD queryId, query, parameters, runtime, elapsedTimeMillis
                    WHERE queryId <> $currentQueryId
                    RETURN collect({
                        id: queryId,
                        query: query,
                        params: parameters,
                        runtime: runtime,
                        elapsedMs: elapsedTimeMillis
                    }) as queries
                """, {"currentQueryId": "current-query-id"})
                return ReadResourceResult(contents=[await r.data() for r in result])

            elif str(uri).startswith("neo4j://nodes/"):
                # Handle node count template
                label = uri.split("/")[-2]
                result = await session.run(
                    "MATCH (n:`" + label + "`) RETURN count(n) as count"
                )
                return ReadResourceResult(contents=[str(result["count"])])

            elif str(uri).startswith("neo4j://relationships/"):
                # Handle relationship count template
                rel_type = uri.split("/")[-2]
                result = await session.run(
                    "MATCH ()-[r:`" + rel_type + "`]->() RETURN count(r) as count"
                )
                return ReadResourceResult(contents=[str(result["count"])])

            raise ValueError(f"Resource implementation not found: {uri}")

        @server.list_prompts()
        async def handle_list_prompts() -> list[Prompt]:
            """list available analysis prompts"""
            return list(PROMPTS.values())

        @server.get_prompt()
        async def handle_get_prompt(
            name: str, arguments: dict[str, str] | None
        ) -> GetPromptResult:
            """Get prompt details for graph analysis"""
            if name not in PROMPTS:
                raise ValueError(f"Unknown prompt: {name}")

            # Generate appropriate messages based on prompt type
            if prompt_name == "graph-query":
                question = arguments.get("question") if arguments else ""
                return GetPromptResult(
                    messages=[
                        PromptMessage(
                            role="system",
                            content=TextContent(
                                type="text",
                                text="You are a Neo4j expert that helps translate natural language questions into Cypher queries."
                            )
                        ),
                        PromptMessage(
                            role="user",
                            content=TextContent(
                                type="text",
                                text=f"Please create a Cypher query to answer this question: {question}"
                            )
                        )
                    ]
                )

            elif prompt_name == "relationship-analysis":
                max_depth = arguments.get("max_depth", 3)
                return GetPromptResult(
                    messages=[
                        PromptMessage(
                            role="system",
                            content=TextContent(
                                type="text",
                                text="You are a graph relationship analyst that helps understand connections between nodes."
                            )
                        ),
                        PromptMessage(
                            role="user",
                            content=TextContent(
                                type="text",
                                text=f"""Analyze the relationships between node {arguments['start_node']} 
                                        and node {arguments['end_node']} up to depth {max_depth}. 
                                        Consider all possible paths and relationship types."""
                            ) 
                        )   
                    ]
                )

            elif prompt_name == "schema-suggestion":
                focus_area = arguments.get("focus_area", "full schema")
                return GetPromptResult(
                    messages=[
                        PromptMessage(
                            role="system",
                            content=TextContent(
                                type="text",
                                text="You are a Neo4j schema optimization expert.",
                            ),
                        ),
                        PromptMessage(
                            role="user",
                            content=TextContent(
                                type="text",
                                text=f"Analyze the current schema patterns for {focus_area} and suggest optimizations considering:\n"
                                "1. Index usage\n"
                                "2. Relationship types and directions\n"
                                "3. Property placement\n"
                                "4. Query patterns",
                            ),
                        ),
                    ]
                )

            elif prompt_name == "query-optimization":
                return GetPromptResult(
                    messages=[
                        PromptMessage(
                            role="system",
                            content=TextContent(
                                type="text",
                                text="You are a Neo4j query optimization expert."
                            )
                        ),
                        PromptMessage(
                            role="user",
                            content=TextContent(
                                type="text",
                                text=f"""Analyze and optimize this Cypher query:\n\n{arguments['query']}\n\n
                                        Additional context: {arguments.get('context', 'No additional context provided')}\n\n
                                        Consider:\n
                                        1. Index usage\n
                                        2. Query pattern efficiency\n
                                        3. Memory usage\n
                                        4. Potential bottlenecks"""
                            )
                        )
                    ]
                )

            raise ValueError("Prompt implementation not found")

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
                    validated_args = input_model.model_validate(arguments or {})
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
