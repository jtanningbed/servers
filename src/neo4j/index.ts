#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { driver as createDriver, auth, Node as Neo4jNode, Relationship as Neo4jRelationship } from 'neo4j-driver';
import { z } from 'zod';
import { zodToJsonSchema } from 'zod-to-json-schema';
import {
  ExecuteCypherSchema,
  CreateNodeSchema,
  CreateRelationshipSchema,
  GetNeighborsSchema,
  NodeSchema,
  RelationshipSchema,
  PathSchema,
  FindPathSchema,
  NodePropertiesSchema,
  RelationshipPropertiesSchema,
  type Node,
  type Relationship,
  type Path
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
    }
  }
);

// Initialize Neo4j connection
const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
const username = process.env.NEO4J_USERNAME || 'neo4j';
const password = process.env.NEO4J_PASSWORD || 'testpassword';
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
      schema: zodToJsonSchema(ExecuteCypherSchema)
    },
    {
      name: "create_node",
      description: "Create a new node with labels and properties",
      schema: zodToJsonSchema(CreateNodeSchema)
    },
    {
      name: "create_relationship",
      description: "Create a relationship between two nodes",
      schema: zodToJsonSchema(CreateRelationshipSchema)
    },
    {
      name: "get_neighbors",
      description: "Get neighboring nodes of a given node",
      schema: zodToJsonSchema(GetNeighborsSchema)
    },
    {
      name: "find_path",
      description: "Find paths between two nodes",
      schema: zodToJsonSchema(FindPathSchema)
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
        const params = ExecuteCypherSchema.parse(args) as z.infer<typeof ExecuteCypherSchema>;
        const result = await session.run(params.query, params.parameters || {});
        
        // Improved type handling for query results
        const toolResult: Record<string, Node | Relationship | unknown> = {};
        result.records.forEach(record => {
          const keys = record.keys as string[];
          for (const key of keys) {
            const value = record.get(key);
            if (value instanceof Neo4jNode) {
              toolResult[key] = NodeSchema.parse({
                id: value.elementId,
                labels: Array.from(value.labels),
                properties: value.properties
              });
            } else if (value instanceof Neo4jRelationship) {
              toolResult[key] = RelationshipSchema.parse({
                id: value.elementId,
                type: value.type,
                fromNode: value.startNodeElementId,
                toNode: value.endNodeElementId,
                properties: value.properties
              });
            } else {
              toolResult[key] = value;
            }
          }
        });
        return { toolResult };
      }

      case "create_node": {
        const params = CreateNodeSchema.parse(args) as z.infer<typeof CreateNodeSchema>;
        const { labels, properties } = params;
        
        // Validate properties against the schema
        NodePropertiesSchema.parse(properties);
        
        const result = await session.executeWrite(async (tx): Promise<{ toolResult: Node }> => {
          const labelStr = labels.map(l => `:${l}`).join('');
          const query = `
            CREATE (n${labelStr})
            SET n = $properties
            RETURN n
          `;
          const result = await tx.run(query, { properties });
          const node = result.records[0].get('n');
          
          return { toolResult: NodeSchema.parse({
            id: node.elementId,
            labels: Array.from(node.labels),
            properties: NodePropertiesSchema.parse(node.properties)
          })};
        });
        return result;
      }

      case "create_relationship": {
        const params = CreateRelationshipSchema.parse(args) as z.infer<typeof CreateRelationshipSchema>;
        const { startNodeId, endNodeId, type, properties = {} } = params;
        
        // Validate properties against the schema
        RelationshipPropertiesSchema.parse(properties);
        
        const result = await session.executeWrite(async (tx): Promise<{ toolResult: Relationship }> => {
          const query = `
            MATCH (from), (to)
            WHERE ID(from) = $startNodeId AND ID(to) = $endNodeId
            CREATE (from)-[r:${type} $properties]->(to)
            RETURN r
          `;
          const result = await tx.run(query, { startNodeId, endNodeId, properties });
          const rel = result.records[0].get('r');
          
          return { toolResult: RelationshipSchema.parse({
            id: rel.elementId,
            type: rel.type,
            fromNode: rel.startNodeElementId,
            toNode: rel.endNodeElementId,
            properties: RelationshipPropertiesSchema.parse(rel.properties)
          })};
        });
        return result;
      }

      case "find_path": {
        const params = FindPathSchema.parse(args) as z.infer<typeof FindPathSchema>;
        const { startNodeId, endNodeId, maxDepth = 4, relationshipTypes } = params;
        
        const result = await session.executeWrite(async (tx): Promise<{ toolResult: Path | null }> => {
          const relationshipTypesClause = relationshipTypes?.length
            ? `:${relationshipTypes.join('|')}`
            : '';
          const query = `
            MATCH path = shortestPath((from)-[${relationshipTypesClause}*..${maxDepth}]-(to))
            WHERE ID(from) = $startNodeId AND ID(to) = $endNodeId
            RETURN path
          `;
          const result = await tx.run(query, { startNodeId, endNodeId });
          
          if (result.records.length === 0) {
            return { toolResult: null };
          }

          const path = result.records[0].get('path');
          return { toolResult: PathSchema.parse({
            nodes: path.segments.map((segment: any) => ({
              id: segment.start.elementId,
              labels: Array.from(segment.start.labels),
              properties: segment.start.properties
            })).concat([{
              id: path.end.elementId,
              labels: Array.from(path.end.labels),
              properties: path.end.properties
            }]),
            relationships: path.segments.map((segment: any) => ({
              id: segment.relationship.elementId,
              type: segment.relationship.type,
              fromNode: segment.start.elementId,
              toNode: segment.end.elementId,
              properties: segment.relationship.properties
            }))
          })};
        });
        return result;
      }

      case "get_neighbors": {
        const params = GetNeighborsSchema.parse(args) as z.infer<typeof GetNeighborsSchema>;
        const { nodeId, direction = 'both', relationshipTypes = [], labels = [] } = params;
        
        const result = await session.executeWrite(async (tx): Promise<{ toolResult: { nodes: Node[], relationships: Relationship[] } }> => {
          const relationshipPattern = relationshipTypes.length ? `:${relationshipTypes.join('|')}` : '';
          const labelPattern = labels.length ? `:${labels.join('|')}` : '';
          const query = direction === 'both'
            ? `MATCH (n)-[r${relationshipPattern}]-(m${labelPattern}) WHERE ID(n) = $nodeId RETURN m, r`
            : direction === 'outgoing'
              ? `MATCH (n)-[r${relationshipPattern}]->(m${labelPattern}) WHERE ID(n) = $nodeId RETURN m, r`
              : `MATCH (n)<-[r${relationshipPattern}]-(m${labelPattern}) WHERE ID(n) = $nodeId RETURN m, r`;

          const result = await tx.run(query, { nodeId });
          return {
            toolResult: {
              nodes: result.records.map(record => {
                const node = record.get('m');
                return NodeSchema.parse({
                  id: node.elementId,
                  labels: Array.from(node.labels),
                  properties: node.properties
                });
              }),
              relationships: result.records.map(record => {
                const rel = record.get('r');
                return RelationshipSchema.parse({
                  id: rel.elementId,
                  type: rel.type,
                  fromNode: rel.startNodeElementId,
                  toNode: rel.endNodeElementId,
                  properties: rel.properties
                });
              })
            }
          };
        });
        return result;
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
    // Verify connection is valid
    await driver.getServerInfo();
    console.log('Connected to Neo4j');

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