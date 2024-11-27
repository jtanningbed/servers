import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { type Request } from '@modelcontextprotocol/sdk/types.js';

export class TestTransport {
  private messageId = 0;
  private server?: Server;

  setServer(server: Server) {
    this.server = server;
  }

  async request(method: string, params: any): Promise<any> {
    if (!this.server) {
      throw new Error('Server not set');
    }

    // Construct a message that follows the MCP protocol
    const message = {
      _type: 'request',
      method,
      params
    } as Request;

    // Use the server's handleMessage method
    const response = await this.server.handleMessage(message);

    if ('error' in response) {
      throw new Error(response.error.message);
    }

    return response.result;
  }
}

export async function initializeServer(server: Server): Promise<TestTransport> {
  const transport = new TestTransport();
  transport.setServer(server);

  // Initialize server
  await transport.request('initialize', {
    capabilities: {
      tools: true,
      resources: true
    }
  });

  // Send initialized notification
  await transport.request('initialized', {});

  return transport;
}

export class MCPTestHarness {
  private transport: TestTransport;

  constructor(transport: TestTransport) {
    this.transport = transport;
  }

  async callTool(name: string, args: any) {
    return this.transport.request('tool/call', {
      name,
      arguments: args
    });
  }

  async listResources() {
    const result = await this.transport.request('resources/list', {});
    return result.resources;
  }

  async readResource(uri: string) {
    const result = await this.transport.request('resources/read', { uri });
    return {
      contents: result.contents
    };
  }

  async listTools() {
    const result = await this.transport.request('tools/list', {});
    return result.tools;
  }
}