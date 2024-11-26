import { z } from 'zod';

// Schema for executing Cypher queries
export const ExecuteCypherSchema = z.object({
    query: z.string().min(1).describe("Cypher query to execute"),
    params: z.record(z.unknown()).optional().describe("Optional query parameters")
});

// Schema for node properties with better type validation
export const NodePropertiesSchema = z.record(
    z.string(),
    z.union([
        z.string(),
        z.number(),
        z.boolean(),
        z.array(z.union([z.string(), z.number(), z.boolean()])),
        z.record(z.string(), z.union([z.string(), z.number(), z.boolean()]))
    ])
).describe("Node properties with support for primitive types, arrays, and nested objects");

// Schema for relationship properties
export const RelationshipPropertiesSchema = z.record(
    z.string(),
    z.union([
        z.string(),
        z.number(),
        z.boolean(),
        z.array(z.union([z.string(), z.number(), z.boolean()])),
        z.record(z.string(), z.union([z.string(), z.number(), z.boolean()]))
    ])
).describe("Relationship properties with support for primitive types, arrays, and nested objects");

// Schema for creating nodes
export const CreateNodeSchema = z.object({
    labels: z.array(z.string()).min(1).describe("Node labels"),
    properties: NodePropertiesSchema
});

// Schema for creating relationships
export const CreateRelationshipSchema = z.object({
    fromNode: z.string().describe("ID or reference of the source node"),
    toNode: z.string().describe("ID or reference of the target node"),
    type: z.string().describe("Relationship type"),
    properties: RelationshipPropertiesSchema.optional().describe("Optional relationship properties")
});

// Schema for finding paths
export const FindPathSchema = z.object({
    fromNode: z.string().describe("Starting node ID or reference"),
    toNode: z.string().describe("Ending node ID or reference"),
    maxDepth: z.number().optional().describe("Maximum path depth (optional)"),
    relationshipTypes: z.array(z.string()).optional().describe("Filter by relationship types")
});

// Schema for getting node neighbors
export const GetNeighborsSchema = z.object({
    nodeId: z.string().describe("Node ID or reference"),
    direction: z.enum(['incoming', 'outgoing', 'both']).default('both').describe("Direction of relationships"),
    relationshipTypes: z.array(z.string()).optional().describe("Filter by relationship types"),
    limit: z.number().optional().describe("Maximum number of neighbors to return")
});

// Response types using Zod
export const NodeSchema = z.object({
    id: z.string(),
    labels: z.array(z.string()),
    properties: NodePropertiesSchema
});

export const RelationshipSchema = z.object({
    id: z.string(),
    type: z.string(),
    fromNode: z.string(),
    toNode: z.string(),
    properties: RelationshipPropertiesSchema
});

export const PathSchema = z.object({
    nodes: z.array(NodeSchema),
    relationships: z.array(RelationshipSchema)
});

// Type exports
export type ExecuteCypherInput = z.infer<typeof ExecuteCypherSchema>;
export type CreateNodeInput = z.infer<typeof CreateNodeSchema>;
export type CreateRelationshipInput = z.infer<typeof CreateRelationshipSchema>;
export type FindPathInput = z.infer<typeof FindPathSchema>;
export type GetNeighborsInput = z.infer<typeof GetNeighborsSchema>;
export type Node = z.infer<typeof NodeSchema>;
export type Relationship = z.infer<typeof RelationshipSchema>;
export type Path = z.infer<typeof PathSchema>;