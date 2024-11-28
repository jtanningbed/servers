import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_server_neo4j.server import Neo4jServer, NLPProvider


@pytest.fixture
async def server():
    server = Neo4jServer()
    yield server
    await server.shutdown()


@pytest.mark.asyncio
async def test_nlp_provider_detection():
    """Test that NLP providers are correctly detected based on environment variables"""
    with patch.dict(
        "os.environ",
        {
            "GOOGLE_APPLICATION_CREDENTIALS": "fake-creds.json",
            "AZURE_API_KEY": "fake-key",
            "AWS_ACCESS_KEY_ID": "fake-id",
            "AWS_SECRET_ACCESS_KEY": "fake-secret",
        },
    ):
        server = Neo4jServer()
        providers = server._detect_nlp_providers()
        assert NLPProvider.GCP in providers
        assert NLPProvider.AZURE in providers
        assert NLPProvider.AWS in providers
        assert NLPProvider.SPACY not in providers


@pytest.mark.asyncio
async def test_explicit_provider_override():
    """Test that explicitly specified provider is used when available"""
    server = Neo4jServer()
    mock_tx = MagicMock()
    mock_tx.run.return_value.single.return_value = {
        "subject": "Apple",
        "predicate": "bought",
        "object": "Beats",
    }

    # Set up multiple providers
    with patch.dict(
        "os.environ",
        {
            "GOOGLE_APPLICATION_CREDENTIALS": "fake-creds.json",
            "AZURE_API_KEY": "fake-key",
        },
    ):
        await server.initialize("bolt://localhost:7687", ("neo4j", "password"))

        # Test explicit GCP
        await server._extract_fact(
            "Apple bought Beats", mock_tx, provider=NLPProvider.GCP
        )
        assert "apoc.nlp.gcp.entities" in mock_tx.run.call_args[0][0]

        # Test explicit Azure
        await server._extract_fact(
            "Apple bought Beats", mock_tx, provider=NLPProvider.AZURE
        )
        assert "apoc.nlp.azure.entities" in mock_tx.run.call_args[0][0]


@pytest.mark.asyncio
async def test_extract_fact_provider_selection():
    """Test that _extract_fact uses the correct provider"""
    server = Neo4jServer()
    # Use AsyncMock instead of MagicMock for async operations
    mock_tx = AsyncMock()
    mock_tx.run.return_value.single.return_value = {
        "subject": "Apple",
        "predicate": "bought",
        "object": "Beats",
    }

    # Test with GCP available
    with patch.dict(
        "os.environ", {"GOOGLE_APPLICATION_CREDENTIALS": "fake-creds.json"}
    ):
        await server.initialize("bolt://localhost:7687", ("neo4j", "password"))
        await server._extract_fact("Apple bought Beats", mock_tx)
        # Check that GCP query was used
        call_args = mock_tx.run.call_args[0][0]
        assert "apoc.nlp.gcp.entities" in call_args


@pytest.mark.asyncio
async def test_spacy_fallback_initialization():
    """Test that spaCy is initialized only when no other providers are available"""
    # Case 1: Other provider available
    with patch.dict(
        "os.environ", {"GOOGLE_APPLICATION_CREDENTIALS": "fake-creds.json"}
    ):
        server = Neo4jServer()
        await server.initialize("bolt://localhost:7687", ("neo4j", "password"))
        assert server.spacy_proc is None
        assert NLPProvider.GCP in server.available_providers

    # Case 2: No providers available
    with patch.dict("os.environ", {}, clear=True):
        server = Neo4jServer()
        with patch("neo4j_spacy_procedures.SpacyNLPProcedure") as mock_spacy:
            await server.initialize("bolt://localhost:7687", ("neo4j", "password"))
            assert server.spacy_proc is not None
            assert NLPProvider.SPACY in server.available_providers
            mock_spacy.assert_called_once()


@pytest.mark.asyncio
async def test_explicit_provider_override():
    """Test that explicitly specified provider is used when available"""
    server = Neo4jServer()
    mock_tx = AsyncMock()
    mock_tx.run.return_value.single.return_value = {
        "subject": "Apple",
        "predicate": "bought",
        "object": "Beats",
    }

    # Set up multiple providers
    with patch.dict(
        "os.environ",
        {
            "GOOGLE_APPLICATION_CREDENTIALS": "fake-creds.json",
            "AZURE_API_KEY": "fake-key",
        },
    ):
        await server.initialize("bolt://localhost:7687", ("neo4j", "password"))

        # Test explicit GCP
        await server._extract_fact(
            "Apple bought Beats", mock_tx, provider=NLPProvider.GCP
        )
        assert "apoc.nlp.gcp.entities" in mock_tx.run.call_args[0][0]

        # Test explicit Azure
        await server._extract_fact(
            "Apple bought Beats", mock_tx, provider=NLPProvider.AZURE
        )
        assert "apoc.nlp.azure.entities" in mock_tx.run.call_args[0][0]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_neo4j_extraction():
    """Test entity extraction against a real Neo4j instance"""
    server = Neo4jServer()
    try:
        await server.initialize("bolt://localhost:7687", ("neo4j", "password"))

        # Ensure we have at least spaCy available
        if not server.available_providers:
            pytest.skip("No NLP providers available, including spaCy fallback")

        async with server.driver.session() as session:
            async with await session.begin_transaction() as tx:
                subject, predicate, obj = await server._extract_fact(
                    "Apple is acquiring Beats for $3 billion", tx
                )
                assert subject == "Apple"
                assert "Beats" in obj

    finally:
        await server.shutdown()
