import { jest, describe, beforeAll, afterAll, beforeEach, it, expect } from '@jest/globals';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { driver as createDriver, auth, Driver } from 'neo4j-driver';
import { initializeMCP, MCPTestHarness } from './mcp-test-utils';
import { createServer } from '../index.js';
import { getTestConfig } from './config.js';

describe('Neo4j MCP Server', () => {
  let config = getTestConfig();
  console.log('Initial config:', JSON.stringify(config, null, 2));
  let mcp: MCPTestHarness;
  let server: Server;
  let driver: Driver;

  beforeAll(async () => {
    try {
      // Ensure we have fresh config
      config = getTestConfig();
      console.log('Config before driver creation:', JSON.stringify(config, null, 2));

      // 1. Create Neo4j driver
      console.log('Creating Neo4j driver...');
      driver = createDriver(config.uri, auth.basic(config.username, config.password));
      await driver.verifyConnectivity({ database: config.database });
      console.log('Neo4j connected successfully');

      // 2. Create MCP server with explicit config copy
      console.log('Creating MCP server with config...');
      server = await createServer({
        uri: config.uri,
        username: config.username,
        password: config.password,
        database: config.database
      });
      console.log('MCP server created successfully');
      
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

  // Rest of the test file remains the same...
