#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { Neo4jClient } from './client.js';
import {
  ExecuteCypherSchema,
  CreateNodeSchema,
  CreateRelationshipSchema,
  FindPathSchema,
  GetNeighborsSchema,
  type ExecuteCypherInput,
  type CreateNodeInput,
  type CreateRelationshipInput,
  type FindPathInput,
  type GetNeighborsInput
} from './schemas.js';
import { zodToJsonSchema } from 'zod-to-json-schema';

// Initialize Neo4j client
const client = new Neo4jClient();

// Create MCP server
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

// List available tools
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
      name: "find_paths",
      description: "Find paths between two nodes",
      inputSchema: zodToJsonSchema(FindPathSchema)
    },
    {
      name: "get_neighbors",
      description: "Get neighboring nodes of a given node",
      inputSchema: zodToJsonSchema(GetNeighborsSchema)
    }
  ]
}));

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  try {
    const { name, arguments: args } = request.params;
    if (!args) throw new Error("Arguments are required");

    switch (name) {
      case "execute_cypher": {
        const params = ExecuteCypherSchema.parse(args);
        const result = await client.executeCypher(params.query, params.params);
        return { toolResult: result };
      }

      case "create_node": {
        const params = CreateNodeSchema.parse(args);
        const result = await client.createNode(params.labels, params.properties);
        return { toolResult: result };
      }

      case "create_relationship": {
        const params = CreateRelationshipSchema.parse(args);
        const result = await client.createRelationship(
          params.fromNode,
          params.toNode,
          params.type,
          params.properties
        );
        return { toolResult: result };
      }

      case "find_paths": {
        const params = FindPathSchema.parse(args);
        const result = await client.findPaths(
          params.fromNode,
          params.toNode,
          params.maxDepth,
          params.relationshipTypes
        );
        return { toolResult: result };
      }

      case "get_neighbors": {
        const params = GetNeighborsSchema.parse(args);
        const result = await client.getNeighbors(
          params.nodeId,
          params.direction,
          params.relationshipTypes,
          params.limit
        );
        return { toolResult: result };
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
  }
});

// Start the server
async function main() {
  try {
    // Verify Neo4j connection
    await client.verifyConnectivity();
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
  await client.close();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.error('Shutting down...');
  await client.close();
  process.exit(0);
});

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});