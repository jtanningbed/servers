import { z } from 'zod';

// Core data types
export const NodeSchema = z.object({
  id: z.string(),
  labels: z.array(z.string()),
  properties: z.record(z.unknown())
});

export const RelationshipSchema = z.object({
  id: z.string(),
  type: z.string(),
  fromNode: z.string(),
  toNode: z.string(),
  properties: z.record(z.unknown())
});

export const PathSchema = z.object({
  nodes: z.array(NodeSchema),
  relationships: z.array(RelationshipSchema)
});

// Tool schemas
export const QueryGraphSchema = z.object({
  query: z.string().min(1).describe(
    'Cypher query to execute. Examples:\n' +
    '- MATCH (n:Person) RETURN n\n' +
    '- MATCH p=(a)-[r:KNOWS]->(b) RETURN p\n' +
    '- MATCH (n) WHERE n.name = $name RETURN n'
  ),
  params: z.record(z.unknown()).optional().describe(
    'Optional query parameters. Example:\n' +
    '{ "name": "Alice" }'
  )
});

export const ModifyGraphSchema = z.object({
  query: z.string().min(1)
    .regex(/^\s*(CREATE|MERGE|SET)/i)
    .describe(
      'Cypher query that modifies the graph. Must start with CREATE, MERGE, or SET. Examples:\n' +
      '- CREATE (n:Person {name: $name}) RETURN n\n' +
      '- MERGE (a:Person {name: $name1})-[r:KNOWS]->(b:Person {name: $name2})\n' +
      '- SET n.age = $age'
    ),
  params: z.record(z.unknown()).optional().describe('Query parameters')
});

// Schema exploration types
export const LabelSchema = z.object({
  name: z.string(),
  propertyKeys: z.array(z.string()),
  count: z.number()
});

export const RelationshipTypeSchema = z.object({
  type: z.string(),
  propertyKeys: z.array(z.string()),
  count: z.number(),
  startNodeLabels: z.array(z.string()),
  endNodeLabels: z.array(z.string())
});

export const GraphSchemaSchema = z.object({
  labels: z.array(LabelSchema),
  relationshipTypes: z.array(RelationshipTypeSchema)
});

// Type exports
export type Node = z.infer<typeof NodeSchema>;
export type Relationship = z.infer<typeof RelationshipSchema>;
export type Path = z.infer<typeof PathSchema>;
export type QueryGraph = z.infer<typeof QueryGraphSchema>;
export type ModifyGraph = z.infer<typeof ModifyGraphSchema>;
export type Label = z.infer<typeof LabelSchema>;
export type RelationshipType = z.infer<typeof RelationshipTypeSchema>;
export type GraphSchema = z.infer<typeof GraphSchemaSchema>;