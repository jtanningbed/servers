from . import server
import asyncio


def main():
    logging.basicConfig(level=logging_level, stream=sys.stderr)
    asyncio.run(
        server.serve(
        )
    )

if __name__ == "__main__":
    main()

__all__ = ["main", "server"]
