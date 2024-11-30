from typing import List, Dict, Any, Optional
from mcp.types import Resource, ResourceTemplate, Tool, TextContent
from neo4j import AsyncDriver
from datetime import datetime
import json
import logging

from ..validation.schema_validator import SchemaValidator
from .templates import QUERY_TEMPLATES, QueryTemplate, QueryResponse
from . import (
    RESOURCES,
    RESOURCE_TEMPLATES,
    TEMPLATE_RESOURCES,
    TEMPLATE_RESOURCE_TEMPLATES
)
from .schemas import (
    # Core operation schemas
    Facts,
    QueryParams,
    ConnectionParams,
    StoreFactsResponse,
    QueryResponse as GraphQueryResponse,
    ConnectionResponse,
    Path,
    # Enhanced operation schemas
    CypherQuery,
    ValidationError
)

logger = logging.getLogger(__name__)


class ResourceHandler:
    def __init__(
        self,
        driver: AsyncDriver,
        schema_validator: SchemaValidator,
        template_executor: TemplateExecutor,
    ):
        self.driver = driver
        self.schema_validator = schema_validator
        self.template_executor = template_executor
        self._resources = {**RESOURCES, **TEMPLATE_RESOURCES}
        self._resource_templates = {**RESOURCE_TEMPLATES, **TEMPLATE_RESOURCE_TEMPLATES}

    async def initialize(self):
        """Initialize handler and verify components"""
        # Verify database connection
        async with self.driver.session() as session:
            try:
                await session.run("RETURN 1")
                logger.info("Database connection verified")
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                raise

        # Initialize schema validator
        await self.schema_validator.initialize()

        # Initialize template executor
        await self.template_executor.initialize()

        logger.info("ResourceHandler initialized successfully")

    async def setup_schema(self, schema: SchemaDefinition) -> SchemaSetupResponse:
        """Set up the database schema based on the provided definition"""
        response = SchemaSetupResponse()

        async with self.driver.session() as session:
            # Create constraints
            for constraint in schema.constraints:
                try:
                    await session.run(constraint)
                    response.created_constraints.append(constraint)
                except Exception as e:
                    response.warnings.append(f"Error creating constraint: {str(e)}")

            # Create indices
            for index in schema.indices:
                try:
                    await session.run(index)
                    response.created_indexes.append(index)
                except Exception as e:
                    response.warnings.append(f"Error creating index: {str(e)}")

            # Create label nodes
            for label_def in schema.node_labels:
                try:
                    query = """
                    MERGE (l:NodeLabel {name: $name})
                    SET l.description = $description
                    """
                    await session.run(
                        query,
                        {"name": label_def.label, "description": label_def.description},
                    )
                    response.created_labels.append(label_def.label)
                except Exception as e:
                    response.warnings.append(
                        f"Error creating label node {label_def.label}: {str(e)}"
                    )

        # Record setup timestamp
        response.timestamp = datetime.now()
        return response

    async def list_tools(self) -> List[Tool]:
        """List all available tools"""
        # Core operation tools
        tools = [
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
            # Enhanced operation tools
            Tool(
                name="execute-cypher",
                description="Execute a custom Cypher query with parameter binding",
                inputSchema=CypherQuery.model_json_schema(),
            )
        ]

        # Add template-based tools
        for name, template in QUERY_TEMPLATES.items():
            tool_schema = {
                "type": "object",
                "properties": {
                    param: {"type": "string", "description": desc}
                    for param, desc in template.parameter_descriptions.items()
                },
                "required": list(template.parameter_descriptions.keys())
            }

            tools.append(Tool(
                name=f"template.{name}",
                description=template.description,
                inputSchema=tool_schema
            ))

        return tools

    async def handle_call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> List[TextContent]:
        """Handle tool execution with routing to appropriate handler"""
        try:
            if name.startswith("template."):
                # Handle template-based tools
                return await self._handle_template_tool(name.split(".", 1)[1], arguments or {})
            elif name in ["store-facts", "query-knowledge", "find-connections"]:
                # Handle core graph operations
                return await self._handle_graph_tool(name, arguments or {})
            elif name == "execute-cypher":
                # Handle direct Cypher execution
                return await self._handle_cypher_tool(arguments or {})
            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            logger.error(f"Tool execution error: {str(e)}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": e.__class__.__name__,
                    "details": str(e)
                }, indent=2)
            )]

    async def _handle_graph_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle core graph operations"""
        model_map = {
            "store-facts": Facts,
            "query-knowledge": QueryParams,
            "find-connections": ConnectionParams
        }

        handlers = {
            "store-facts": self._store_facts,
            "query-knowledge": self._query_knowledge,
            "find-connections": self._find_connections
        }

        validated_args = model_map[name].model_validate(arguments)
        result = await handlers[name](validated_args)

        return [TextContent(
            type="text",
            text=result.model_dump_json(indent=2)
        )]

    async def _handle_template_tool(self, template_name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle template-based operations"""
        if template_name not in QUERY_TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}")

        template = QUERY_TEMPLATES[template_name]

        # Validate and execute template
        validation_issues = await self.validate_template(template_name, arguments)
        if validation_issues:
            raise ValidationError(field="parameters", details="\n".join(validation_issues))

        async with self.driver.session() as session:
            result = await session.run(template.query, arguments)
            data = await result.data()

            response = QueryResponse(
                results=data,
                total_results=len(data),
                timestamp=datetime.now(),
                template_used=template_name
            )

            return [TextContent(
                type="text",
                text=response.model_dump_json(indent=2)
            )]

    async def _handle_cypher_tool(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle direct Cypher query execution"""
        query = CypherQuery.model_validate(arguments)
        await self.schema_validator.validate_query(query)

        async with self.driver.session() as session:
            result = await session.run(query.query, query.parameters or {})
            data = await result.data()

            response = QueryResponse(
                results=data,
                total_results=len(data),
                timestamp=datetime.now()
            )

            return [TextContent(
                type="text",
                text=response.model_dump_json(indent=2)
            )]

    # Core graph operations (from original server)
    async def _store_facts(self, args: Facts) -> StoreFactsResponse:
        """Store facts in the knowledge graph.
        Args:
            args: Facts model containing:
                - context (optional): Context to store facts under
                - facts: list[Fact] of facts to store
        Returns:
            StoreFactsResponse object containing:
                - stored_facts: list[Fact] of stored fact metadata
                - context: The context used
                - total_stored: Number of facts stored
                - created_at: Datetime of when the facts were stored
        """
        context = args.context if args.context is not None else "default"
        created_at = datetime.now()
        stored_facts: list[Fact] = []

        async with self.driver.session() as session:
            async with await session.begin_transaction() as tx:
                await self._ensure_context_schema(context, tx)

                for fact in args.facts:
                    query = """
                    MERGE (s:Entity {name: $subject})
                    MERGE (o:Entity {name: $object})
                    CREATE (s)-[r:RELATES {
                        type: $predicate,
                        context: $context,
                        created_at: datetime()
                    }]->(o)
                    RETURN {
                        subject: s.name,
                        predicate: r.type,
                        object: o.name
                    } as fact
                    """

                    result = await tx.run(
                        query,
                        {
                            "subject": fact.subject,
                            "predicate": fact.predicate,
                            "object": fact.object,
                            "context": context,
                        },
                    )

                    fact_data = await result.single()
                    if fact_data:
                        stored_facts.append(
                            Fact(
                                subject=fact_data["fact"]["subject"],
                                predicate=fact_data["fact"]["predicate"],
                                object=fact_data["fact"]["object"],
                            )
                        )

                await tx.commit()

        return StoreFactsResponse(
            stored_facts=stored_facts,
            context=context,
            total_stored=len(stored_facts),
            created_at=created_at,
        )

    async def _query_knowledge(self, args: QueryParams) -> QueryResponse:
        """Query relationships in the knowledge graph"""
        context_filter = "WHERE r.context = $context" if args.context else ""

        query = f"""
        MATCH p=(s:Entity)-[r:RELATES]->(o:Entity)
        {context_filter}
        RETURN {{
            from_entity: {{ 
                name: s.name, 
                type: coalesce(s.type, 'Entity') 
            }},
            to_entity: {{ 
                name: o.name, 
                type: coalesce(o.type, 'Entity') 
            }},
            relation_type: r.type,
            context: r.context,
            created_at: r.created_at
        }} as relation
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"context": args.context})
            data = await result.data()

            relations = [
                Relation(
                    from_entity=Entity(**r["relation"]["from_entity"]),
                    to_entity=Entity(**r["relation"]["to_entity"]),
                    relation_type=r["relation"]["relation_type"],
                    context=r["relation"]["context"],
                    created_at=(r["relation"]["created_at"].to_native() 
                              if hasattr(r["relation"]["created_at"], "to_native") 
                              else r["relation"]["created_at"]) if r["relation"]["created_at"] else None,
                    created_at=(
                        (
                            r["relation"]["created_at"].to_native()
                            if hasattr(r["relation"]["created_at"], "to_native")
                            else r["relation"]["created_at"]
                        )
                        if r["relation"]["created_at"]
                        else None
                    ),
                )
                for r in data
            ]

            return QueryResponse(
                relations=relations, context=args.context, total_found=len(relations)
            )

    async def _find_connections(self, args: ConnectionParams) -> ConnectionResponse:
        """Find paths between two entities in the knowledge graph"""
        # We need to interpolate max_depth directly since it can't be a parameter in shortestPath
        query = f"""
        MATCH path = shortestPath(
            (a:Entity {{name: $concept_a}})-[r:RELATES*1..{args.max_depth}]-(b:Entity {{name: $concept_b}})
        )
        RETURN {{
            entities: [n in nodes(path) | {{
                name: n.name,
                type: coalesce(n.type, 'Entity')
            }}],
            relations: [r in relationships(path) | {{
                relation_type: r.type,
                context: r.context,
                created_at: r.created_at,
                from_entity: {{
                    name: startNode(r).name,
                    type: coalesce(startNode(r).type, 'Entity')
                }},
                to_entity: {{
                    name: endNode(r).name,
                    type: coalesce(endNode(r).type, 'Entity')
                }}
            }}]
        }} as path
        """

        # Remove max_depth from parameters since it's now in the query string
        params = {
            "concept_a": args.concept_a,
            "concept_b": args.concept_b
        }
        params = {"concept_a": args.concept_a, "concept_b": args.concept_b}

        async with self.driver.session() as session:
            result = await session.run(query, params)
            paths_data = await result.data()

            paths = []
            for p in paths_data:
                path_data = p["path"]
                entities = [Entity(**e) for e in path_data["entities"]]
                relations = []
                for r in path_data["relations"]:
                    # Convert Neo4j DateTime to Python datetime if needed
                    if r["created_at"]:
                        r["created_at"] = (r["created_at"].to_native() 
                                         if hasattr(r["created_at"], "to_native") 
                                         else r["created_at"])
                        r["created_at"] = (
                            r["created_at"].to_native()
                            if hasattr(r["created_at"], "to_native")
                            else r["created_at"]
                        )
                    relations.append(Relation(**r))

                paths.append(
                    Path(
                        entities=entities,
                        relations=relations,
                        length=len(relations)
                    )
                )

            return ConnectionResponse(
                paths=paths,
                start_entity=args.concept_a,
                end_entity=args.concept_b,
                total_paths=len(paths),
            )

    # Resource handling methods remain the same
    async def list_resources(self) -> List[Resource]:
        return self._resources["contents"]

    async def list_resource_templates(self) -> List[ResourceTemplate]:
        return self._resource_templates["contents"]

    async def read_resource(self, uri: str) -> str | bytes:
        if uri.startswith("neo4j://templates/"):
            return await self.handle_template_resource(uri)
        else:
            return await self.handle_neo4j_resource(uri)

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