from mcp.types import Prompt

PROMPTS: dict[str, Prompt] = {
    "graph-query": Prompt(
        name="graph-query",
        description="Generate and execute a Cypher query based on natural language",
        arguments=[
            {
                "name": "question",
                "description": "Natural language question about the graph data",
                "required": True,
            }
        ],
    ),
    "relationship-analysis": Prompt(
        name="relationship-analysis",
        description="Analyze relationships between nodes in the graph",
        arguments=[
            {
                "name": "start_node",
                "description": "Starting node label or identifier",
                "required": True,
            },
            {
                "name": "end_node",
                "description": "Ending node label or identifier",
                "required": True,
            },
            {
                "name": "max_depth",
                "description": "Maximum path depth to analyze",
                "required": False,
            },
        ],
    ),
    "schema-suggestion": Prompt(
        name="schema-suggestion",
        description="Get suggestions for optimizing graph schema based on current usage patterns",
        arguments=[
            {
                "name": "focus_area",
                "description": "Specific area of the schema to analyze (optional)",
                "required": False,
            }
        ],
    ),
    "query-optimization": Prompt(
        name="query-optimization",
        description="Analyze and optimize a Cypher query",
        arguments=[
            {
                "name": "query",
                "description": "Cypher query to optimize",
                "required": True,
            },
            {
                "name": "context",
                "description": "Additional context about query usage",
                "required": False,
            },
        ],
    ),
}
