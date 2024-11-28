# conftest.py

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase
import os


@pytest_asyncio.fixture
async def neo4j_connection():
    """Create a real Neo4j connection for integration tests"""
    uri = os.getenv("NEO4J_TEST_URI", "neo4j://localhost:7687")
    auth = (
        os.getenv("NEO4J_TEST_USER", "neo4j"),
        os.getenv("NEO4J_TEST_PASSWORD", "testpassword"),
    )

    driver = AsyncGraphDatabase.driver(uri, auth=auth)

    # Verify connection
    try:
        async with driver.session() as session:
            await session.run("MATCH (n) RETURN count(n)")
    except Exception as e:
        pytest.skip(f"Neo4j not available: {e}")

    yield driver

    # Cleanup
    await driver.close()


@pytest_asyncio.fixture
async def clean_database(neo4j_connection):
    """Clear all data from the test database"""
    async with neo4j_connection.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
