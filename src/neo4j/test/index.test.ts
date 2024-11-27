import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { driver as createDriver, auth, Driver } from 'neo4j-driver';
import { initializeMCP, MCPTestHarness } from './mcp-test-utils';
import { createServer } from '../index.js';
import { getTestConfig } from './test-config.js';

describe('Neo4j MCP Server', () => {
  const config = getTestConfig();
  let mcp: MCPTestHarness;
  let server: Server;
  let driver: Driver;

  beforeAll(async () => {
    try {
      // 1. Create Neo4j driver
      console.log('Creating Neo4j driver...');
      driver = createDriver(config.uri, auth.basic(config.username, config.password));
      await driver.verifyConnectivity({ database: config.database });
      console.log('Neo4j connected successfully');

      // 2. Create MCP server
      console.log('Creating MCP server...');
      server = await createServer(config);
      
      // 3. Initialize MCP
      console.log('Initializing MCP...');
      mcp = await initializeMCP(server);
      console.log('Test setup complete');

    } catch (error) {
      console.error('Setup failed:', error);
      // Cleanup on error
      await driver?.close();
      await mcp?.cleanup();
      throw error;
    }
  });

  afterAll(async () => {
    console.log('Cleaning up...');
    await mcp?.cleanup();
    await driver?.close();
  });

  beforeEach(async () => {
    const session = driver.session({ database: config.database });
    try {
      await session.run('MATCH (n) DETACH DELETE n');
    } finally {
      await session.close();
    }
  });

  describe('Basic Operations', () => {
    describe('query_graph', () => {
      it('should execute simple read queries', async () => {
        const result = await mcp.callTool('query_graph', {
          query: 'RETURN 1 as n'
        });
        expect(result.toolResult[0].n).toBe(1);
      });

      it('should handle query parameters', async () => {
        const result = await mcp.callTool('query_graph', {
          query: 'RETURN $value as n',
          params: { value: 42 }
        });
        expect(result.toolResult[0].n).toBe(42);
      });
    });

    describe('modify_graph', () => {
      it('should create nodes and relationships', async () => {
        const result = await mcp.callTool('modify_graph', {
          query: `
            CREATE (a:Person {name: 'Alice', age: 30})
            CREATE (b:Person {name: 'Bob', age: 25})
            CREATE (a)-[r:KNOWS {since: 2020}]->(b)
            RETURN a, b, r
          `
        });
        
        const record = result.toolResult[0];
        expect(record.a.properties).toEqual({ name: 'Alice', age: 30 });
        expect(record.b.properties).toEqual({ name: 'Bob', age: 25 });
        expect(record.r.type).toBe('KNOWS');
        expect(record.r.properties).toEqual({ since: 2020 });
      });

      it('should validate query starts with CREATE/MERGE/SET', async () => {
        await expect(
          mcp.callTool('modify_graph', {
            query: 'MATCH (n) RETURN n'
          })
        ).rejects.toThrow(/must start with CREATE, MERGE, or SET/i);
      });
    });
  });

  describe('Schema Exploration', () => {
    it('should expose schema as resource', async () => {
      // Create some test data
      await mcp.callTool('modify_graph', {
        query: `
          CREATE (p:Person {name: 'Alice'})
          CREATE (c:Company {name: 'Acme'})
          CREATE (p)-[r:WORKS_AT]->(c)
        `
      });

      const resources = await mcp.listResources();
      expect(resources).toContainEqual(expect.objectContaining({
        uri: 'neo4j://schema',
        mimeType: 'application/json'
      }));

      const schema = await mcp.readResource('neo4j://schema');
      const data = JSON.parse(schema.contents[0].text);
      
      expect(data.labels).toContainEqual(expect.objectContaining({
        name: 'Person',
        propertyKeys: ['name']
      }));

      expect(data.relationshipTypes).toContainEqual(expect.objectContaining({
        type: 'WORKS_AT'
      }));
    });
  });

  describe('Error Handling', () => {
    it('should handle syntax errors in Cypher queries', async () => {
      await expect(
        mcp.callTool('query_graph', {
          query: 'MATCH n RETURN m'
        })
      ).rejects.toThrow();
    });

    it('should handle non-existent properties', async () => {
      const result = await mcp.callTool('query_graph', {
        query: 'MATCH (n:Person) RETURN n.nonexistent'
      });
      expect(result.toolResult).toEqual([{ 'n.nonexistent': null }]);
    });

    it('should handle null parameters', async () => {
      const result = await mcp.callTool('query_graph', {
        query: 'RETURN $param as value',
        params: { param: null }
      });
      expect(result.toolResult).toEqual([{ value: null }]);
    });
  });
});