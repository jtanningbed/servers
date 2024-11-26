#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { driver as createDriver, auth, Node as Neo4jNode, Relationship as Neo4jRelationship } from 'neo4j-driver';
import { zodToJsonSchema } from 'zod-to-json-schema';
import {
  ExecuteCypherSchema,
  CreateNodeSchema,
  CreateRelationshipSchema,
  GetNeighborsSchema,
  NodeSchema,
  RelationshipSchema,
  PathSchema,
  NodePropertiesSchema,
  RelationshipPropertiesSchema
} from './schemas.js';

// Initialize server
const server = new Server(
  {
    name: "neo4j-mcp-server",
    version: "0.1.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Initialize Neo4j connection
const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
const username = process.env.NEO4J_USERNAME || 'neo4j';
const password = process.env.NEO4J_PASSWORD;
const database = process.env.NEO4J_DATABASE || 'neo4j';

if (!password) {
  console.error("NEO4J_PASSWORD environment variable is required");
  process.exit(1);
}

const driver = createDriver(uri, auth.basic(username, password));

// Tool handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "execute_cypher",
      description: "Execute a Cypher query against the Neo4j database",
      inputSchema: zodToJsonSchema(ExecuteCypherSchema)
    },
    {
      name: "create_node",
      description: "Create a new node with labels and properties",
      inputSchema: zodToJsonSchema(CreateNodeSchema)
    },
    {
      name: "create_relationship",
      description: "Create a relationship between two nodes",
      inputSchema: zodToJsonSchema(CreateRelationshipSchema)
    },
    {
      name: "get_neighbors",
      description: "Get neighboring nodes of a given node",
      inputSchema: zodToJsonSchema(GetNeighborsSchema)
    }
  ]
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const session = driver.session({ database });
  try {
    const { name, arguments: args } = request.params;
    if (!args) throw new Error("Arguments are required");

    switch (name) {
      case "execute_cypher": {
        const params = ExecuteCypherSchema.parse(args);
        const result = await session.run(params.query, params.params);
        
        // Improved type handling for query results
        return {
          toolResult: result.records.map(record => {
            const resultObj: Record<string, unknown> = {};
            // Convert keys to string array before using them
            const keys = record.keys as string[];
            for (const key of keys) {
              const value = record.get(key);
              // Handle Neo4j node and relationship types
              if (value instanceof Neo4jNode) {
                resultObj[key] = NodeSchema.parse({
                  id: value.elementId,
                  labels: Array.from(value.labels),
                  properties: NodePropertiesSchema.parse(value.properties)
                });
              } else if (value instanceof Neo4jRelationship) {
                resultObj[key] = RelationshipSchema.parse({
                  id: value.elementId,
                  type: value.type,
                  fromNode: value.startNodeElementId,
                  toNode: value.endNodeElementId,
                  properties: RelationshipPropertiesSchema.parse(value.properties)
                });
              } else {
                resultObj[key] = value;
              }
            }
            return resultObj;
          })
        };
      }

      case "create_node": {
        const { labels, properties } = CreateNodeSchema.parse(args);
        // Validate properties against the schema before creating the node
        NodePropertiesSchema.parse(properties);
        
        const labelStr = labels.map(l => `:${l}`).join('');
        const propsStr = Object.entries(properties)
          .map(([k, v]) => `${k}: $${k}`)
          .join(', ');

        const query = `CREATE (n${labelStr} {${propsStr}}) RETURN n`;
        const result = await session.run(query, properties);
        const node = result.records[0].get('n');
        
        return { toolResult: NodeSchema.parse({
          id: node.elementId,
          labels: Array.from(node.labels),
          properties: NodePropertiesSchema.parse(node.properties)
        })};
      }

      case "create_relationship": {
        const { fromNode, toNode, type, properties = {} } = CreateRelationshipSchema.parse(args);
        // Validate properties against the schema before creating the relationship
        if (properties) {
          RelationshipPropertiesSchema.parse(properties);
        }

        const propsStr = Object.entries(properties)
          .map(([k, v]) => `${k}: $${k}`)
          .join(', ');

        const query = `
          MATCH (from), (to)
          WHERE elementId(from) = $fromId AND elementId(to) = $toId
          CREATE (from)-[r:${type} {${propsStr}}]->(to)
          RETURN r
        `;

        const result = await session.run(query, {
          fromId: fromNode,
          toId: toNode,
          ...properties
        });

        const rel = result.records[0].get('r');
        return { toolResult: RelationshipSchema.parse({
          id: rel.elementId,
          type: rel.type,
          fromNode: rel.startNodeElementId,
          toNode: rel.endNodeElementId,
          properties: properties ? RelationshipPropertiesSchema.parse(rel.properties) : {}
        })};
      }

      case "get_neighbors": {
        const { nodeId, direction, relationshipTypes = [], limit } = GetNeighborsSchema.parse(args);
        const relTypeStr = relationshipTypes.length
          ? `:${relationshipTypes.join('|')}`
          : '';

        let pattern: string;
        if (direction === 'incoming') {
          pattern = `(neighbor)-[${relTypeStr}]->(n)`;
        } else if (direction === 'outgoing') {
          pattern = `(n)-[${relTypeStr}]->(neighbor)`;
        } else {
          pattern = `(n)-[${relTypeStr}]-(neighbor)`;
        }

        const query = `
          MATCH ${pattern}
          WHERE elementId(n) = $nodeId
          RETURN DISTINCT neighbor
          ${limit ? `LIMIT ${limit}` : ''}
        `;

        const result = await session.run(query, { nodeId });
        return { 
          toolResult: result.records.map(record => {
            const node = record.get('neighbor');
            return NodeSchema.parse({
              id: node.elementId,
              labels: Array.from(node.labels),
              properties: NodePropertiesSchema.parse(node.properties)
            });
          })
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    console.error('Error in tool execution:', error);
    if (error instanceof Error) {
      throw new Error(`Tool execution failed: ${error.message}`);
    }
    throw error;
  } finally {
    await session.close();
  }
});

// Start server
async function main() {
  try {
    // Verify Neo4j connection
    await driver.verifyConnectivity();
    console.error('Successfully connected to Neo4j');

    // Start server
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('Neo4j MCP Server running on stdio');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

// Handle cleanup
process.on('SIGINT', async () => {
  console.error('Shutting down...');
  await driver.close();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.error('Shutting down...');
  await driver.close();
  process.exit(0);
});

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});