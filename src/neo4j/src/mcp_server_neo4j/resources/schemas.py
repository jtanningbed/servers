"""
Schema definitions and models for Neo4j database.
Consolidates schemas from schema.py, schemas.py, and examples.py.
"""
from typing import Dict, List, Optional, Any, Set
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

# Schema Definition Models
class PropertyType(str, Enum):
    """Supported property types for node and relationship properties"""
    STRING = "String"
    INTEGER = "Integer"
    FLOAT = "Float"
    BOOLEAN = "Boolean"
    DATE = "Date"
    DATETIME = "DateTime"
    POINT = "Point"
    DURATION = "Duration"
    LIST = "List"

class IndexType(str, Enum):
    """Neo4j index types"""
    BTREE = "BTREE"
    TEXT = "TEXT"
    POINT = "POINT"
    RANGE = "RANGE"
    FULLTEXT = "FULLTEXT"

class PropertyDefinition(BaseModel):
    """Definition for a node or relationship property"""
    name: str = Field(..., description="Name of the property")
    type: PropertyType = Field(..., description="Data type of the property")
    required: bool = Field(default=False, description="Whether the property is required")
    indexed: bool = Field(default=False, description="Whether to create an index on this property")
    index_type: Optional[IndexType] = Field(
        default=None,
        description="Type of index to create if indexed is True"
    )
    default: Optional[Any] = Field(
        default=None,
        description="Default value for the property"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of what this property represents"
    )

class NodeLabelDefinition(BaseModel):
    """Definition for a node label and its properties"""
    label: str = Field(..., description="Label name for the node")
    properties: List[PropertyDefinition] = Field(
        default_factory=list,
        description="Properties that can be set on nodes with this label"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of what this node label represents"
    )

class RelationshipTypeDefinition(BaseModel):
    """Definition for a relationship type and its properties"""
    type: str = Field(..., description="Type name for the relationship")
    properties: List[PropertyDefinition] = Field(
        default_factory=list,
        description="Properties that can be set on relationships of this type"
    )
    source_labels: List[str] = Field(
        ...,
        description="Valid labels for source nodes of this relationship"
    )
    target_labels: List[str] = Field(
        ...,
        description="Valid labels for target nodes of this relationship"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of what this relationship represents"
    )

class SchemaDefinition(BaseModel):
    """Complete schema definition for the graph database"""
    node_labels: List[NodeLabelDefinition] = Field(
        default_factory=list,
        description="Definitions for all node labels in the schema"
    )
    relationship_types: List[RelationshipTypeDefinition] = Field(
        default_factory=list,
        description="Definitions for all relationship types in the schema"
    )


class SchemaSetupResponse(BaseModel):
    """Response model for schema setup operations"""

    created_constraints: List[str] = []  # List of successfully created constraints
    created_indexes: List[str] = []  # List of successfully created indexes
    created_labels: List[str] = []  # List of successfully created label nodes
    warnings: List[str] = []  # Any warnings encountered during setup
    timestamp: datetime = datetime.now()  # When the schema setup was performed

    class Config:
        json_schema_extra = {
            "example": {
                "created_constraints": [
                    "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"
                ],
                "created_indexes": [
                    "CREATE INDEX type IF NOT EXISTS FOR (e:Entity) ON (e.type)"
                ],
                "created_labels": ["Entity", "Context"],
                "warnings": ["Warning: Index 'type' already exists"],
                "timestamp": "2024-03-15T14:30:00",
            }
        }


class CypherQuery(BaseModel):
    """Model for executing custom Cypher queries with parameter binding."""

    query: str = Field(..., description="The Cypher query to execute")
    parameters: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional parameters for query binding"
    )
    description: str = Field(
        ...,
        description="Description of what the query does (helps LLMs understand the purpose)",
    )
    expected_result_type: str = Field(
        ..., description="Description of the expected return format"
    )
    template_name: Optional[str] = Field(
        None, description="Name of the template this query is based on, if any"
    )

    @validator("template_name")
    def validate_template(cls, v):
        if v and v not in QUERY_TEMPLATES:
            raise ValueError(
                f"Unknown template: {v}. Available templates: {list(QUERY_TEMPLATES.keys())}"
            )
        return v

    @classmethod
    def from_template(
        cls, template_name: str, parameters: Optional[Dict[str, Any]] = None
    ) -> "CypherQuery":
        """Create a query from a template"""
        if template_name not in QUERY_TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}")

        template = QUERY_TEMPLATES[template_name]
        return cls(
            query=template["query"],
            parameters=parameters or {},
            description=template["description"],
            expected_result_type="Template-based query results",
            template_name=template_name,
        )


class QueryResponse(BaseModel):
    """Model for query execution results."""

    results: List[Dict[str, Any]] = Field(..., description="Query results")
    total_results: int = Field(..., description="Total number of results returned")
    query_details: Optional[Dict[str, Any]] = Field(
        None, description="Optional query execution details like performance metrics"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    template_used: Optional[str] = Field(
        None, description="Name of the template used, if query was template-based"
    )


class QueryParams(BaseModel):
    """Parameters for querying the knowledge graph"""

    context: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "context": "technology",
                }
            ]
        }
    }


class ConnectionParams(BaseModel):
    """Parameters for finding connections between entities"""

    concept_a: str
    concept_b: str
    max_depth: int = 3

    model_config = {
        "json_schema_extra": {
            "examples": [{"concept_a": "Alice", "concept_b": "Bob", "max_depth": 3}]
        }
    }


class Fact(BaseModel):
    """A single fact represented as a subject-predicate-object triple"""

    subject: str
    predicate: str
    object: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"subject": "Alice", "predicate": "KNOWS", "object": "Bob"},
                {
                    "subject": "Neural Networks",
                    "predicate": "IS_TYPE_OF",
                    "object": "Machine Learning",
                },
                {
                    "subject": "Python",
                    "predicate": "USED_FOR",
                    "object": "Data Science",
                },
            ]
        }
    }


class Facts(BaseModel):
    """A collection of facts with optional context"""

    context: Optional[str] = None
    facts: list[Fact]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "context": "tech_skills",
                    "facts": [
                        {
                            "subject": "Alice",
                            "predicate": "SKILLED_IN",
                            "object": "Python",
                        },
                        {
                            "subject": "Python",
                            "predicate": "USED_IN",
                            "object": "Data Science",
                        },
                    ],
                }
            ]
        }
    }


# Operation Response Models
class ValidationError(BaseModel):
    """Validation error response"""
    error: str
    field: str
    details: str

class Neo4jError(BaseModel):
    """Neo4j operation error response"""
    error: str
    details: str

class Entity(BaseModel):
    """Entity in the graph"""
    name: str
    type: str = "Entity"
    observations: List[Dict[str, Any]] = Field(default_factory=list)

class Relation(BaseModel):
    """Relationship between entities"""
    from_entity: Entity
    to_entity: Entity
    relation_type: str
    context: Optional[str] = None
    created_at: Optional[datetime] = None

class Path(BaseModel):
    """Path between entities"""
    entities: List[Entity]
    relations: List[Relation]
    length: int


class StoreFactsResponse(BaseModel):
    """Response from storing facts in the knowledge graph"""

    stored_facts: list[Fact]
    context: str
    total_stored: int
    created_at: datetime


class ConnectionResponse(BaseModel):
    """Response from finding connections between entities"""

    paths: list[Path]
    start_entity: str
    end_entity: str
    total_paths: int


# Example schemas for different use cases
SOCIAL_NETWORK_SCHEMA = SchemaDefinition(
    node_labels=[
        NodeLabelDefinition(
            label="Person",
            properties=[
                PropertyDefinition(
                    name="name",
                    type=PropertyType.STRING,
                    required=True,
                    indexed=True,
                    index_type=IndexType.TEXT,
                    description="Person's full name",
                ),
                PropertyDefinition(
                    name="email",
                    type=PropertyType.STRING,
                    required=True,
                    indexed=True,
                    description="Person's email address",
                ),
                PropertyDefinition(
                    name="joined_date",
                    type=PropertyType.DATETIME,
                    required=True,
                    description="When the person joined",
                ),
                PropertyDefinition(
                    name="interests",
                    type=PropertyType.LIST,
                    description="List of person's interests",
                ),
            ],
            description="Represents a user in the social network",
        ),
        NodeLabelDefinition(
            label="Post",
            properties=[
                PropertyDefinition(
                    name="content",
                    type=PropertyType.STRING,
                    required=True,
                    index_type=IndexType.FULLTEXT,
                    indexed=True,
                    description="The post content",
                ),
                PropertyDefinition(
                    name="created_at",
                    type=PropertyType.DATETIME,
                    required=True,
                    indexed=True,
                    description="When the post was created",
                ),
                PropertyDefinition(
                    name="likes",
                    type=PropertyType.INTEGER,
                    default=0,
                    description="Number of likes",
                ),
            ],
            description="A post made by a user",
        ),
    ],
    relationship_types=[
        RelationshipTypeDefinition(
            type="FOLLOWS",
            source_labels=["Person"],
            target_labels=["Person"],
            properties=[
                PropertyDefinition(
                    name="since", type=PropertyType.DATETIME, required=True
                )
            ],
            description="Indicates that one person follows another",
        ),
        RelationshipTypeDefinition(
            type="POSTED",
            source_labels=["Person"],
            target_labels=["Post"],
            properties=[],
            description="Connects a person to their posts",
        ),
        RelationshipTypeDefinition(
            type="LIKED",
            source_labels=["Person"],
            target_labels=["Post"],
            properties=[
                PropertyDefinition(name="at", type=PropertyType.DATETIME, required=True)
            ],
            description="Indicates that a person liked a post",
        ),
    ],
)

PROJECT_MANAGEMENT_SCHEMA = SchemaDefinition(
    node_labels=[
        NodeLabelDefinition(
            label="Project",
            properties=[
                PropertyDefinition(
                    name="name",
                    type=PropertyType.STRING,
                    required=True,
                    indexed=True,
                    description="Project name",
                ),
                PropertyDefinition(
                    name="start_date",
                    type=PropertyType.DATE,
                    required=True,
                    description="Project start date",
                ),
                PropertyDefinition(
                    name="end_date",
                    type=PropertyType.DATE,
                    description="Project end date",
                ),
                PropertyDefinition(
                    name="budget", type=PropertyType.FLOAT, description="Project budget"
                ),
            ],
        ),
        NodeLabelDefinition(
            label="Task",
            properties=[
                PropertyDefinition(
                    name="title", type=PropertyType.STRING, required=True, indexed=True
                ),
                PropertyDefinition(
                    name="status",
                    type=PropertyType.STRING,
                    required=True,
                    default="TODO",
                ),
                PropertyDefinition(
                    name="priority", type=PropertyType.INTEGER, default=1
                ),
                PropertyDefinition(name="estimated_hours", type=PropertyType.FLOAT),
            ],
        ),
    ],
    relationship_types=[
        RelationshipTypeDefinition(
            type="CONTAINS",
            source_labels=["Project"],
            target_labels=["Task"],
            properties=[],
            description="Links a project to its tasks",
        ),
        RelationshipTypeDefinition(
            type="DEPENDS_ON",
            source_labels=["Task"],
            target_labels=["Task"],
            properties=[
                PropertyDefinition(
                    name="type",
                    type=PropertyType.STRING,
                    required=True,
                    description="Type of dependency (e.g., 'BLOCKS', 'RELATES_TO')",
                )
            ],
            description="Indicates task dependencies",
        ),
    ],
)

ECOMMERCE_SCHEMA = SchemaDefinition(
    node_labels=[
        NodeLabelDefinition(
            label="Product",
            properties=[
                PropertyDefinition(
                    name="sku",
                    type=PropertyType.STRING,
                    required=True,
                    indexed=True,
                    description="Product SKU"
                ),
                PropertyDefinition(
                    name="name",
                    type=PropertyType.STRING,
                    required=True,
                    indexed=True,
                    index_type=IndexType.TEXT,
                    description="Product name"
                ),
                PropertyDefinition(
                    name="price",
                    type=PropertyType.FLOAT,
                    required=True,
                    description="Product price"
                )
            ]
        ),
        NodeLabelDefinition(
            label="Customer",
            properties=[
                PropertyDefinition(
                    name="id",
                    type=PropertyType.STRING,
                    required=True,
                    indexed=True,
                    description="Customer ID"
                ),
                PropertyDefinition(
                    name="email",
                    type=PropertyType.STRING,
                    required=True,
                    indexed=True,
                    description="Customer email"
                )
            ]
        )
    ],
    relationship_types=[
        RelationshipTypeDefinition(
            type="PURCHASED",
            source_labels=["Customer"],
            target_labels=["Product"],
            properties=[
                PropertyDefinition(
                    name="date",
                    type=PropertyType.DATETIME,
                    required=True,
                    description="Purchase date"
                ),
                PropertyDefinition(
                    name="quantity",
                    type=PropertyType.INTEGER,
                    required=True,
                    description="Quantity purchased"
                )
            ]
        )
    ]
)

# Common query templates with examples
QUERY_TEMPLATES = {
    "node_creation": {
        "query": """
        CREATE (n:$label $properties)
        RETURN n
        """,
        "description": "Create a new node with the given label and properties",
        "example": {
            "query": """
            CREATE (p:Person {
                name: $name,
                email: $email,
                joined_date: datetime()
            }) RETURN p
            """,
            "parameters": {"name": "John Doe", "email": "john@example.com"},
        },
    },
    "relationship_creation": {
        "query": """
        MATCH (a:$label1 {$match1_prop: $match1_value})
        MATCH (b:$label2 {$match2_prop: $match2_value})
        CREATE (a)-[r:$rel_type $rel_props]->(b)
        RETURN type(r) as relationship_type, r as relationship
        """,
        "description": "Create a relationship between two existing nodes",
        "example": {
            "query": """
            MATCH (a:Person {email: $follower_email})
            MATCH (b:Person {email: $followed_email})
            CREATE (a)-[r:FOLLOWS {since: datetime()}]->(b)
            RETURN type(r) as relationship_type, r as relationship
            """,
            "parameters": {
                "follower_email": "john@example.com",
                "followed_email": "jane@example.com",
            },
        },
    },
    "complex_path_search": {
        "query": """
        MATCH path = (start:$start_label)-[*1..$max_depth]-(end:$end_label)
        WHERE start.$match_prop = $match_value
        AND (end:$end_label)
        AND ALL(r IN relationships(path) 
            WHERE type(r) IN $allowed_rels)
        RETURN path,
               length(path) as distance,
               [n IN nodes(path) | labels(n)[0]] as node_types,
               [r IN relationships(path) | type(r)] as relationships
        ORDER BY distance
        LIMIT $limit
        """,
        "description": "Find paths between nodes with specific constraints",
        "example": {
            "query": """
            MATCH path = (p1:Person)-[*1..3]-(p2:Person)
            WHERE p1.email = $email1
            AND p2.email = $email2
            AND ALL(r IN relationships(path) 
                WHERE type(r) IN ['FOLLOWS', 'LIKED'])
            RETURN path,
                   length(path) as distance,
                   [n IN nodes(path) | labels(n)[0]] as node_types,
                   [r IN relationships(path) | type(r)] as relationships
            ORDER BY distance
            LIMIT 5
            """,
            "parameters": {"email1": "john@example.com", "email2": "jane@example.com"},
        },
    },
    "temporal_analysis": {
        "query": """
        MATCH (n:$label)
        WHERE n.$date_field > $start_date
        AND n.$date_field < $end_date
        WITH n,
             datetime(n.$date_field).week as week,
             datetime(n.$date_field).year as year
        RETURN year, week, count(n) as count
        ORDER BY year, week
        """,
        "description": "Analyze time-based patterns in the data",
        "example": {
            "query": """
            MATCH (p:Post)
            WHERE p.created_at > datetime('2024-01-01')
            AND p.created_at < datetime('2024-12-31')
            WITH p,
                 datetime(p.created_at).week as week,
                 datetime(p.created_at).year as year
            RETURN year, week, count(p) as post_count
            ORDER BY year, week
            """,
            "parameters": {},
        },
    },
    "graph_analytics": {
        "query": """
        MATCH (n:$label)
        OPTIONAL MATCH (n)-[r]->()
        WITH n,
             labels(n) as node_labels,
             count(DISTINCT type(r)) as relationship_types,
             count(r) as total_relationships
        RETURN {
            node_info: properties(n),
            labels: node_labels,
            relationship_count: total_relationships,
            relationship_types: relationship_types
        } as node_analytics
        ORDER BY total_relationships DESC
        LIMIT $limit
        """,
        "description": "Analyze node connectivity and relationship patterns",
        "example": {
            "query": """
            MATCH (p:Person)
            OPTIONAL MATCH (p)-[r]->()
            WITH p,
                 labels(p) as node_labels,
                 count(DISTINCT type(r)) as relationship_types,
                 count(r) as total_relationships
            RETURN {
                node_info: properties(p),
                labels: node_labels,
                relationship_count: total_relationships,
                relationship_types: relationship_types
            } as person_analytics
            ORDER BY total_relationships DESC
            LIMIT 10
            """,
            "parameters": {},
        },
    },
    "recommendation_engine": {
        "query": """
        MATCH (source:$label {$match_prop: $match_value})-[r1:$rel_type]->(shared)<-[r2:$rel_type]-(recommended:$label)
        WHERE recommended <> source
        AND NOT (source)-[:$existing_rel_type]->(recommended)
        WITH recommended,
             count(shared) as shared_count,
             collect(shared.$collect_prop) as shared_items
        RETURN recommended.$return_prop as recommended_entity,
               shared_count,
               shared_items
        ORDER BY shared_count DESC
        LIMIT $limit
        """,
        "description": "Generate recommendations based on shared connections or interests",
        "example": {
            "query": """
            MATCH (p:Person {email: $email})-[:LIKED]->(post:Post)<-[:LIKED]-(recommended:Person)
            WHERE recommended <> p
            AND NOT (p)-[:FOLLOWS]->(recommended)
            WITH recommended,
                 count(post) as shared_likes,
                 collect(post.content) as shared_posts
            RETURN recommended.name as recommended_person,
                   shared_likes,
                   shared_posts
            ORDER BY shared_likes DESC
            LIMIT 5
            """,
            "parameters": {"email": "john@example.com"},
        },
    },
}

# Combine all schema templates
SCHEMA_TEMPLATES = {
    "social_network": SOCIAL_NETWORK_SCHEMA,
    "project_management": PROJECT_MANAGEMENT_SCHEMA,
    "ecommerce": ECOMMERCE_SCHEMA
}
