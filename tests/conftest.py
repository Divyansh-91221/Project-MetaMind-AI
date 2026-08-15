"""Shared pytest fixtures.

Unit tests must run with no external services: the graph, vector store and LLM are all
swapped for in-memory/deterministic implementations here.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Force offline providers before application modules read settings.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("GRAPH_STORE", "memory")
os.environ.setdefault("VECTOR_STORE", "memory")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("AUTH_ENABLED", "false")

from app.ai.llm import MockLLMProvider, set_llm_provider  # noqa: E402
from app.graph.base import InMemoryGraphStore  # noqa: E402
from app.graph.neo4j_client import set_graph_store  # noqa: E402
from app.rag.embeddings import HashEmbeddingProvider, set_embedding_provider  # noqa: E402


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def graph_store() -> InMemoryGraphStore:
    """Fresh in-memory graph per test."""
    store = InMemoryGraphStore()
    set_graph_store(store)
    return store


@pytest.fixture(autouse=True)
def offline_providers() -> Iterator[None]:
    """Guarantee no test ever reaches a hosted model."""
    set_llm_provider(MockLLMProvider())
    set_embedding_provider(HashEmbeddingProvider(dimension=256))
    yield


@pytest.fixture
async def demo_connector() -> AsyncIterator[object]:
    """The demo connector instance used across extraction tests."""
    from app.connectors.demo import DemoConnector

    connector = DemoConnector()
    yield connector
    await connector.close()
