import os
from typing import List, Dict, Any, Optional
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Prompt,
    PromptArgument,
    GetPromptResult,
    PromptMessage,
    TextContent,
    Tool,
)
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from pydantic import BaseModel, AnyUrl
from neo4j import AsyncGraphDatabase, AsyncDriver


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


class Neo4jServer(Server):
    def __init__(self):
        super().__init__("mcp-server-neo4j")
        self.driver: Optional[AsyncDriver] = None

    async def initialize(self, uri: str, auth: tuple):
        self.driver = AsyncGraphDatabase.driver(uri, auth=auth)

    async def shutdown(self):
        if self.driver:
            await self.driver.close()

    async def _store_facts(self, args: Dict) -> Dict[str, Any]:
        params = Fact(**args)
        async with self.driver.session() as session:
            stored_facts = []
            for fact in params.facts:
                query = """
                CALL apoc.nlp.gcp.entities($fact) YIELD value
                WITH value.entities as entities
                WHERE size(entities) >= 2
                WITH entities[0] as subject, entities[-1] as object,
                     apoc.text.regexGroups($fact, '.*?\\s(\\w+)\\s.*')[0][1] as predicate
                MERGE (s:Entity {name: subject.text})
                MERGE (o:Entity {name: object.text})
                CREATE (s)-[r:RELATES {type: predicate, context: $context}]->(o)
                RETURN s.name as subject, r.type as predicate, o.name as object
                """
                result = await session.run(
                    query, {"fact": fact, "context": params.context}
                )
                stored_facts.extend(await result.data())

            await self.request_context.session.send_resource_list_changed()
            return {"stored_facts": stored_facts}

    async def _query_knowledge(self, args: Dict) -> Dict[str, Any]:
        params = KnowledgeQuery(**args)
        context_filter = "WHERE r.context = $context" if params.context else ""

        async with self.driver.session() as session:
            query = f"""
            MATCH p=()-[r]-()
            {context_filter}
            WITH p, relationships(p) as rels
            WHERE all(r in rels WHERE type(r) = 'RELATES')
            RETURN [n in nodes(p) | n.name] as entities,
                   [r in rels | r.type] as relationships
            """
            result = await session.run(query, {"context": params.context})
            paths = await result.data()

            return {
                "knowledge": [
                    f"{path['entities'][0]} {path['relationships'][0]} {path['entities'][1]}"
                    for path in paths
                ]
            }

    async def _find_connections(self, args: Dict) -> Dict[str, Any]:
        params = Connection(**args)
        async with self.driver.session() as session:
            query = """
            MATCH path = shortestPath(
                (a:Entity {name: $concept_a})-[*1..$max_depth]-(b:Entity {name: $concept_b})
            )
            RETURN [n in nodes(path) | n.name] as entities,
                   [r in relationships(path) | r.type] as relationships
            """
            result = await session.run(query, params.dict())
            paths = await result.data()

            return {
                "connections": [
                    " -> ".join(
                        [
                            f"{entities[i]} {relationships[i]}"
                            for i in range(len(path["relationships"]))
                        ]
                        + [path["entities"][-1]]
                    )
                    for path in paths
                ]
            }


async def serve(
    uri: str = "neo4j://localhost:7687",
    username: str = "neo4j",
    password: str = "password",
) -> None:
    server = Neo4jServer()
    await server.initialize(uri, (username, password))

    @server.list_resources()
    async def handle_list_resources(self) -> List[Resource]:
        async with self.driver.session() as session:
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
    async def handle_read_resource(self, uri: AnyUrl) -> str:
        if uri.scheme != "neo4j":
            raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

        label = uri.host
        async with self.driver.session() as session:
            result = await session.run(f"MATCH (n:{label}) RETURN n")
            nodes = await result.data()
        return str(nodes)

    @server.list_prompts()
    async def handle_list_prompts(self) -> List[Prompt]:
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
        self, name: str, arguments: Dict[str, str] | None
    ) -> GetPromptResult:
        if name != "analyze-graph":
            raise ValueError(f"Unknown prompt: {name}")

        context = (arguments or {}).get("context", "")
        context_clause = f"WHERE r.context = '{context}'" if context else ""

        async with self.driver.session() as session:
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
    async def handle_list_tools(self) -> List[Tool]:
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
        self, name: str, arguments: Dict | None
    ) -> List[TextContent]:
        tool_handlers = {
            "store-facts": self._store_facts,
            "query-knowledge": self._query_knowledge,
            "find-connections": self._find_connections,
        }

        handler = tool_handlers.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")

        result = await handler(arguments or {})
        return [TextContent(type="text", text=str(result))]


server = Neo4jServer()
options = server.create_initialization_options()
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            options
        )


if __name__ == "__main__":
    import asyncio
    import os

    asyncio.run(
        serve(
            uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password"),
        )
    )
