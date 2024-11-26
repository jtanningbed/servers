# Neo4j MCP Server

A Model Context Protocol server implementation for Neo4j graph database integration. This server enables LLMs to interact with Neo4j databases through a standardized interface, supporting graph operations, Cypher queries, and graph traversal.

## Features

- Direct Neo4j database connectivity
- Cypher query execution
- Node and relationship management
- Path finding and graph traversal
- Neighbor discovery

## Installation

```bash
# Using npm
npm install @modelcontextprotocol/server-neo4j

# Using yarn
yarn add @modelcontextprotocol/server-neo4j
```

## Usage

### Standalone Server

Run the server directly using npx:

```bash
npx -y @modelcontextprotocol/server-neo4j
```

### Environment Variables

The server requires the following environment variables:

- `NEO4J_URI`: Neo4j connection URI (default: `bolt://localhost:7687`)
- `NEO4J_USERNAME`: Neo4j database username (default: `neo4j`)
- `NEO4J_PASSWORD`: Neo4j database password (required)
- `NEO4J_DATABASE`: Neo4j database name (default: `neo4j`)

### Claude Desktop Integration

Add the following to your Claude Desktop configuration file:

```json
{
  "mcpServers": {
    "neo4j": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-neo4j"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "NEO4J_DATABASE": "neo4j"
      }
    }
  }
}
```

## Available Tools

### execute_cypher
Execute Cypher queries against the Neo4j database.
```typescript
{
  query: string;    // Cypher query to execute
  params?: object;  // Optional query parameters
}
```

### create_node
Create a new node with labels and properties.
```typescript
{
  labels: string[];           // Node labels
  properties: Record<string, any>;  // Node properties
}
```

### create_relationship
Create a relationship between two nodes.
```typescript
{
  fromNode: string;           // ID or reference of the source node
  toNode: string;             // ID or reference of the target node
  type: string;               // Relationship type
  properties?: Record<string, any>;  // Optional relationship properties
}
```

### find_paths
Find paths between two nodes in the graph.
```typescript
{
  fromNode: string;           // Starting node ID or reference
  toNode: string;             // Ending node ID or reference
  maxDepth?: number;          // Maximum path depth (default: 4)
  relationshipTypes?: string[];  // Filter by relationship types
}
```

### get_neighbors
Get neighboring nodes of a given node.
```typescript
{
  nodeId: string;             // Node ID or reference
  direction?: 'incoming' | 'outgoing' | 'both';  // Direction of relationships
  relationshipTypes?: string[];  // Filter by relationship types
  limit?: number;             // Maximum number of neighbors to return
}
```

## Example Usage

### Basic Query
```typescript
// Execute a Cypher query
const result = await client.executeCypher(
  "MATCH (n:Person) WHERE n.name = $name RETURN n",
  { name: "John" }
);
```

### Creating Nodes and Relationships
```typescript
// Create a person node
const person = await client.createNode(
  ["Person"],
  { name: "John", age: 30 }
);

// Create a company node
const company = await client.createNode(
  ["Company"],
  { name: "Acme Corp" }
);

// Create an employment relationship
await client.createRelationship(
  person.id,
  company.id,
  "WORKS_AT",
  { since: "2020" }
);
```

### Graph Traversal
```typescript
// Find paths between nodes
const paths = await client.findPaths(
  person1.id,
  person2.id,
  3,  // max depth
  ["KNOWS", "WORKS_AT"]  // relationship types
);

// Get neighbors
const coworkers = await client.getNeighbors(
  person.id,
  'both',
  ["WORKS_WITH"]
);
```

## Development

### Setup

1. Clone the repository:
```bash
git clone https://github.com/modelcontextprotocol/servers.git
cd servers/src/neo4j
```

2. Install dependencies:
```bash
npm install
```

3. Start Neo4j (Docker example):
```bash
docker run \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest
```

4. Build the project:
```bash
npm run build
```

### Testing

To test the server with the MCP Inspector:
```bash
npm run inspector
```

## Contributing

Contributions are welcome! Please read the [Contributing Guide](../../CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## Security

For details about our security policy and how to report security vulnerabilities, please read our [Security Policy](../../SECURITY.md).

## License

This project is licensed under the MIT License - see the [LICENSE](../../LICENSE) file for details.
