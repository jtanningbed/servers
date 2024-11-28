from .server import serve


def main():
    import asyncio
    import os

    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "testpassword")

    asyncio.run(serve())


if __name__ == "__main__":
    main()
