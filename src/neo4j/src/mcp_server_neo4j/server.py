from typing import List, Dict, Any, Optional
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
from pydantic import BaseModel, AnyUrl
from neo4j import AsyncGraphDatabase, AsyncDriver
from dotenv import load_dotenv
import logging
import os
from enum import Enum

load_dotenv()
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-server-neo4j")

class Fact(BaseModel):
    context: Optional[str]
    facts: List[str]


class Connection(BaseModel):
    concept_a: str
    concept_b: str
    max_depth: Optional[int] = 3


class KnowledgeQuery(BaseModel):
    query: str
    context: Optional[str] = None


class Entity(BaseModel):
    name: str
    type: str
    observations: List[str] = []


class Relation(BaseModel):
    from_entity: str
    to_entity: str
    relation_type: str


class NLPProvider(Enum):
    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"
    OPENAI = "openai"
    SPACY = "spacy"


SCHEMA_SETUP = """
CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE;
CREATE INDEX type IF NOT EXISTS FOR (e:Entity) ON (e.type);
"""

class Neo4jServer(Server):
    def __init__(self):
        # print(f'Neo4jServer.__init__')
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

    async def _ensure_context_schema(self, context: str, tx):
        """Ensure schema exists for given context"""
        await tx.run(f"""
       MERGE (c:Context {{name: $context}})
       """, context=context)

    async def _store_facts(self, args: Dict) -> Dict[str, Any]:
        params = Fact(**args)
        context = params.context or "default"
        stored_facts = []

        async with self.driver.session() as session:
            async with await session.begin_transaction() as tx:
                await self._ensure_context_schema(context, tx)

                for fact in params.facts:
                    subject, predicate, object = await self._extract_fact(fact, tx)

                    query = """
                    MERGE (s:Entity {name: $subject})
                    ON CREATE SET s.type = $type
                    MERGE (o:Entity {name: $object}) 
                    ON CREATE SET o.type = $type
                    """

                    result = await tx.run(query, {
                       "subject": subject,
                       "predicate": predicate,
                       "object": object,
                       "context": context
                   })
                    stored_facts.extend(await result.data())

                await tx.commit()

        return {"stored_facts": stored_facts}

    async def _query_knowledge(self, args: Dict) -> Dict[str, Any]:
        params = KnowledgeQuery(**args)
        context_filter = "WHERE r.context = $context" if params.context else ""

        query = f"""
        MATCH p=(s:Entity)-[r:RELATES]->(o:Entity)
        {context_filter}
        RETURN {{
            from: {{ name: s.name, type: s.type }},
            relation: r.type,
            to: {{ name: o.name, type: o.type }}
        }} as relation
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"context": params.context})
            data = await result.data()

            # Convert to validated models
            relations = [
                Relation(
                    from_entity=r["relation"]["from"]["name"],
                    to_entity=r["relation"]["to"]["name"],
                    relation_type=r["relation"]["relation"],
                )
                for r in data
            ]

            return {"relations": [r.model_dump() for r in relations]}

    async def _find_connections(self, args: Dict) -> Dict[str, Any]:
        params = Connection(**args)

        # Validate entities exist
        for name in [params.concept_a, params.concept_b]:
            entity = Entity(name=name, type="concept")

        query = """
        MATCH path = shortestPath(
            (a:Entity {name: $concept_a})-[r:RELATION*1..$max_depth]-(b:Entity {name: $concept_b})
        )
        RETURN [n in nodes(path) | {name: n.name, type: n.type}] as nodes,
               [r in relationships(path) | r.type] as relations
        """

        async with self.driver.session() as session:
            result = await session.run(query, params.dict())
            paths = await result.data()

            connections = []
            for path in paths:
                path_entities = [Entity(**node) for node in path["nodes"]]
                path_relations = [
                    Relation(from_entity=e1.name, to_entity=e2.name, relation_type=rel)
                    for e1, e2, rel in zip(
                        path_entities[:-1], path_entities[1:], path["relations"]
                    )
                ]
                connections.append(
                    {
                        "entities": [e.model_dump() for e in path_entities],
                        "relations": [r.model_dump() for r in path_relations],
                    }
                )

            return {"connections": connections}


    async def _extract_fact(
        self, fact: str, tx, provider: Optional[NLPProvider] = None
    ) -> tuple[str, str, str]:
        """Extract subject, predicate, object from fact using specified or available NLP provider"""

        if provider and provider != NLPProvider.SPACY:
            # Use specified provider
            query = f"""
            CALL apoc.nlp.{provider.value}.entities($fact) YIELD value
            WITH value.entities as entities
            WHERE size(entities) >= 2
            WITH entities[0] as subject, entities[-1] as object,
                apoc.text.regexGroups($fact, '.*?\\s(\\w+)\\s.*')[0][1] as predicate
            RETURN subject.text as subject, predicate, object.text as object
            """
        elif provider == NLPProvider.SPACY or not provider:
            # Use spaCy or fallback to it if no provider specified
            query = """
            CALL custom.nlp.spacy.entities($fact) YIELD value
            WITH value.entities as entities
            WHERE size(entities) >= 2
            WITH entities[0] as subject, entities[-1] as object,
                apoc.text.regexGroups($fact, '.*?\\s(\\w+)\\s.*')[0][1] as predicate
            RETURN subject.text as subject, predicate, object.text as object
            """

        result = await tx.run(query, {"fact": fact})
        data = await result.single()
        return data["subject"], data["predicate"], data["object"]


async def serve() -> None:

    uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    username=os.getenv("NEO4J_USERNAME", "neo4j")
    password=os.getenv("NEO4J_PASSWORD", "testpassword")

    server = Neo4jServer()
    await server.initialize(uri, (username, password))
    logger.info("Server initialized")

    try: 
        @server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            async with server.driver.session() as session:
                result = await session.run("MATCH (n) RETURN DISTINCT labels(n) as labels")
                labels = await result.data()

            return [
                Resource(
                    uri=AnyUrl(f"neo4j://{label}"),
                    name=f"Node type: {label}",
                    description=f"Access nodes of type {label}",
                    mimeType="application/json",
                )
                for label_set in labels
                for label in label_set["labels"]
            ]

        @server.read_resource()
        async def handle_read_resource(uri: AnyUrl) -> str:
            if uri.scheme != "neo4j":
                raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

            label = uri.host
            async with server.driver.session() as session:
                result = await session.run(f"MATCH (n:{label}) RETURN n")
                nodes = await result.data()
            return str(nodes)

        @server.list_prompts()
        async def handle_list_prompts() -> List[Prompt]:
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
            name: str, arguments: Dict[str, str] | None
        ) -> GetPromptResult:
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
        async def handle_list_tools() -> List[Tool]:
            return [
                Tool(
                    name="store-facts",
                    description="Store new facts in the knowledge graph",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "context": {"type": "string"},
                            "facts": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["facts"],
                    },
                ),
                Tool(
                    name="query-knowledge",
                    description="Query the knowledge graph",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "context": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="find-connections",
                    description="Find connections between concepts",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "concept_a": {"type": "string"},
                            "concept_b": {"type": "string"},
                            "max_depth": {"type": "integer", "default": 3},
                        },
                        "required": ["concept_a", "concept_b"],
                    },
                ),
            ]

        @server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict | None
        ) -> List[TextContent]:
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

        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )
    finally:
        await server.shutdown()
