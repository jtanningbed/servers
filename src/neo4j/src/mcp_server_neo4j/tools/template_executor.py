from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from neo4j import AsyncDriver
import logging
from ..resources.templates import QUERY_TEMPLATES, QueryTemplate
from ..validation.schema_validator import SchemaValidator
from ..resources.schemas import CypherQuery, RelationshipTypeDefinition, QueryResponse

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
    def __init__(self, driver: AsyncDriver, schema_validator: SchemaValidator):
        self.driver = driver
        self.schema_validator = schema_validator
        self._loaded_templates: Dict[str, QueryTemplate] = {}

    async def initialize(self):
        """Initialize the template executor and validate templates against schema"""
        try:
            # Load and verify templates
            for name, template in QUERY_TEMPLATES.items():
                try:
                    # Verify template against schema
                    if self.schema_validator:
                        # Validate template compatibility with schema
                        schema_issues = (
                            await self.schema_validator.validate_template_compatibility(
                                name,
                                template.query,
                                template.required_labels,
                                template.required_relationships,
                            )
                        )
                        if schema_issues:
                            logger.warning(
                                f"Template {name} has schema compatibility issues: {schema_issues}"
                            )
                            continue

                    # Verify query syntax
                    async with self.driver.session() as session:
                        # Create dummy parameters based on parameter descriptions
                        dummy_params = self._create_dummy_params(template)
                        await session.run(f"EXPLAIN {template.query}", dummy_params)
                        self._loaded_templates[name] = template
                        logger.info(f"Successfully loaded template: {name}")
                except Exception as e:
                    logger.warning(f"Failed to validate template {name}: {e}")

            logger.info(
                f"Template executor initialized with {len(self._loaded_templates)} valid templates"
            )
        except Exception as e:
            logger.error(f"Failed to initialize template executor: {e}")
            raise

    def _create_dummy_params(self, template: QueryTemplate) -> Dict[str, Any]:
        """Create dummy parameters for template validation"""
        dummy_params = {}
        for param_name, param_desc in template.parameter_descriptions.items():
            # Basic type inference from description
            if "number" in param_desc.lower() or "count" in param_desc.lower():
                dummy_params[param_name] = 0
            elif "date" in param_desc.lower():
                dummy_params[param_name] = "2024-01-01"
            elif "list" in param_desc.lower() or "array" in param_desc.lower():
                dummy_params[param_name] = []
            else:
                dummy_params[param_name] = "dummy_value"
        return dummy_params

    async def execute(
        self, template_name: str, parameters: Dict[str, Any]
    ) -> QueryResponse:
        """Execute a template with the given parameters"""
        if template_name not in self._loaded_templates:
            raise ValueError(f"Template {template_name} not found or failed validation")

        template = self._loaded_templates[template_name]

        # Additional parameter validation if needed
        if self.schema_validator:
            await self.schema_validator.validate_template_parameters(
                template_name, parameters
            )

        async with self.driver.session() as session:
            result = await session.run(template.query, parameters)
            data = await result.data()

            return QueryResponse(
                results=data, total_results=len(data), template_used=template_name
            )


class QueryBuilder:
    """Helper class for building Cypher queries programmatically."""

    @staticmethod
    def create_node_query(label: str, properties: Dict[str, Any]) -> CypherQuery:
        """Build a query to create a node"""
        return CypherQuery.from_template(
            "node_creation", parameters={"label": label, "properties": properties}
        )

    @staticmethod
    def create_relationship_query(rel_def: RelationshipTypeDefinition) -> CypherQuery:
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
