from . import server
import asyncio
import os

def main():
    asyncio.run(
        server.serve(
            uri=os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password"),
        )
    )

if __name__ == "__main__":
    main()

__all__ = ["main", "server"]
