# tests/conftest.py
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("NEO4J_URI", "neo4j://localhost:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "testpassword")
