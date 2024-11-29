# mcp-server-neo4j: A Neo4j MCP server

## Overview

A Model Context Protocol server for Neo4j graph database integration. This server provides tools to store, query, and analyze graph data via Large Language Models, making it ideal for knowledge graph management, relationship analysis, and graph-based RAG applications.

Please note that mcp-server-neo4j is currently in early development. The functionality and available tools are subject to change and expansion as we continue to develop and improve the server.

### Tools

1. `store-facts`
   - Stores facts in the knowledge graph as subject-predicate-object triples
   - Input:
     ```json
     {
       "context": "optional string context",
       "facts": [
         {
           "subject": "Entity1",
           "predicate": "RELATION_TYPE",
           "object": "Entity2"
         }
       ]
     }
     ```
   - Returns: Stored facts with metadata including context and creation time

2. `query-knowledge`
   - Queries relationships in the knowledge graph
   - Input:
     ```json
     {
       "context": "optional string to filter by context"
     }
     ```
   - Returns: List of relationships with their metadata

3. `find-connections`
   - Finds paths between two entities in the graph
   - Input:
     ```json
     {
       "concept_a": "starting entity",
       "concept_b": "target entity",
       "max_depth": "optional int (default: 3)"
     }
     ```
   - Returns: Paths found between the entities with relationship details

## Installation

### Using uv (recommended)

When using [`uv`](https://docs.astral.sh/uv/) no specific installation is needed. We will
use [`uvx`](https://docs.astral.sh/uv/guides/tools/) to directly run *mcp-server-neo4j*.

### Using PIP

Alternatively you can install `mcp-server-neo4j` via pip:

```bash
pip install mcp-server-neo4j
```

After installation, you can run it as a script using:

```bash
python -m mcp_server_neo4j
```

## Configuration

The server requires a running Neo4j instance. Connection details can be provided via environment variables:
- `NEO4J_URI` (default: "neo4j://localhost:7687")
- `NEO4J_USERNAME` (default: "neo4j")
- `NEO4J_PASSWORD` (default: "testpassword")

### Usage with Claude Desktop

Add this to your `claude_desktop_config.json`:

<details>
<summary>Using uvx</summary>

```json
"mcpServers": {
  "neo4j": {
    "command": "uvx",
    "args": ["mcp-server-neo4j"],
    "env": {
      "NEO4J_URI": "neo4j://localhost:7687",
      "NEO4J_USERNAME": "neo4j",
      "NEO4J_PASSWORD": "your-password"
    }
  }
}
```
</details>

<details>
<summary>Using pip installation</summary>

```json
"mcpServers": {
  "neo4j": {
    "command": "python",
    "args": ["-m", "mcp_server_neo4j"],
    "env": {
      "NEO4J_URI": "neo4j://localhost:7687",
      "NEO4J_USERNAME": "neo4j",
      "NEO4J_PASSWORD": "your-password"
    }
  }
}
```
</details>

### Usage with [Zed](https://github.com/zed-industries/zed)

Add to your Zed settings.json:

<details>
<summary>Using uvx</summary>

```json
"context_servers": [
  "mcp-server-neo4j": {
    "command": "uvx",
    "args": ["mcp-server-neo4j"],
    "env": {
      "NEO4J_URI": "neo4j://localhost:7687",
      "NEO4J_USERNAME": "neo4j",
      "NEO4J_PASSWORD": "your-password"
    }
  }
],
```
</details>

<details>
<summary>Using pip installation</summary>

```json
"context_servers": {
  "mcp-server-neo4j": {
    "command": "python",
    "args": ["-m", "mcp_server_neo4j"],
    "env": {
      "NEO4J_URI": "neo4j://localhost:7687",
      "NEO4J_USERNAME": "neo4j",
      "NEO4J_PASSWORD": "your-password"
    }
  }
},
```
</details>

## Debugging

You can use the MCP inspector to debug the server. For uvx installations:

```bash
npx @modelcontextprotocol/inspector uvx mcp-server-neo4j
```

Or if you've installed the package in a specific directory or are developing on it:

```bash
cd path/to/servers/src/neo4j
npx @modelcontextprotocol/inspector uv run mcp-server-neo4j
```

## Example Usage

Here's how an LLM might interact with the server:

1. Storing facts:
```python
# Store some knowledge
await store_facts({
  "context": "technology",
  "facts": [
    {
      "subject": "Python",
      "predicate": "IS_TYPE_OF",
      "object": "Programming Language"
    },
    {
      "subject": "Python",
      "predicate": "USED_FOR",
      "object": "Data Science"
    }
  ]
})
```

2. Querying relationships:
```python
# Query by context
await query_knowledge({
  "context": "technology"
})
```

3. Finding connections:
```python
# Find how entities are connected
await find_connections({
  "concept_a": "Python",
  "concept_b": "Data Science",
  "max_depth": 2
})
```

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.