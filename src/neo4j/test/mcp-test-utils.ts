import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { type Request } from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';

type BaseResponse = z.ZodObject<any, any>;

export class TestTransport {
    private messageId = 0;
    private server?: Server;

    setServer(server: Server) {
        console.log('Setting server on TestTransport');
        this.server = server;
    }

    async request<T extends BaseResponse>(method: string, params: any, resultSchema: T): Promise<z.infer<T>> {
        if (!this.server) {
            throw new Error('Server not set');
        }
        console.log(`Making request: ${method}`, params);

        const result = await this.server.request({
            method,
            params
        }, resultSchema);

        console.log(`Got result for ${method}:`, result);
        return result;
    }
}

export async function initializeServer(server: Server): Promise<TestTransport> {
    console.log('Initializing server...');
    const transport = new TestTransport();
    transport.setServer(server);

    console.log('Sending initialize request...');
    await transport.request('initialize', {
        capabilities: {
            tools: true,
            resources: true
        }
    }, z.object({
        protocolVersion: z.string()
    }));

    console.log('Sending initialized notification...');
    await transport.request('initialized', {}, z.object({}));

    console.log('Server initialization complete');
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
    }, z.object({
      toolResult: z.any()
    }));
  }

  async listResources() {
    const result = await this.transport.request('resources/list', {}, z.object({
      resources: z.array(z.object({
        uri: z.string(),
        mimeType: z.string(),
        name: z.string().optional(),
        description: z.string().optional()
      }))
    }));
    return result.resources;
  }

  async readResource(uri: string) {
    const result = await this.transport.request('resources/read', { uri }, z.object({
      contents: z.array(z.object({
        uri: z.string(),
        mimeType: z.string(),
        text: z.string()
      }))
    }));
    return {
      contents: result.contents
    };
  }

  async listTools() {
    const result = await this.transport.request('tools/list', {}, z.object({
      tools: z.array(z.object({
        name: z.string(),
        description: z.string(),
        inputSchema: z.any()
      }))
    }));
    return result.tools;
  }
}