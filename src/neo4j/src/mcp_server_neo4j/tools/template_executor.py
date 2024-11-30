from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from neo4j import AsyncDriver
import logging
from ..resources.templates import QUERY_TEMPLATES, QueryTemplate
from ..validation.schema_validator import SchemaValidator

logger = logging.getLogger(__name__)

class TemplateExecutionRequest(BaseModel):
    """Request to execute a query template"""
    template_name: str
    parameters: Dict[str, Any]
    customizations: Optional[Dict[str, Any]] = None

class TemplateExecutionResponse(BaseModel):
    """Response from template execution"""
    results: List[Dict[str, Any]]
    template_used: str
    execution_stats: Optional[Dict[str, Any]] = None
    warnings: List[str] = []

class TemplateExecutor:
    """Executes query templates with validation and customization"""

    def __init__(self, driver: AsyncDriver, validator: SchemaValidator):
        self.driver = driver
        self.validator = validator

    async def execute_template(
        self,
        request: TemplateExecutionRequest
    ) -> TemplateExecutionResponse:
        """Execute a query template with the given parameters"""

        # Validate template exists
        if request.template_name not in QUERY_TEMPLATES:
            raise ValueError(f"Unknown template: {request.template_name}")

        template = QUERY_TEMPLATES[request.template_name]

        # Validate parameters and schema compatibility
        validation_issues = await self.validator.validate_template_compatibility(
            request.template_name,
            template.query,
            template.required_labels,
            template.required_relationships
        )

        # Prepare query
        query = template.query
        parameters = request.parameters.copy()

        # Apply customizations if provided
        if request.customizations:
            if "additional_where" in request.customizations:
                # Add custom WHERE clauses
                where_clause = request.customizations["additional_where"]
                if "WHERE" in query:
                    query = query.replace(
                        "WHERE",
                        f"WHERE {where_clause} AND"
                    )
                else:
                    # Find appropriate place to insert WHERE clause
                    match_end = query.find(")")
                    if match_end != -1:
                        query = (
                            query[:match_end + 1] +
                            f"\nWHERE {where_clause}" +
                            query[match_end + 1:]
                        )

            if "order_by" in request.customizations:
                # Add or replace ORDER BY
                order_by = request.customizations["order_by"]
                if "ORDER BY" in query:
                    # Replace existing ORDER BY
                    query = query[:query.find("ORDER BY")] + f"ORDER BY {order_by}"
                else:
                    # Add new ORDER BY before LIMIT if it exists
                    if "LIMIT" in query:
                        query = query.replace(
                            "LIMIT",
                            f"ORDER BY {order_by}\nLIMIT"
                        )
                    else:
                        query += f"\nORDER BY {order_by}"

            if "limit" in request.customizations:
                # Add or replace LIMIT
                limit = request.customizations["limit"]
                if "LIMIT" in query:
                    query = query[:query.find("LIMIT")] + f"LIMIT {limit}"
                else:
                    query += f"\nLIMIT {limit}"

        # Execute query
        try:
            async with self.driver.session() as session:
                result = await session.run(query, parameters)

                # Get execution stats if available
                execution_stats = None
                try:
                    summary = await result.consume()
                    execution_stats = {
                        "counters": summary.counters,
                        "database": summary.database,
                        "query_type": summary.query_type,
                        "plan": summary.plan
                    }
                except:
                    pass  # Ignore stats collection errors

                # Get results
                data = await result.data()

                return TemplateExecutionResponse(
                    results=data,
                    template_used=request.template_name,
                    execution_stats=execution_stats,
                    warnings=validation_issues
                )

        except Exception as e:
            logger.error(f"Template execution error: {str(e)}")
            raise


class QueryBuilder:
    """Helper class for building Cypher queries programmatically."""

    @staticmethod
    def create_node_query(label: str, properties: Dict[str, Any]) -> CypherQuery:
        """Build a query to create a node"""
        return CypherQuery.from_template(
            "node_creation", parameters={"label": label, "properties": properties}
        )

    @staticmethod
    def create_relationship_query(rel_def: RelationshipDefinition) -> CypherQuery:
        """Build a query to create a relationship"""
        return CypherQuery.from_template(
            "relationship_creation",
            parameters={
                "label1": rel_def.source_type,
                "label2": rel_def.target_type,
                "match1_prop": list(rel_def.source_properties.keys())[0],
                "match1_value": list(rel_def.source_properties.values())[0],
                "match2_prop": list(rel_def.target_properties.keys())[0],
                "match2_value": list(rel_def.target_properties.values())[0],
                "rel_type": rel_def.relationship_type,
                "rel_props": rel_def.relationship_properties or {},
            },
        )

    @staticmethod
    def find_paths_query(
        start_label: str,
        end_label: str,
        match_property: str,
        match_value: Any,
        allowed_relationships: List[str],
        max_depth: int = 3,
        limit: int = 5,
    ) -> CypherQuery:
        """Build a query to find paths between nodes"""
        return CypherQuery.from_template(
            "complex_path_search",
            parameters={
                "start_label": start_label,
                "end_label": end_label,
                "match_prop": match_property,
                "match_value": match_value,
                "allowed_rels": allowed_relationships,
                "max_depth": max_depth,
                "limit": limit,
            },
        )

    @staticmethod
    def recommendation_query(
        label: str,
        match_property: str,
        match_value: Any,
        relationship_type: str,
        existing_relationship_type: str,
        collect_property: str,
        return_property: str,
        limit: int = 5,
    ) -> CypherQuery:
        """Build a query for generating recommendations"""
        return CypherQuery.from_template(
            "recommendation_engine",
            parameters={
                "label": label,
                "match_prop": match_property,
                "match_value": match_value,
                "rel_type": relationship_type,
                "existing_rel_type": existing_relationship_type,
                "collect_prop": collect_property,
                "return_prop": return_property,
                "limit": limit,
            },
        )
