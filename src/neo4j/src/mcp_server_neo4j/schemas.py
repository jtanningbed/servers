from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Input Models
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


# Output Models
class Entity(BaseModel):
    name: str
    type: str
    observations: list[str] = []


class Relation(BaseModel):
    from_entity: Entity
    to_entity: Entity
    relation_type: str
    context: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "from_entity": {"name": "Alice", "type": "Person"},
                    "to_entity": {"name": "Bob", "type": "Person"},
                    "relation_type": "KNOWS",
                    "context": "social",
                    "created_at": "2024-01-01T00:00:00",
                }
            ]
        }
    }


class StoreFactsResponse(BaseModel):
    """Response from storing facts in the knowledge graph"""

    stored_facts: list[Fact]
    context: str
    total_stored: int
    created_at: datetime


class QueryResponse(BaseModel):
    """Response from querying the knowledge graph"""

    relations: list[Relation]
    context: Optional[str] = None
    total_found: int = 0


class Path(BaseModel):
    """A path between two entities"""

    entities: list[Entity]
    relations: list[Relation]
    length: int


class ConnectionResponse(BaseModel):
    """Response from finding connections between entities"""

    paths: list[Path]
    start_entity: str
    end_entity: str
    total_paths: int


# Errors
class Neo4jError(BaseModel):
    """Error response for Neo4j operations"""

    error: str
    details: Optional[str] = None
    context: Optional[dict] = None


class ValidationError(BaseModel):
    """Error response for input validation failures"""

    error: str
    field: str
    details: str
