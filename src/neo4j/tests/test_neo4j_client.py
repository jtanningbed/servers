# test_neo4j_client.py
import asyncio
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

params = StdioServerParameters(
    command="uv",
    args=[
        "--directory",
        "/Users/jason/Development/tools/servers/src/neo4j/",
        "run",
        "mcp-server-neo4j"
    ]
)

async def test_neo4j_server():
    async with stdio_client(params) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
        # Store facts
        store_result = await session.call_tool(
            "store-facts",
            {"facts": ["Alice works at Acme", "Bob knows Alice"], "context": "test"},
        )
        print("Store result:", store_result)

        # Query knowledge
        query_result = await session.call_tool("query-knowledge", {"context": "test"})
        print("Query result:", query_result)

        # Find connections
        connection_result = await session.call_tool(
            "find-connections", {"concept_a": "Alice", "concept_b": "Acme"}
        )
        print("Connection result:", connection_result)


if __name__ == "__main__":
    asyncio.run(test_neo4j_server())
