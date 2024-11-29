from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field
from datetime import datetime

class CypherQuery(BaseModel):
    """Model for executing custom Cypher queries with parameter binding."""
    query: str = Field(..., description="The Cypher query to execute")
    parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional parameters for query binding"
    )
    description: str = Field(
        ..., 
        description="Description of what the query does (helps LLMs understand the purpose)"
    )
    expected_result_type: str = Field(
        ...,
        description="Description of the expected return format"
    )

class QueryResponse(BaseModel):
    """Model for query execution results."""
    results: List[Dict[str, Any]] = Field(..., description="Query results")
    total_results: int = Field(..., description="Total number of results returned")
    query_details: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional query execution details like performance metrics"
    )
    timestamp: datetime = Field(default_factory=datetime.now)

class RelationshipDefinition(BaseModel):
    """Model for creating typed relationships between nodes."""
    source_type: str = Field(..., description="Type/label of the source node")
    target_type: str = Field(..., description="Type/label of the target node")
    relationship_type: str = Field(..., description="Type of relationship to create")
    source_properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Properties to match source node"
    )
    target_properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Properties to match target node"
    )
    relationship_properties: Optional[Dict[str, Any]] = Field(
        None,
        description="Properties to set on the relationship"
    )

# Common query templates to help guide the LLM
QUERY_TEMPLATES = {
    "find_relationships": {
        "query": """
        MATCH (a)-[r]->(b)
        WHERE a.name = $name
        RETURN type(r) as relationship, collect({
            node: b.name,
            properties: properties(r)
        }) as connections
        """,
        "description": "Find all relationships and connected nodes for a given node",
        "example_params": {"name": "John"}
    },

    "property_based_search": {
        "query": """
        MATCH (n)
        WHERE n[$property] $operator $value
        RETURN n
        """,
        "description": "Search for nodes based on property values",
        "example_params": {
            "property": "age",
            "operator": ">",
            "value": 30
        }
    },

    "path_analysis": {
        "query": """
        MATCH path = (start)-[*1..{max_depth}]-(end)
        WHERE start.name = $start_name AND end.name = $end_name
        RETURN path,
               length(path) as path_length,
               [n in nodes(path) | n.name] as node_names,
               [r in relationships(path) | type(r)] as relationship_types
        """,
        "description": "Analyze paths between two nodes including path details",
        "example_params": {
            "start_name": "Alice",
            "end_name": "Bob",
            "max_depth": 3
        }
    },

    "relationship_analytics": {
        "query": """
        MATCH (n)-[r]->(m)
        WHERE type(r) = $relationship_type
        RETURN type(r) as relationship,
               count(*) as total_count,
               collect(distinct labels(n)) as source_types,
               collect(distinct labels(m)) as target_types,
               avg(toFloat(r.weight)) as avg_weight
        """,
        "description": "Analyze relationship patterns and metrics",
        "example_params": {"relationship_type": "FOLLOWS"}
    }
}