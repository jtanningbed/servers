from typing import Dict, Any, Optional
from mcp.types import (
    Prompt,
    GetPromptResult,
    PromptMessage,
    TextContent
)
from .templates import QUERY_TEMPLATES

# Prompts for guiding query and schema operations
NEO4J_PROMPTS: dict[str, Prompt] = {
    "query-suggestion": Prompt(
        name="query-suggestion",
        description="Get suggestions for Neo4j query templates based on your intent",
        arguments=[
            {
                "name": "intent", 
                "description": "Description of what you want to achieve",
                "required": True,
            },
            {
                "name": "data_description",
                "description": "Description of your data model",
                "required": False,
            },
            {
                "name": "example_data",
                "description": "Example of your data",
                "required": False,
            }
        ]
    ),
    "schema-design": Prompt(
        name="schema-design",
        description="Get recommendations for Neo4j schema design based on your use case",
        arguments=[
            {
                "name": "start_node",
                "description": "Starting node label or identifier",
                "required": True,
            }, 
            {
                "name": "use_case",
                "description": "Description of your application",
                "required": True,
            },
            {
                "name": "requirements",
                "description": "Specific requirements for your data model",
                "required": True,
            },
            {
                "name": "query_patterns",
                "description": "Common queries you need to support",
                "required": False,
            }
        ],
    ),
    "query-optimization": Prompt(
        name="query-optimization",
        description="Get suggestions for optimizing your Cypher queries",
        arguments=[
            {
                "name": "query",
                "description": "Cypher query to optimize",
                "required": True,
            },
            {
                "name": "context",
                "description": "Additional context about your data and requirements",
                "required": False,
            }
    ],
    ),
    "relationship-analysis": Prompt(
        name="relationship-analysis",
        description="Get analysis of relationship patterns between nodes",
        arguments=[
            {
                "name": "start-node",
                "description": "Starting node label or identifier",
                "required": True
            }, 
            {
                "name": "end-node",
                "description": "Ending node label or identifier",
                "required": True
            }, 
            {
                "name": "relationship-types",
                "description": "Types of relationships to consider",
                "required": False
            }, 
            {
                "name": "max-depth",
                "description": "Maximum path depth to analyze",
                "required": False
            }
        ]
    )
}


async def handle_query_suggestion_prompt(
    intent: str,
    data_description: Optional[str] = None,
    example_data: Optional[str] = None
) -> GetPromptResult:
    """Generate a response for query template suggestions"""
    template_descriptions = "\n".join([
        f"- {name}: {template.description}"
        for name, template in QUERY_TEMPLATES.items()
    ])
    
    content = f"""Based on your intent: "{intent}"

Available query templates:
{template_descriptions}

Let me suggest the most appropriate templates and how to use them.

Please also consider these aspects:
1. Data model constraints and assumptions
2. Performance implications
3. Alternative approaches if needed
"""

    if data_description:
        content += f"\nConsidering your data model:\n{data_description}"
    
    if example_data:
        content += f"\nBased on your example data:\n{example_data}"

    return GetPromptResult(
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=content
                )
            )
        ]
    )

async def handle_schema_design_prompt(
    use_case: str,
    requirements: str,
    query_patterns: Optional[str] = None
) -> GetPromptResult:
    """Generate a response for schema design suggestions"""
    content = f"""Let me help you design a Neo4j schema for your use case:
"{use_case}"

Requirements to consider:
{requirements}

I'll suggest:
1. Node labels and their properties
2. Relationship types and structures
3. Indexes and constraints
4. Data modeling best practices
"""

    if query_patterns:
        content += f"\nConsidering these query patterns:\n{query_patterns}"

    return GetPromptResult(
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=content
                )
            )
        ]
    )

async def handle_query_optimization_prompt(
    query: str,
    context: Optional[str] = None
) -> GetPromptResult:
    """Generate a response for query optimization suggestions"""
    content = f"""Let me analyze this Cypher query for optimization opportunities:

```cypher
{query}
```

I'll consider:
1. Index usage and label scans
2. Relationship traversal patterns
3. Parameter usage and literal values
4. Aggregation and collection handling
5. Query plan analysis
"""

    if context:
        content += f"\nAdditional context to consider:\n{context}"

    return GetPromptResult(
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=content
                )
            )
        ]
    )

async def handle_relationship_analysis_prompt(
    start_node: Dict[str, Any],
    end_node: Dict[str, Any],
    relationship_types: list[str],
    max_depth: int = 3
) -> GetPromptResult:
    """Generate a response for relationship pattern analysis"""
    content = f"""Analyze relationships between:
Start node: {start_node}
End node: {end_node}
Considering relationship types: {', '.join(relationship_types)}
Maximum path depth: {max_depth}

I'll analyze:
1. Direct relationships
2. Indirect paths and connecting nodes
3. Relationship patterns and frequencies
4. Potential new relationship types
"""

    return GetPromptResult(
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=content
                )
            )
        ]
    )

# Mapping of prompt names to their handlers
PROMPT_HANDLERS = {
    "query-suggestion": handle_query_suggestion_prompt,
    "schema-design": handle_schema_design_prompt,
    "query-optimization": handle_query_optimization_prompt,
    "relationship-analysis": handle_relationship_analysis_prompt

}
