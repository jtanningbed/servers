import { jest, describe, beforeAll, afterAll, beforeEach, it, expect } from '@jest/globals';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { driver as createDriver, auth, Driver } from 'neo4j-driver';
import { initializeMCP, MCPTestHarness } from './mcp-test-utils';
import { createServer } from '../index.js';
import { getTestConfig } from './config.js';

describe('Neo4j MCP Server', () => {
  // Try creating config before any test setup
  const initialConfig = getTestConfig();
  console.log('Initial config loaded:', initialConfig);

  // Test the config loading first
  it('should load config correctly', () => {
    const config = getTestConfig();
    expect(config.uri).toBeDefined();
    expect(config.username).toBeDefined();
    expect(config.password).toBeDefined();
    expect(config.database).toBeDefined();
    console.log('Config test passed');
  });

  // Test server creation separately
  it('should create server with config', async () => {
    const config = {
      uri: 'bolt://localhost:7687',
      username: 'neo4j',
      password: 'testpassword',
      database: 'neo4j'
    };
    
    const server = await createServer(config);
    expect(server).toBeDefined();
    console.log('Server creation test passed');
  });

  // Original test suite follows...
  let mcp: MCPTestHarness;
  let server: Server;
  let driver: Driver;

  beforeAll(async () => {
    const config = getTestConfig();
    console.log('Setting up with config:', config);

    try {
      // 1. Create Neo4j driver
      driver = createDriver(config.uri, auth.basic(config.username, config.password));
      await driver.verifyConnectivity({ database: config.database });
      console.log('Neo4j connected successfully');

      // 2. Create MCP server
      server = await createServer({
        uri: config.uri,
        username: config.username,
        password: config.password,
        database: config.database
      });
      
      // 3. Initialize MCP
      mcp = await initializeMCP(server);
      console.log('Test setup complete');

    } catch (error) {
      console.error('Setup failed:', error);
      await driver?.close();
      await mcp?.cleanup();
      throw error;
    }
  });

  afterAll(async () => {
    await mcp?.cleanup();
    await driver?.close();
  });

  // Rest of your test cases follow...
});
