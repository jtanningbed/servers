"""
Query templates and models for Neo4j operations.
Consolidates templates from queries.py and examples.py.
"""
from typing import Dict, Set, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class QueryTemplate(BaseModel):
    """Definition of a reusable query template"""
    name: str = Field(..., description="Template identifier")
    query: str = Field(..., description="Parameterized Cypher query")
    description: str = Field(..., description="Description of what the template does")
    required_labels: Set[str] = Field(
        default_factory=set,
        description="Node labels required by this template"
    )
    required_relationships: Set[str] = Field(
        default_factory=set,
        description="Relationship types required by this template"
    )
    parameter_descriptions: Dict[str, str] = Field(
        default_factory=dict,
        description="Descriptions of expected parameters"
    )
    example: Dict[str, Any] = Field(
        ...,
        description="Example usage of the template"
    )
    category: str = Field(
        ...,
        description="Category of operation (e.g., analysis, creation, search)"
    )
    validation_rules: Dict[str, str] = Field(
        default_factory=dict,
        description="Rules for validating parameter values"
    )

class QueryResponse(BaseModel):
    """Model for query execution results"""
    results: List[Dict[str, Any]] = Field(..., description="Query results")
    total_results: int = Field(..., description="Total number of results returned")
    query_details: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional query execution details like performance metrics"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    template_used: Optional[str] = Field(
        None,
        description="Name of the template used, if query was template-based"
    )

# Collection of standard query templates
STANDARD_TEMPLATES = {
    "entity_search": QueryTemplate(
        name="entity_search",
        description="Search for entities based on property values with optional relationship constraints",
        query="""
        MATCH (n:$label)
        WHERE n[$property] $operator $value
        OPTIONAL MATCH (n)-[r]-(related)
        WHERE type(r) in $relationship_types
        RETURN n as entity,
               collect({
                   relationship: type(r),
                   direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END,
                   entity: {
                       labels: labels(related),
                       properties: properties(related)
                   }
               }) as connections
        """,
        required_labels=set(),  # Determined by parameters
        required_relationships=set(),  # Determined by parameters
        parameter_descriptions={
            "label": "Label of entities to search",
            "property": "Property to filter on",
            "operator": "Comparison operator (e.g., =, >, <, CONTAINS)",
            "value": "Value to compare against",
            "relationship_types": "List of relationship types to include",
        },
        example={
            "query": """
            MATCH (p:Person)
            WHERE p.age > 25
            OPTIONAL MATCH (p)-[r:KNOWS|WORKS_WITH]-(related)
            RETURN p as entity,
                   collect({
                       relationship: type(r),
                       direction: CASE WHEN startNode(r) = p THEN 'outgoing' ELSE 'incoming' END,
                       entity: {
                           labels: labels(related),
                           properties: properties(related)
                       }
                   }) as connections
            """,
            "parameters": {
                "label": "Person",
                "property": "age",
                "operator": ">",
                "value": 25,
                "relationship_types": ["KNOWS", "WORKS_WITH"],
            },
        },
        category="search",
        validation_rules={
            "operator": "must be one of: =, >, <, >=, <=, CONTAINS, STARTS WITH, ENDS WITH",
            "relationship_types": "must be a non-empty list of existing relationship types",
        },
    ),
    "graph_analytics": QueryTemplate(
        name="graph_analytics",
        description="Perform graph analytics on entities and their relationships",
        query="""
        MATCH (n:$label)
        OPTIONAL MATCH (n)-[r]-()
        WITH n,
             count(DISTINCT type(r)) as relationship_types_count,
             count(r) as total_relationships,
             collect(DISTINCT type(r)) as relationship_types,
             [r IN collect(r) WHERE startNode(r) = n] as outgoing,
             [r IN collect(r) WHERE endNode(r) = n] as incoming
        RETURN {
            entity: {
                labels: labels(n),
                properties: properties(n)
            },
            metrics: {
                relationship_types_count: relationship_types_count,
                total_relationships: total_relationships,
                outgoing_count: size(outgoing),
                incoming_count: size(incoming),
                relationship_types: relationship_types
            }
        } as analysis
        ORDER BY total_relationships DESC
        LIMIT $limit
        """,
        required_labels=set(),
        required_relationships=set(),
        parameter_descriptions={
            "label": "Label of entities to analyze",
            "limit": "Maximum number of results to return",
        },
        example={
            "query": """
            MATCH (p:Person)
            OPTIONAL MATCH (p)-[r]-()
            WITH p,
                 count(DISTINCT type(r)) as relationship_types_count,
                 count(r) as total_relationships,
                 collect(DISTINCT type(r)) as relationship_types,
                 [r IN collect(r) WHERE startNode(r) = p] as outgoing,
                 [r IN collect(r) WHERE endNode(r) = p] as incoming
            RETURN {
                entity: {
                    labels: labels(p),
                    properties: properties(p)
                },
                metrics: {
                    relationship_types_count: relationship_types_count,
                    total_relationships: total_relationships,
                    outgoing_count: size(outgoing),
                    incoming_count: size(incoming),
                    relationship_types: relationship_types
                }
            } as analysis
            ORDER BY total_relationships DESC
            LIMIT 10
            """,
            "parameters": {"label": "Person", "limit": 10},
        },
        category="analytics",
        validation_rules={
            "limit": "must be a positive integer less than or equal to 100"
        },
    ),
    "temporal_pattern": QueryTemplate(
        name="temporal_pattern",
        description="Analyze temporal patterns in relationship creation",
        query="""
        MATCH (n:$label)-[r:$relationship_type]->()
        WHERE exists(r.$timestamp_property)
        WITH r.$timestamp_property as timestamp,
             datetime(r.$timestamp_property) as dt,
             count(*) as count
        WITH dt.year as year, 
             dt.month as month,
             count
        RETURN year, month, count,
               apoc.agg.statistic(collect(count)) as statistics
        ORDER BY year, month
        """,
        required_labels=set(),
        required_relationships=set(),
        parameter_descriptions={
            "label": "Label of source entities",
            "relationship_type": "Type of relationship to analyze",
            "timestamp_property": "Property containing the timestamp",
        },
        example={
            "query": """
            MATCH (p:Person)-[r:POSTED]->()
            WHERE exists(r.created_at)
            WITH r.created_at as timestamp,
                 datetime(r.created_at) as dt,
                 count(*) as count
            WITH dt.year as year, 
                 dt.month as month,
                 count
            RETURN year, month, count,
                   apoc.agg.statistic(collect(count)) as statistics
            ORDER BY year, month
            """,
            "parameters": {
                "label": "Person",
                "relationship_type": "POSTED",
                "timestamp_property": "created_at",
            },
        },
        category="analytics",
        validation_rules={
            "timestamp_property": "must be a property containing a valid timestamp or datetime"
        },
    ),
    "recommendation": QueryTemplate(
        name="recommendation",
        description="Generate recommendations based on shared patterns",
        query="""
        MATCH (source:$label {$match_prop: $match_value})
        MATCH (source)-[:$through_relationship]->(shared)<-[:$through_relationship]-(recommended:$label)
        WHERE recommended <> source
        AND NOT (source)-[:$existing_relationship]->(recommended)
        WITH recommended,
             count(shared) as shared_count,
             collect(shared) as shared_items
        RETURN recommended {
            .*,
            shared_count: shared_count,
            shared_items: [item in shared_items | item {.*}]
        } as recommendation
        ORDER BY shared_count DESC
        LIMIT $limit
        """,
        required_labels=set(),
        required_relationships=set(),
        parameter_descriptions={
            "label": "Label of entities to find recommendations for",
            "match_prop": "Property to match the source entity",
            "match_value": "Value to match on source entity",
            "through_relationship": "Relationship type to find commonalities",
            "existing_relationship": "Relationship type to exclude existing connections",
            "limit": "Maximum number of recommendations",
        },
        example={
            "query": """
            MATCH (p:Person {email: 'alice@example.com'})
            MATCH (p)-[:LIKES]->(movie)<-[:LIKES]-(recommended:Person)
            WHERE recommended <> p
            AND NOT (p)-[:FOLLOWS]->(recommended)
            WITH recommended,
                 count(movie) as shared_count,
                 collect(movie) as shared_movies
            RETURN recommended {
                .*,
                shared_count: shared_count,
                shared_movies: [movie in shared_movies | movie {.*}]
            } as recommendation
            ORDER BY shared_count DESC
            LIMIT 5
            """,
            "parameters": {
                "label": "Person",
                "match_prop": "email",
                "match_value": "alice@example.com",
                "through_relationship": "LIKES",
                "existing_relationship": "FOLLOWS",
                "limit": 5,
            },
        },
        category="recommendation",
        validation_rules={
            "limit": "must be a positive integer less than or equal to 50"
        },
    ),
}

# Add any additional specialized templates here
ANALYTICS_TEMPLATES = {
    "graph_metrics": QueryTemplate(
        name="graph_metrics",
        query="""
        CALL gds.graph.create.cypher(
            'analysis-graph',
            'MATCH (n:$label) RETURN id(n) AS id',
            'MATCH (n:$label)-[r:$relationship]->(m:$label) RETURN id(n) AS source, id(m) AS target'
        )
        YIELD graphName
        WITH graphName
        CALL gds.degree.stream(graphName)
        YIELD nodeId, score
        WITH nodeId, score
        MATCH (n) WHERE id(n) = nodeId
        RETURN n {.*, degree: score} as node
        ORDER BY score DESC
        LIMIT $limit
        """,
        description="Calculate graph metrics using GDS library",
        required_labels=set(),
        required_relationships=set(),
        parameter_descriptions={
            "label": "Node label to analyze",
            "relationship": "Relationship type to consider",
            "limit": "Maximum number of results"
        },
        example={
            "parameters": {
                "label": "Person",
                "relationship": "FOLLOWS",
                "limit": 10
            }
        },
        category="analytics",
        validation_rules={
            "limit": "must be a positive integer less than or equal to 100"
        }
    )
}

# Combine all templates
QUERY_TEMPLATES = {
    **STANDARD_TEMPLATES,
    **ANALYTICS_TEMPLATES
}
