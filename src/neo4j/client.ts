import neo4j, { Driver, Session, Result } from 'neo4j-driver';
import type { Node, Relationship, Path } from './schemas.js';

export class Neo4jClient {
  private driver: Driver;
  private database: string;

  constructor() {
    const uri = process.env.NEO4J_URI || 'bolt://localhost:7687';
    const username = process.env.NEO4J_USERNAME || 'neo4j';
    const password = process.env.NEO4J_PASSWORD;
    const database = process.env.NEO4J_DATABASE || 'neo4j';

    if (!password) {
      throw new Error('NEO4J_PASSWORD environment variable is required');
    }

    this.driver = neo4j.driver(uri, neo4j.auth.basic(username, password));
    this.database = database;
  }

  async verifyConnectivity(): Promise<void> {
    await this.driver.verifyConnectivity();
  }

  async close(): Promise<void> {
    await this.driver.close();
  }

  private async getSession(): Promise<Session> {
    return this.driver.session({ database: this.database });
  }

  // Convert Neo4j Node to our Node type
  private convertNode(node: neo4j.Node): Node {
    return {
      id: node.elementId,
      labels: Array.from(node.labels),
      properties: Object.fromEntries(
        Object.entries(node.properties).map(([k, v]) => [k, v])
      )
    };
  }

  // Convert Neo4j Relationship to our Relationship type
  private convertRelationship(rel: neo4j.Relationship): Relationship {
    return {
      id: rel.elementId,
      type: rel.type,
      fromNode: rel.startNodeElementId,
      toNode: rel.endNodeElementId,
      properties: Object.fromEntries(
        Object.entries(rel.properties).map(([k, v]) => [k, v])
      )
    };
  }

  // Execute a Cypher query with parameters
  async executeCypher(query: string, params?: Record<string, any>): Promise<any> {
    const session = await this.getSession();
    try {
      const result = await session.run(query, params);
      return result.records.map(record => {
        const obj: Record<string, any> = {};
        record.keys.forEach(key => {
          const value = record.get(key);
          if (neo4j.isNode(value)) {
            obj[key] = this.convertNode(value);
          } else if (neo4j.isRelationship(value)) {
            obj[key] = this.convertRelationship(value);
          } else if (neo4j.isPath(value)) {
            obj[key] = {
              nodes: value.segments.map(s => this.convertNode(s.start))
                .concat([this.convertNode(value.end)]),
              relationships: value.segments.map(s => this.convertRelationship(s.relationship))
            };
          } else {
            obj[key] = value;
          }
        });
        return obj;
      });
    } finally {
      await session.close();
    }
  }

  // Create a new node
  async createNode(labels: string[], properties: Record<string, any>): Promise<Node> {
    const labelStr = labels.map(l => `:${l}`).join('');
    const propsStr = Object.entries(properties)
      .map(([k, v]) => `${k}: $${k}`)
      .join(', ');

    const query = `CREATE (n${labelStr} {${propsStr}}) RETURN n`;
    const result = await this.executeCypher(query, properties);
    return result[0].n;
  }

  // Create a new relationship
  async createRelationship(
    fromNodeId: string,
    toNodeId: string,
    type: string,
    properties: Record<string, any> = {}
  ): Promise<Relationship> {
    const propsStr = Object.entries(properties)
      .map(([k, v]) => `${k}: $${k}`)
      .join(', ');

    const query = `
      MATCH (from), (to)
      WHERE elementId(from) = $fromId AND elementId(to) = $toId
      CREATE (from)-[r:${type} {${propsStr}}]->(to)
      RETURN r
    `;

    const params = {
      fromId: fromNodeId,
      toId: toNodeId,
      ...properties
    };

    const result = await this.executeCypher(query, params);
    return result[0].r;
  }

  // Find paths between nodes
  async findPaths(
    fromNodeId: string,
    toNodeId: string,
    maxDepth: number = 4,
    relationshipTypes: string[] = []
  ): Promise<Path[]> {
    const relTypeStr = relationshipTypes.length
      ? `:${relationshipTypes.join('|')}`
      : '';

    const query = `
      MATCH path = (from)-[${relTypeStr}*..${maxDepth}]->(to)
      WHERE elementId(from) = $fromId AND elementId(to) = $toId
      RETURN path
    `;

    const result = await this.executeCypher(query, {
      fromId: fromNodeId,
      toId: toNodeId
    });

    return result.map((r: any) => r.path);
  }

  // Get node neighbors
  async getNeighbors(
    nodeId: string,
    direction: 'incoming' | 'outgoing' | 'both' = 'both',
    relationshipTypes: string[] = [],
    limit?: number
  ): Promise<Node[]> {
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

    const result = await this.executeCypher(query, { nodeId });
    return result.map((r: any) => r.neighbor);
  }
}