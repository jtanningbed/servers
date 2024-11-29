from typing import Dict, Any, List
from mcp.types import Resource, ResourceTemplate
from ..validation.schema_validator import SchemaValidator
from .templates import QUERY_TEMPLATES
import json

# Cypher query standard resources
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
            mime_type="text/plain",
        ),
    ]
}

# Dynamic Cypher query resource templates
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

# Static Resources for Neo4j templates and schemas
TEMPLATE_RESOURCES = {
    "contents": [
        Resource(
            uri=AnyUrl("neo4j://templates/queries"),
            title="Available Query Templates",
            description="List of pre-defined Cypher query templates with examples and validation rules", 
            mime_type="application/json"
        ),
        Resource(
            uri=AnyUrl("neo4j://templates/schemas"),
            title="Schema Templates",
            description="Example schema definitions for common use cases", 
            mime_type="application/json"
        ),
        Resource(
            uri=AnyUrl("neo4j://templates/analytics"),
            title="Analytics Templates",
            description="Templates for common graph analytics patterns", 
            mime_type="application/json"
        ),
        Resource(
            uri=AnyUrl("neo4j://templates/recommendations"),
            title="Recommendation Templates",
            description="Templates for building recommendation systems", 
            mime_type="application/json"
        )
    ]
}

TEMPLATE_RESOURCE_TEMPLATES = {
    "contents": [
        ResourceTemplate(
            uri_template="neo4j://templates/queries/{/category}",
            title="Query Templates by Category",
            description="Access query templates filtered by category",
            mime_type="application/json"
        ),
        ResourceTemplate(
            uri_template="neo4j://templates/schemas/{/domain}",
            title="Domain-Specific Schema Templates",
            description="Access schema templates for specific domains",
            mime_type="application/json"
        )
    ]
}


class ResourceHandler:
    """Handler for Templates and Resources"""
    def __init__(self, driver: AsyncDriver):
        self.driver = driver
        self.schema_validator = SchemaValidator(driver)

    async def handle_template_resource(self, uri: str) -> str:
        """Handle requests for template resources"""
        if uri == "neo4j://templates/queries":
            return json.dumps({
                name: {
                    "description": template.description,
                    "category": template.category,
                    "parameters": template.parameter_descriptions,
                    "example": template.example,
                    "validation_rules": template.validation_rules
                }
                for name, template in QUERY_TEMPLATES.items()
            }, indent=2)

        elif uri.startswith("neo4j://templates/queries/"):
            category = uri.split("/")[-1]
            return json.dumps({
                name: {
                    "description": template.description,
                    "parameters": template.parameter_descriptions,
                    "example": template.example
                }
                for name, template in QUERY_TEMPLATES.items()
                if template.category == category
            }, indent=2)

        elif uri == "neo4j://templates/analytics":
            return json.dumps({
                name: {
                    "description": template.description,
                    "parameters": template.parameter_descriptions,
                    "example": template.example
                }
                for name, template in QUERY_TEMPLATES.items()
                if template.category == "analytics"
            }, indent=2)

        elif uri == "neo4j://templates/recommendations":
            return json.dumps({
                name: {
                    "description": template.description,
                    "parameters": template.parameter_descriptions,
                    "example": template.example
                }
                for name, template in QUERY_TEMPLATES.items()
                if template.category == "recommendation"
            }, indent=2)

        raise ValueError(f"Unknown template resource: {uri}")

    async def validate_template(self, template_name: str, parameters: Dict[str, Any]) -> List[str]:
        """Validate template parameters and compatibility with current schema"""
        if template_name not in QUERY_TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}")

        template = QUERY_TEMPLATES[template_name]

        # Validate parameters
        issues = []
        for param, rule in template.validation_rules.items():
            if param in parameters:
                try:
                    # Apply validation rule
                    if "must be one of" in rule:
                        allowed = rule.split(": ")[1].split(", ")
                        if str(parameters[param]) not in allowed:
                            issues.append(f"Parameter '{param}' {rule}")
                    elif "must be a positive integer" in rule:
                        value = int(parameters[param])
                        if value <= 0:
                            issues.append(f"Parameter '{param}' must be positive")
                        if "less than or equal to" in rule:
                            limit = int(rule.split("less than or equal to ")[1])
                            if value > limit:
                                issues.append(f"Parameter '{param}' must be <= {limit}")
                except (ValueError, TypeError):
                    issues.append(f"Invalid value for parameter '{param}'")

        # Check schema compatibility
        schema_issues = await self.schema_validator.validate_template_compatibility(
            template_name,
            template.query,
            template.required_labels,
            template.required_relationships
        )
        issues.extend(schema_issues)

        return issues

    async def handle_neo4j_resource(self, uri: str) -> str:
        """Handle requests for schema resources"""
        async with self.driver.session() as session:  
            if uri == "neo4j://schema/nodes":
                result = await session.run(
                    """
                CALL apoc.meta.nodeTypeProperties()
                YIELD nodeType, nodeLabels, propertyName, propertyTypes, mandatory, propertyObservations, totalObservations
                RETURN collect({
                    nodeType: nodeType,
                    nodeLabels: nodeLabels,
                    propertyName: propertyName,
                    propertyTypes: propertyTypes,
                    mandatory: mandatory,
                    propertyObservations: propertyObservations,
                    totalObservations: totalObservations
                }) AS schema
                """
                )
                data = await result.single()
                return json.dumps(data["schema"]) if data else "[]"

            elif uri_str == "neo4j://schema/relationships":
                result = await session.run(
                    """
                CALL apoc.meta.relTypeProperties()
                YIELD relType, propertyName, propertyTypes
                RETURN collect({
                    type: relType,
                    property: propertyName,
                    types: propertyTypes
                }) as schema
                """
                )
                data = await result.single()
                return json.dumps(data["schema"])

            elif uri_str == "neo4j://schema/indexes":
                result = await session.run(
                    """
                    SHOW INDEXES
                    YIELD name, labelsOrTypes, properties, type
                    RETURN collect({
                        name: name,
                        labels: labelsOrTypes,
                        properties: properties,
                        type: type
                    }) as indexes
                """
                )
                data = await result.single()
                return json.dumps(data["indexes"])

            # Query resources
            elif uri_str == "neo4j://queries/slow":
                # Assuming we have a method to fetch slow query logs
                logger.info("Not implemented yet.")
                return "Not implemented yet."

            # Statistics resources
            elif uri_str == "neo4j://stats/memory":
                # Using system commands instead of dbms
                result = await session.run(
                    """
                    SHOW SETTINGS YIELD name, value 
                    WHERE name CONTAINS 'memory' OR name CONTAINS 'heap'
                    RETURN name, value
                """
                )
                data = await result.single()
                return json.dumps(data)

            elif uri_str == "neo4j://stats/transactions":
                # Using system transactions info
                result = await session.run(
                    """
                    CALL apoc.monitor.tx()
                    YIELD rolledBackTx, peakTx, lastTxId, currentOpenedTx, totalOpenedTx, totalTx
                    RETURN {
                        rolledBackTx: rolledBackTx,
                        peakTx: peakTx,
                        lastTxId: lastTxId,
                        currentOpenedTx: currentOpenedTx,
                        totalOpenedTx: totalOpenedTx,
                        totalTx: totalTx
                    } as stats
                """
                )
                data = await result.single()
                return json.dumps(data["stats"])

            # Label count
            elif uri_str.startswith("neo4j://labels") and uri_str.endswith(
                "/count"
            ):
                result = await session.run(
                    """
                    CALL apoc.meta.stats() 
                    YIELD labelCount 
                    RETURN labelCount as count
                """
                )
                data = await result.single()
                return str(data["count"])

            # Template resources handling
            elif uri_str.startswith("neo4j://queries/active"):
                query_id = uri_str.split("/")[-2]
                result = await session.run(
                    """
                    SHOW TRANSACTIONS
                    YIELD transactionId, currentQueryId, currentQuery, status, elapsedTime
                    WHERE currentQueryId <> $currentQueryId
                    RETURN collect({
                        transactionId: transactionId,
                        queryId: currentQueryId,
                        query: currentQuery,
                        status: status,
                        elapsedTime: elapsedTime
                    }) as queries
                """,
                    {
                        "currentQueryId": (
                            query_id if query_id else "current-query-id"
                        )
                    },
                )
                data = await result.single()
                return json.dumps(data["queries"])

            # Node count by label
            elif uri_str.startswith("neo4j://nodes/") and uri_str.endswith(
                "/count"
            ):
                label = uri_str.split("/")[-2]
                result = await session.run(
                    "CALL apoc.meta.stats() YIELD labels RETURN labels[$label] as count",
                    {"label": label},
                )
                data = await result.single()
                return str(data["count"])

            # Relationship count by type
            elif uri_str.startswith("neo4j://relationships/") and uri_str.endswith(
                "/count"
            ):
                rel_type = uri_str.split("/")[-2]
                result = await session.run(
                    "CALL apoc.meta.stats() YIELD relTypesCount RETURN relTypesCount[$rel_type] as count",
                    {"rel_type": rel_type},
                )
                data = await result.single()
                return str(data["count"])

        raise ValueError(f"Resource not found: {uri_str}")

    async def handle_tool_resource(self, server: Neo4jServer, uri: AnyUrl) -> List[str]:
        try:
            tool_handlers = {
                "store-facts": server._store_facts,
                "query-knowledge": server._query_knowledge,
                "find-connections": server._find_connections,
                "execute-cypher": server.execute_cypher,
            }

            handler = tool_handlers.get(name)
            if not handler:
                raise ValueError(f"Unknown tool: {name}")

            # Validate input
            model_map = {
                "store-facts": Facts,
                "query-knowledge": QueryParams,
                "find-connections": ConnectionParams,
                "execute-cypher": CypherQuery
            }

            input_model = model_map[name]
            try:
                validated_args = input_model.model_validate(arguments or {})
            except ValidationError as e:
                return [await server.format_error(e)]

            # Execute handler
            try:
                result = await handler(validated_args)
                return [await server.format_response(result)]
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                return [await server.format_error(e)]

        except Exception as e:
            logger.error(f"Unexpected error in tool handler: {e}")
            return [await server.format_error(e)]

    async def list_tools() -> list[Tool]:
        """List available graph operation tools"""
        return [
            Tool(
                name="store-facts",
                description="""Store new facts in the knowledge graph. 
                Facts are represented as subject-predicate-object triples,
                optionally grouped under a context.""",
                inputSchema=Facts.model_json_schema(),
            ),
            Tool(
                name="query-knowledge",
                description="Query relationships in the knowledge graph by context",
                inputSchema=QueryParams.model_json_schema(),
            ),
            Tool(
                name="find-connections",
                description="Find paths between two entities in the knowledge graph",
                inputSchema=ConnectionParams.model_json_schema(),
            ),
            Tool(
                name="execute-cypher",
                description="Execute a custom Cypher query with parameter binding",
                inputSchema=CypherQuery.model_json_schema(),
            ),
        ]
