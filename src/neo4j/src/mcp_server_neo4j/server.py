from typing import Any, Optional
from datetime import datetime
from mcp.types import (
    Resource,
    Prompt,
    PromptArgument,
    GetPromptResult,
    PromptMessage,
    TextContent,
    Tool,
)
from mcp.server import Server
from pydantic import BaseModel, AnyUrl, field_validator
from neo4j import AsyncGraphDatabase, AsyncDriver
from dotenv import load_dotenv
import logging
import os

load_dotenv()
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-server-neo4j")


# Input Models
class QueryParams(BaseModel):
    """Parameters for querying the knowledge graph"""
    context: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "examples": [{
                "context": "technology",
            }]
        }
    }


class ConnectionParams(BaseModel):
    """Parameters for finding connections between entities"""
    concept_a: str
    concept_b: str
    max_depth: int = 3

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "concept_a": "Alice",
                "concept_b": "Bob",
                "max_depth": 3
            }]
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
                {
                    "subject": "Alice",
                    "predicate": "KNOWS",
                    "object": "Bob"
                },
                {
                    "subject": "Neural Networks",
                    "predicate": "IS_TYPE_OF",
                    "object": "Machine Learning"
                },
                {
                    "subject": "Python",
                    "predicate": "USED_FOR",
                    "object": "Data Science"
                }
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
                            "object": "Python"
                        },
                        {
                            "subject": "Python",
                            "predicate": "USED_IN",
                            "object": "Data Science"
                        }
                    ]
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
                    "created_at": "2024-01-01T00:00:00"
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


SCHEMA_SETUP = [
    "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
    "CREATE INDEX type IF NOT EXISTS FOR (e:Entity) ON (e.type)"
]


class Neo4jServer(Server):
    def __init__(self):
        super().__init__("mcp-server-neo4j")
        self.driver: Optional[AsyncDriver] = None

    async def initialize(self, uri: str, auth: tuple):
        self.driver = AsyncGraphDatabase.driver(uri, auth=auth)
        logger.info("Driver initialized")

    async def shutdown(self):
        if self.driver:
            logger.info("Driver shutting down...")
            await self.driver.close()
            logger.info("Driver shutdown complete")

    async def _ensure_context_schema(self, context: str, tx):
        """Ensure schema exists for given context"""
        await tx.run(
            f"""
       MERGE (c:Context {name: $context})
       """,
            context=context,
        )

    async def _store_facts(self, args: Facts) -> StoreFactsResponse:
        """Store facts in the knowledge graph.

        Args:
            args: Facts model containing:
                - context (optional): Context to store facts under
                - facts: list[Fact] of facts to store

        Returns:
            StoreFactsResponse object containing:
                - stored_facts: list[Fact] of store