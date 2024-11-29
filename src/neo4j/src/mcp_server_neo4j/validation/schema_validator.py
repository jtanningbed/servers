from typing import Dict, List, Optional, Set
from pydantic import BaseModel
from neo4j import AsyncGraphDatabase, AsyncDriver
import logging

logger = logging.getLogger(__name__)

class SchemaValidationError(Exception):
    """Custom exception for schema validation errors"""
    pass

class SchemaValidator:
    """Validates Neo4j schema operations and ensures consistency"""
    
    def __init__(self, driver: AsyncDriver):
        self.driver = driver
        
    async def get_current_schema(self) -> Dict:
        """Fetch current database schema information"""
        async with self.driver.session() as session:
            # Get node labels and their properties
            result = await session.run("""
                CALL apoc.meta.nodeTypeProperties()
                YIELD nodeType, propertyName, propertyTypes
                RETURN collect({
                    nodeType: nodeType,
                    propertyName: propertyName,
                    propertyTypes: propertyTypes
                }) as schema
            """)
            node_schema = (await result.single())["schema"]
            
            # Get relationship types and their properties
            result = await session.run("""
                CALL apoc.meta.relTypeProperties()
                YIELD relType, propertyName, propertyTypes
                RETURN collect({
                    relType: relType,
                    propertyName: propertyName,
                    propertyTypes: propertyTypes
                }) as schema
            """)
            rel_schema = (await result.single())["schema"]
            
            return {
                "nodes": node_schema,
                "relationships": rel_schema
            }

    async def validate_query_against_schema(
        self, 
        query: str,
        schema: Dict,
        parameters: Optional[Dict] = None
    ) -> List[str]:
        """
        Validate a Cypher query against the current schema
        Returns a list of warnings/suggestions
        """
        warnings = []
        
        # Extract labels and relationship types from the query using EXPLAIN
        async with self.driver.session() as session:
            try:
                result = await session.run(f"EXPLAIN {query}", parameters or {})
                plan = await result.consume()
                
                # Extract identifiers and operators from the query plan
                identifiers = set()
                operators = set()
                
                def extract_from_plan(plan_dict):
                    if "identifiers" in plan_dict:
                        identifiers.update(plan_dict["identifiers"])
                    if "operatorType" in plan_dict:
                        operators.add(plan_dict["operatorType"])
                    for child in plan_dict.get("children", []):
                        extract_from_plan(child)
                
                extract_from_plan(plan.plan)
                
                # Check for missing indexes
                if "NodeByLabelScan" in operators:
                    warnings.append(
                        "Query uses label scan. Consider adding indexes for better performance."
                    )
                
                # Check for cartesian products
                if "CartesianProduct" in operators:
                    warnings.append(
                        "Query includes cartesian product which may impact performance."
                    )
                
                # Validate labels against schema
                schema_labels = {node["nodeType"] for node in schema["nodes"]}
                query_labels = {
                    ident.split(":")[1]
                    for ident in identifiers
                    if ":" in ident
                }
                
                unknown_labels = query_labels - schema_labels
                if unknown_labels:
                    warnings.append(
                        f"Query references unknown labels: {unknown_labels}"
                    )
                
            except Exception as e:
                warnings.append(f"Could not validate query: {str(e)}")
        
        return warnings

    async def validate_template_compatibility(
        self,
        template_name: str,
        template_query: str,
        required_labels: Set[str],
        required_relationship_types: Set[str]
    ) -> List[str]:
        """
        Validate that a template is compatible with the current schema
        Returns a list of compatibility issues
        """
        current_schema = await self.get_current_schema()
        issues = []
        
        # Check required labels
        schema_labels = {
            node["nodeType"] 
            for node in current_schema["nodes"]
        }
        missing_labels = required_labels - schema_labels
        if missing_labels:
            issues.append(
                f"Template requires labels that don't exist in schema: {missing_labels}"
            )
            
        # Check required relationship types
        schema_rel_types = {
            rel["relType"]
            for rel in current_schema["relationships"]
        }
        missing_rels = required_relationship_types - schema_rel_types
        if missing_rels:
            issues.append(
                f"Template requires relationship types that don't exist in schema: {missing_rels}"
            )
            
        # Validate the template query itself
        query_warnings = await self.validate_query_against_schema(
            template_query,
            current_schema
        )
        if query_warnings:
            issues.extend([
                f"Template query warning: {warning}"
                for warning in query_warnings
            ])
            
        return issues

    async def validate_schema_changes(
        self,
        new_labels: Set[str],
        new_relationship_types: Set[str],
        new_indexes: List[Dict]
    ) -> List[str]:
        """
        Validate proposed schema changes
        Returns a list of potential issues or conflicts
        """
        current_schema = await self.get_current_schema()
        issues = []
        
        # Check for label conflicts
        current_labels = {
            node["nodeType"]
            for node in current_schema["nodes"]
        }
        conflicting_labels = new_labels & current_labels
        if conflicting_labels:
            issues.append(
                f"Labels already exist in schema: {conflicting_labels}"
            )
            
        # Check for relationship type conflicts
        current_rel_types = {
            rel["relType"]
            for rel in current_schema["relationships"]
        }
        conflicting_rels = new_relationship_types & current_rel_types
        if conflicting_rels:
            issues.append(
                f"Relationship types already exist in schema: {conflicting_rels}"
            )
            
        # Validate new indexes
        async with self.driver.session() as session:
            result = await session.run("SHOW INDEXES")
            existing_indexes = await result.data()
            
            for new_index in new_indexes:
                for existing in existing_indexes:
                    if (
                        existing["labelsOrTypes"] == new_index["labels"] and
                        existing["properties"] == new_index["properties"]
                    ):
                        issues.append(
                            f"Index already exists for {new_index['labels']} on {new_index['properties']}"
                        )
                        
        return issues