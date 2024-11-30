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
    # Enhanced operation schemas
    CypherQuery,
    ValidationError
)

logger = logging.getLogger(__name__)

class ResourceHandler:
    def __init__(self, driver: AsyncDriver):
        self.driver = driver
        self.schema_validator = SchemaValidator(driver)
        self._resources = {
            **RESOURCES,
            **TEMPLATE_RESOURCES
        }
        self._resource_templates = {
            **RESOURCE_TEMPLATES,
            **TEMPLATE_RESOURCE_TEMPLATES
        }

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
        """Store facts in the knowledge graph"""
        # Implementation from original server
        pass

    async def _query_knowledge(self, args: QueryParams) -> GraphQueryResponse:
        """Query relationships in the knowledge graph"""
        # Implementation from original server
        pass

    async def _find_connections(self, args: ConnectionParams) -> ConnectionResponse:
        """Find paths between concepts"""
        # Implementation from original server
        pass

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

    # Template validation
    async def validate_template(self, template_name: str, parameters: Dict[str, Any]) -> List[str]:
        """Validate template parameters and compatibility"""
        # Implementation from enhanced version
        pass

class ResourceHandler:
    def __init__(self, driver: AsyncDriver):
        self.driver = driver
        self.schema_validator = SchemaValidator(driver)
        self._resources = {
            **RESOURCES,
            **TEMPLATE_RESOURCES
        }
        self._resource_templates = {
            **RESOURCE_TEMPLATES,
            **TEMPLATE_RESOURCE_TEMPLATES
        }

    async def list_resources(self) -> List[Resource]:
        """List all available resources"""
        return self._resources["contents"]

    async def list_resource_templates(self) -> List[ResourceTemplate]:
        """List all available resource templates"""
        return self._resource_templates["contents"]

    async def list_tools(self) -> List[Tool]:
        """List available graph operation tools"""
        # Base tools
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

    async def read_resource(self, uri: str) -> str | bytes:
        """Handle resource reading based on URI type"""
        if uri.startswith("neo4j://templates/"):
            return await self.handle_template_resource(uri)
        else:
            return await self.handle_neo4j_resource(uri)

    async def handle_call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> List[TextContent]:
        """Handle tool execution with proper routing"""
        try:
            if name.startswith("template."):
                template_name = name.split(".", 1)[1]
                return await self._handle_template_tool(template_name, arguments or {})
            else:
                return await self._handle_standard_tool(name, arguments or {})
        except Exception as e:
            logger.error(f"Tool execution error: {str(e)}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": e.__class__.__name__,
                    "details": str(e)
                }, indent=2)
            )]

    async def _handle_template_tool(self, template_name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute a query template"""
        if template_name not in QUERY_TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}")

        template = QUERY_TEMPLATES[template_name]
        
        # Validate template parameters
        validation_issues = await self.validate_template(template_name, arguments)
        if validation_issues:
            raise ValidationError(
                field="parameters",
                details="\n".join(validation_issues)
            )

        # Execute template query
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

    async def _handle_standard_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle execution of standard tools"""
        # Validate input
        model_map = {
            "store-facts": Facts,
            "query-knowledge": QueryParams,
            "find-connections": ConnectionParams,
            "execute-cypher": CypherQuery
        }

        if name not in model_map:
            raise ValueError(f"Unknown tool: {name}")

        input_model = model_map[name]
        validated_args = input_model.model_validate(arguments)

        # Execute appropriate handler
        handlers = {
            "store-facts": self._store_facts,
            "query-knowledge": self._query_knowledge,
            "find-connections": self._find_connections,
            "execute-cypher": self._execute_cypher
        }

        result = await handlers[name](validated_args)
        return [TextContent(
            type="text",
            text=result.model_dump_json(indent=2)
        )]

    # Internal methods for handling individual tools
    async def _store_facts(self, args: Facts):
        """Implementation comes from original server"""
        pass

    async def _query_knowledge(self, args: QueryParams):
        """Implementation comes from original server"""
        pass

    async def _find_connections(self, args: ConnectionParams):
        """Implementation comes from original server"""
        pass

    async def _execute_cypher(self, query: CypherQuery):
        """Execute a Cypher query with validation"""
        if self.schema_validator:
            await self.schema_validator.validate_query(query)
            
        async with self.driver.session() as session:
            result = await session.run(query.query, query.parameters or {})
            data = await result.data()
            
            return QueryResponse(
                results=data,
                total_results=len(data),
                timestamp=datetime.now()
            )

    async def handle_template_resource(self, uri: str) -> str:
        """Handle requests for template resources"""
        # Implementation from original handlers.py
        pass

    async def handle_neo4j_resource(self, uri: str) -> str:
        """Handle requests for Neo4j resources"""
        # Implementation from original handlers.py
        pass