import { z } from 'zod';

// Basic property schemas
export const NodePropertiesSchema = z.record(z.union([z.string(), z.number(), z.boolean(), z.array(z.union([z.string(), z.number(), z.boolean()]))]));
export const RelationshipPropertiesSchema = z.record(z.union([z.string(), z.number(), z.boolean(), z.array(z.union([z.string(), z.number(), z.boolean()]))]));

// Core type schemas
export const NodeSchema = z.object({
  id: z.string(),
  labels: z.array(z.string()),
  properties: NodePropertiesSchema
});

export const RelationshipSchema = z.object({
  id: z.string(),
  type: z.string(),
  startNodeId: z.string(),
  endNodeId: z.string(),
  properties: RelationshipPropertiesSchema
});

export const PathSchema = z.object({
  nodes: z.array(NodeSchema),
  relationships: z.array(RelationshipSchema)
});

// Input schemas for tool handlers
export const ExecuteCypherSchema = z.object({
  query: z.string(),
  parameters: z.record(z.any()).optional()
});

export const CreateNodeSchema = z.object({
  labels: z.array(z.string()),
  properties: NodePropertiesSchema
});

export const CreateRelationshipSchema = z.object({
  startNodeId: z.string(),
  endNodeId: z.string(),
  type: z.string(),
  properties: RelationshipPropertiesSchema
});

export const FindPathSchema = z.object({
  startNodeId: z.string(),
  endNodeId: z.string(),
  relationshipTypes: z.array(z.string()).optional(),
  maxDepth: z.number().optional()
});

export const GetNeighborsSchema = z.object({
  nodeId: z.string(),
  relationshipTypes: z.array(z.string()).optional(),
  direction: z.enum(['incoming', 'outgoing', 'both']).optional(),
  labels: z.array(z.string()).optional()
});

// Core type exports
export type Node = z.infer<typeof NodeSchema>;
export type Relationship = z.infer<typeof RelationshipSchema>;
export type Path = z.infer<typeof PathSchema>;

// Property type exports
export type NodeProperties = z.infer<typeof NodePropertiesSchema>;
export type RelationshipProperties = z.infer<typeof RelationshipPropertiesSchema>;