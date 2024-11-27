#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { driver as createDriver, auth, isInt, Integer } from 'neo4j-driver';
import { zodToJsonSchema } from 'zod-to-json-schema';
import {
  QueryGraphSchema,
  ModifyGraphSchema,
  GraphSchemaSchema,
} from './schemas.js';

// Helper functions for processing Neo4j values
function processQueryValue(value: any): any {
  if (value === null || value === undefined) {
    return null;
  }

  // Handle Neo4j Node type
  if (value.labels && value.properties && value.elementId) {
    return {
      id: value.elementId,
      labels: Array.from(value.labels),
      properties: Object.fromEntries(
        Object.entries(value.properties).map(([k, v]) => [
          k,
          v && typeof v === 'object' && isInt(v) ? Integer.fromValue(v).toNumber() : v
        ])
      )
    };
  }

  // Handle Neo4j Relationship type
  if (value.type && value.properties && value.elementId) {
    return {
      id: value.elementId,
      type: value.type,
      fromNode: value.startNodeElementId,
      toNode: value.endNodeElementId,
      properties: Object.fromEntries(
        Object.entries(value.properties).map(([k, v]) => [
          k,
          v && typeof v === 'object' && isInt(v) ? Integer.fromValue(v).toNumber() : v
        ])
      )
    };
  }

  // Handle Neo4j Path type
  if (value.segments) {
    return {
      nodes: value.segments.map((s: any) => processQueryValue(s.start))
        .concat([processQueryValue(value.end)]),
      relationships: value.segments.map((s: any) => processQueryValue(s.relationship))
    };
  }

  // Handle Neo4j Integer
  if (value && typeof value === 'object' && isInt(value)) {
    return Integer.fromValue(value).toNumber();
  }

  return value;
}

// Server creation function exported for testing
export async function createServer(config?: {
  uri?: string;
  username?: string;
  password?: string;
  database?: string;
}): Promise<Server> {
  // Use provided config or environment variables
  const uri = config?.uri || process.env.NEO4J_URI || 'bolt://localhost:7687';
  const username = config?.username || process.env.NEO4J_USERNAME || 'neo4j';
  const password = config?.password || process.env.NEO4J_PASSWORD;
  const database = config?.database || process.env.NEO4J_DATABASE || 'neo4j';

  if (!password) {
    throw new Error("Password is required (either pass it in config.password or set NEO4J_PASSWORD environment variable)");
  }

  const driver = createDriver(uri, auth.basic(username, password));

  // Initialize server
  const server = new Server(
    {
      name: "neo4j-mcp-server",
      version: "0.1.0",
    },
    {
      capabilities: {
        tools: {},
        resources: {}
      },
    }
  );

  // Resource handling
  server.setRequestHandler(ListResourcesRequestSchema, async () => ({
    resources: [
      {
        uri: "neo4j://schema",
        mimeType: "application/json",
        name: "Graph Schema",
        description: "Database schema including labels, relationships, and their properties"
      }
    ]
  }));

  server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
    const session = driver.session({ database });
    try {
      if (request.params.uri !== "neo4j://schema") {
        throw new Error("Invalid resource URI");
      }

      // Get all node labels and their properties
      const labelResult = await session.run(
        'CALL db.labels() YIELD label ' +
        'CALL { ' +
        '  WITH label ' +
        '  MATCH (n) ' +
        '  WHERE label IN labels(n) ' +
        '  WITH label, n, properties(n) as props ' +
        '  RETURN label, collect(DISTINCT keys(props)) as propertyKeys, count(n) as nodeCount ' +
        '  LIMIT 1 ' +
        '} ' +
        'RETURN label as name, propertyKeys[0] as propertyKeys, nodeCount as count'
      );

      // Get all relationship types and their properties
      const relResult = await session.run(
        'CALL db.relationshipTypes() YIELD relationshipType ' +
        'CALL { ' +
        '  WITH relationshipType ' +
        '  MATCH (start)-[r]->(end) ' +
        '  WHERE type(r) = relationshipType ' +
        '  WITH relationshipType, r, properties(r) as props, ' +
        '       labels(start) as startLabels, labels(end) as endLabels ' +
        '  RETURN relationshipType, ' +
        '         collect(DISTINCT keys(props)) as propertyKeys, ' +
        '         count(r) as relCount, ' +
        '         collect(DISTINCT startLabels) as startNodeLabels, ' +
        '         collect(DISTINCT endLabels) as endNodeLabels ' +
        '  LIMIT 1 ' +
        '} ' +
        'RETURN relationshipType as type, ' +
        '       propertyKeys[0] as propertyKeys, ' +
        '       relCount as count, ' +
        '       startNodeLabels[0] as startNodeLabels, ' +
        '       endNodeLabels[0] as endNodeLabels'
      );

      const schema = GraphSchemaSchema.parse({
        labels: labelResult.records.map(record => ({
          name: record.get('name'),
          propertyKeys: record.get('propertyKeys') || [],
          count: Integer.fromValue(record.get('count')).toNumber()
        })),
        relationshipTypes: relResult.records.map(record => ({
          type: record.get('type'),
          propertyKeys: record.get('propertyKeys') || [],
          count: Integer.fromValue(record.get('count')).toNumber(),
          startNodeLabels: record.get('startNodeLabels') || [],
          endNodeLabels: record.get('endNodeLabels') || []
        }))
      });

      return {
        contents: [{
          uri: request.params.uri,
          mimeType: "application/json",
          text: JSON.stringify(schema, null, 2)
        }]
      };
    } finally {
      await session.close();
    }
  });

  // Tool handlers
  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [
      {
        name: "query_graph",
        description: "Execute a read-only Cypher query to retrieve data from the graph. " +
          "Returns nodes, relationships, and paths based on the query. " +
          "Use this for searching, traversing, and analyzing the graph structure.",
        inputSchema: zodToJsonSchema(QueryGraphSchema)
      },
      {
        name: "modify_graph",
        description: "Modify the graph using Cypher CREATE, MERGE, or SET operations. " +
          "Use this for creating nodes, establishing relationships, or updating properties. " +
          "Query must start with CREATE, MERGE, or SET.",
        inputSchema: zodToJsonSchema(ModifyGraphSchema)
      },
      {
        name: "explore_schema",
        description: "Get detailed information about the graph structure, including: \n" +
          "- Available node labels and their properties\n" +
          "- Relationship types and their properties\n" +
          "- Connectivity patterns between different types of nodes",
        inputSchema: { type: "object", properties: {} }
      }
    ]
  }));

  // Handle tool calls
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const session = driver.session({ database });
    try {
      const { name, arguments: args } = request.params;
      if (!args && name !== 'explore_schema') {
        throw new Error("Arguments are required");
      }

      switch (name) {
        case "query_graph": {
          const params = QueryGraphSchema.parse(args);
          const result = await session.run(params.query, params.params);
          
          return {
            toolResult: result.records.map(record => {
              const obj: { [key: string]: any } = {};
              const keys = Array.from(record.keys);
              for (const key of keys) {
                obj[String(key)] = processQueryValue(record.get(key));
              }
              return obj;
            })
          };
        }

        case "modify_graph": {
          const params = ModifyGraphSchema.parse(args);
          const result = await session.run(params.query, params.params);
          
          return {
            toolResult: result.records.map(record => {
              const obj: { [key: string]: any } = {};
              const keys = Array.from(record.keys);
              for (const key of keys) {
                obj[String(key)] = processQueryValue(record.get(key));
              }
              return obj;
            })
          };
        }

        case "explore_schema": {
          const labelResult = await session.run(
            'CALL db.labels() YIELD label ' +
            'CALL { ' +
            '  WITH label ' +
            '  MATCH (n) ' +
            '  WHERE label IN labels(n) ' +
            '  WITH label, n, properties(n) as props ' +
            '  RETURN label, collect(DISTINCT keys(props)) as propertyKeys, count(n) as nodeCount ' +
            '  LIMIT 1 ' +
            '} ' +
            'RETURN label as name, propertyKeys[0] as propertyKeys, nodeCount as count'
          );

          const relResult = await session.run(
            'CALL db.relationshipTypes() YIELD relationshipType ' +
            'CALL { ' +
            '  WITH relationshipType ' +
            '  MATCH (start)-[r]->(end) ' +
            '  WHERE type(r) = relationshipType ' +
            '  WITH relationshipType, r, properties(r) as props, ' +
            '       labels(start) as startLabels, labels(end) as endLabels ' +
            '  RETURN relationshipType, ' +
            '         collect(DISTINCT keys(props)) as propertyKeys, ' +
            '         count(r) as relCount, ' +
            '         collect(DISTINCT startLabels) as startNodeLabels, ' +
            '         collect(DISTINCT endLabels) as endNodeLabels ' +
            '  LIMIT 1 ' +
            '} ' +
            'RETURN relationshipType as type, ' +
            '       propertyKeys[0] as propertyKeys, ' +
            '       relCount as count, ' +
            '       startNodeLabels[0] as startNodeLabels, ' +
            '       endNodeLabels[0] as endNodeLabels'
          );

          const schema = GraphSchemaSchema.parse({
            labels: labelResult.records.map(record => ({
              name: record.get('name'),
              propertyKeys: record.get('propertyKeys') || [],
              count: Integer.fromValue(record.get('count')).toNumber()
            })),
            relationshipTypes: relResult.records.map(record => ({
              type: record.get('type'),
              propertyKeys: record.get('propertyKeys') || [],
              count: Integer.fromValue(record.get('count')).toNumber(),
              startNodeLabels: record.get('startNodeLabels') || [],
              endNodeLabels: record.get('endNodeLabels') || []
            }))
          });

          return { toolResult: schema };
        }

        default:
          throw new Error(`Unknown tool: ${name}`);
      }
    } catch (error) {
      if (error instanceof Error) {
        throw new Error(`Tool execution failed: ${error.message}`);
      }
      throw error;
    } finally {
      await session.close();
    }
  });

  return server;
}

// Simple server startup
async function runServer() {
  const server = await createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

runServer().catch(console.error);
