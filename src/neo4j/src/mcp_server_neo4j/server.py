# Update at the top where SCHEMA_SETUP is defined
SCHEMA_SETUP = [
    "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
    "CREATE INDEX type IF NOT EXISTS FOR (e:Entity) ON (e.type)"
]

# Then in serve function
async def serve(
    uri: str = "neo4j://localhost:7687",
    username: str = "neo4j",
    password: str = "testpassword"
) -> None:
    logging.info(f"Attempting to connect with: URI={uri}, USERNAME={username}")
    # Don't log the actual password
    logging.info(f"Password provided: {'Yes' if password else 'No'}")

    server = Neo4jServer()
    await server.initialize(uri, (username, password))
    logger.info("Server initialized")

    try:
        # Initialize schema
        async with server.driver.session() as session:
            for statement in SCHEMA_SETUP:
                await session.run(statement)
            logger.info("Schema initialized")
            
        @server.list_resources()
        # ... rest of the file unchanged ...
