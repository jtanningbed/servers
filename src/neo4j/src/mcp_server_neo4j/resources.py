from mcp.types import Resource, AnyUrl, ResourceTemplate

RESOURCES: dict[str, list[Resource]] = {
    # Schema resources
    "contents": [
        Resource(
            uri=AnyUrl("neo4j://schema/nodes"),
            name="Node Labels Schema",
            description="List of all node labels and their properties in the database",
            mime_type="application/json",
        ),
        Resource(
            uri=AnyUrl("neo4j://schema/relationships"),
            name="Relationship Types Schema",
            description="List of all relationship types and their properties",
            mime_type="application/json",
        ),
        Resource(
            uri=AnyUrl("neo4j://schema/indexes"),
            name="Database Indexes",
            description="List of all indexes and constraints",
            mime_type="application/json",
        ),
        # Query resources
        Resource(
            uri=AnyUrl("neo4j://queries/slow"),
            name="Slow Query Log",
            description="Log of queries that took longer than threshold to execute",
            mime_type="text/plain",
        ),
        # Statistics resources
        Resource(
            uri=AnyUrl("neo4j://stats/memory"),
            name="Memory Statistics",
            description="Current memory usage statistics",
            mime_type="application/json",
        ),
        Resource(
            uri=AnyUrl("neo4j://stats/transactions"),
            name="Transaction Statistics",
            description="Current transaction statistics",
            mime_type="application/json",
        ),
        Resource(
            uri=AnyUrl("neo4j://labels/count"),
            name="Label Count",
            description="Current node label count",
            mime_type="text/plain"
        ),
    ]
}

RESOURCE_TEMPLATES: dict[str, list[ResourceTemplate]] = {
    "contents": [
        # Template resources
        ResourceTemplate(
            uriTemplate="neo4j://nodes/{/label}/count",
            name="Node Count by Label",
            description="Count of nodes for a specific label",
            mime_type="text/plain",
        ),
        ResourceTemplate(
            uriTemplate="neo4j://relationships/{/type}/count",
            name="Relationship Count by Type",
            description="Count of relationships for a specific type",
            mime_type="text/plain",
        ),
        ResourceTemplate(
            uriTemplate="neo4j://queries/active/{/queryId}",
            name="Active Queries",
            description="Currently running queries excluding specified query ID",
            mimeType="application/json",
        ),
    ]
}
