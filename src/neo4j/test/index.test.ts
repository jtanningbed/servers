import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { driver as createDriver, auth } from 'neo4j-driver';
import { initializeServer, MCPTestHarness } from './mcp-test-utils';

// Import the server creation function (we'll need to export this from index.ts)
const createServer = () => new Server(
  { name: "neo4j-mcp-server", version: "0.1.0" },
  { capabilities: { tools: {}, resources: {} } }
);

describe('Neo4j MCP Server', () => {
  const dbConfig = {
    uri: process.env.NEO4J_URI || 'bolt://localhost:7687',
    username: process.env.NEO4J_USERNAME || 'neo4j',
    password: process.env.NEO4J_PASSWORD || 'testpassword',
    database: process.env.NEO4J_DATABASE || 'neo4j'
  };

  let testDriver: any;
  let server: Server;
  let mcp: MCPTestHarness;

  beforeAll(async () => {
    // Set up Neo4j test driver
    testDriver = createDriver(
      dbConfig.uri,
      auth.basic(dbConfig.username, dbConfig.password)
    );
    await testDriver.verifyConnectivity();

    // Set up MCP server
    server = await createServer();
    const transport = await initializeServer(server);
    mcp = new MCPTestHarness(transport);
  });

  afterAll(async () => {
    await testDriver.close();
  });

  beforeEach(async () => {
    // Clear database before each test
    const session = testDriver.session({ database: dbConfig.database });
    try {
      await session.run('MATCH (n) DETACH DELETE n');
    } finally {
      await session.close();
    }
  });

  describe('Basic Operations', () => {
    describe('query_graph', () => {
      it('should execute simple read queries', async () => {
        const session = testDriver.session({ database: dbConfig.database });
        try {
          // Create test data
          await session.run(
            'CREATE (p:Person {name: "Alice", age: 30}) RETURN p'
          );

          // Test query
          const result = await mcp.callTool('query_graph', {
            query: 'MATCH (p:Person) RETURN p.name, p.age'
          });

          expect(result.toolResult).toHaveLength(1);
          expect(result.toolResult[0]).toEqual({
            'p.name': 'Alice',
            'p.age': 30
          });
        } finally {
          await session.close();
        }
      });

      it('should handle query parameters', async () => {
        const session = testDriver.session({ database: dbConfig.database });
        try {
          await session.run(
            'CREATE (p:Person {name: "Bob", age: 25}) RETURN p'
          );

          const result = await mcp.callTool('query_graph', {
            query: 'MATCH (p:Person) WHERE p.name = $name RETURN p.age',
            params: { name: 'Bob' }
          });

          expect(result.toolResult).toHaveLength(1);
          expect(result.toolResult[0]['p.age']).toBe(25);
        } finally {
          await session.close();
        }
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

        expect(result.toolResult).toHaveLength(1);
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
    it('should return database schema', async () => {
      const session = testDriver.session({ database: dbConfig.database });
      try {
        // Create test schema
        await session.run(`
          CREATE (p1:Person {name: 'Alice', age: 30})
          CREATE (p2:Person {name: 'Bob', age: 25})
          CREATE (c:Company {name: 'Acme', founded: 2020})
          CREATE (p1)-[r1:WORKS_AT {since: 2019}]->(c)
          CREATE (p2)-[r2:WORKS_AT {since: 2020}]->(c)
          CREATE (p1)-[r3:KNOWS]->(p2)
        `);

        const result = await mcp.callTool('explore_schema', {});

        expect(result.toolResult.labels).toContainEqual({
          name: 'Person',
          propertyKeys: ['name', 'age'],
          count: 2
        });

        expect(result.toolResult.relationshipTypes).toContainEqual({
          type: 'WORKS_AT',
          propertyKeys: ['since'],
          count: 2,
          startNodeLabels: ['Person'],
          endNodeLabels: ['Company']
        });
      } finally {
        await session.close();
      }
    });

    it('should expose schema as resource', async () => {
      const session = testDriver.session({ database: dbConfig.database });
      try {
        await session.run(`
          CREATE (p:Person {name: 'Alice'})
          CREATE (c:Company {name: 'Acme'})
          CREATE (p)-[r:WORKS_AT]->(c)
        `);

        const resources = await mcp.listResources();
        expect(resources).toContainEqual({
          uri: 'neo4j://schema',
          mimeType: 'application/json',
          name: 'Graph Schema'
        });

        const schema = await mcp.readResource('neo4j://schema');
        expect(JSON.parse(schema.contents[0].text)).toMatchObject({
          labels: expect.arrayContaining([{
            name: 'Person',
            propertyKeys: ['name']
          }]),
          relationshipTypes: expect.arrayContaining([{
            type: 'WORKS_AT'
          }])
        });
      } finally {
        await session.close();
      }
    });
  });

  describe('Integration Scenarios', () => {
    it('should support creating and querying a knowledge graph', async () => {
      // Create initial data structure
      await mcp.callTool('modify_graph', {
        query: `
          CREATE (alice:Person {name: 'Alice', age: 30, role: 'Engineer'})
          CREATE (bob:Person {name: 'Bob', age: 25, role: 'Designer'})
          CREATE (carol:Person {name: 'Carol', age: 35, role: 'Manager'})
          CREATE (acme:Company {name: 'Acme Corp', founded: 2020})
          CREATE (proj:Project {name: 'Website Redesign', started: 2024})
          RETURN *
        `
      });

      // Add relationships
      await mcp.callTool('modify_graph', {
        query: `
          MATCH (alice:Person {name: 'Alice'})
          MATCH (bob:Person {name: 'Bob'})
          MATCH (carol:Person {name: 'Carol'})
          MATCH (acme:Company {name: 'Acme Corp'})
          MATCH (proj:Project {name: 'Website Redesign'})
          CREATE (alice)-[:WORKS_AT {since: 2021}]->(acme)
          CREATE (bob)-[:WORKS_AT {since: 2022}]->(acme)
          CREATE (carol)-[:WORKS_AT {since: 2020}]->(acme)
          CREATE (alice)-[:WORKS_ON {role: 'Lead Developer'}]->(proj)
          CREATE (bob)-[:WORKS_ON {role: 'UI Designer'}]->(proj)
          CREATE (carol)-[:MANAGES]->(proj)
          CREATE (alice)-[:KNOWS {since: 2021}]->(bob)
          CREATE (bob)-[:KNOWS {since: 2022}]->(carol)
          RETURN *
        `
      });

      // Query team structure
      const teamQuery = await mcp.callTool('query_graph', {
        query: `
          MATCH (p:Person)-[r:WORKS_ON]->(proj:Project)
          RETURN p.name as name, p.role as role, r.role as projectRole
          ORDER BY name
        `
      });

      expect(teamQuery.toolResult).toEqual([
        { name: 'Alice', role: 'Engineer', projectRole: 'Lead Developer' },
        { name: 'Bob', role: 'Designer', projectRole: 'UI Designer' },
        { name: 'Carol', role: 'Manager', projectRole: null }
      ]);

      // Find all paths between team members
      const pathQuery = await mcp.callTool('query_graph', {
        query: `
          MATCH path = (p1:Person)-[:KNOWS*1..2]->(p2:Person)
          WHERE p1.name = 'Alice' AND p2.name = 'Carol'
          RETURN path
        `
      });

      expect(pathQuery.toolResult[0].path).toMatchObject({
        nodes: [
          { properties: { name: 'Alice' } },
          { properties: { name: 'Bob' } },
          { properties: { name: 'Carol' } }
        ]
      });

      // Check schema after creating the graph
      const schema = await mcp.callTool('explore_schema', {});
      expect(schema.toolResult).toMatchObject({
        labels: expect.arrayContaining([
          { name: 'Person', propertyKeys: expect.arrayContaining(['name', 'age', 'role']) },
          { name: 'Company', propertyKeys: expect.arrayContaining(['name', 'founded']) },
          { name: 'Project', propertyKeys: expect.arrayContaining(['name', 'started']) }
        ]),
        relationshipTypes: expect.arrayContaining([
          { type: 'WORKS_AT', propertyKeys: ['since'] },
          { type: 'WORKS_ON', propertyKeys: ['role'] },
          { type: 'KNOWS', propertyKeys: ['since'] },
          { type: 'MANAGES', propertyKeys: [] }
        ])
      });
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

    it('should handle invalid parameter types', async () => {
      await expect(
        mcp.callTool('query_graph', {
          query: 'CREATE (n:Node {prop: $value}) RETURN n',
          params: { value: undefined }
        })
      ).rejects.toThrow();
    });
  });
});
