"""Integration test fixtures.

These tests require the Docker Compose stack (PostgreSQL with pgvector, and optionally
Neo4j). They skip - rather than fail - when the services are unreachable, so the unit suite
stays runnable anywhere.

    docker compose up -d postgres neo4j
    pytest -m integration
"""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.base import Base
from app.models.documents import PGVECTOR_ENABLED

pytestmark = pytest.mark.integration


_postgres_reachable: bool | None = None


def _postgres_available() -> bool:
    """Fast, cached reachability probe.

    A socket check rather than a driver connection: it fails immediately when nothing is
    listening, instead of costing a connection timeout per test.
    """
    global _postgres_reachable
    if _postgres_reachable is None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            _postgres_reachable = (
                sock.connect_ex((settings.postgres_host, settings.postgres_port)) == 0
            )
    return _postgres_reachable


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A fresh schema per test.

    Function-scoped on purpose: the ingestion fixture commits, so a shared schema would leak
    state between tests, and an event loop shared across scopes upsets asyncpg.
    """
    if not _postgres_available():
        pytest.skip("PostgreSQL is not reachable; run `docker compose up -d postgres`.")

    engine = create_async_engine(settings.async_database_url, pool_pre_ping=True)
    async with engine.begin() as conn:
        if PGVECTOR_ENABLED:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        # Schema is created directly here; migrations are exercised separately by
        # `alembic upgrade head` in CI.
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session bound to the per-test schema."""
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def ingested(session: AsyncSession) -> AsyncSession:
    """Demo landscape loaded and the lineage graph rebuilt - the baseline most integration and
    smoke tests need. Shared here so every integration test file gets the same setup."""
    from app.ingestion.pipeline import IngestionPipeline
    from app.schemas.metadata import IngestionRequest
    from app.services.lineage.lineage_service import LineageService

    await IngestionPipeline(session).run(
        IngestionRequest(connector="demo", data_source_name="demo-test"),
        principal="integration-test",
    )
    await session.commit()
    await LineageService(session).rebuild_graph(principal="integration-test")
    return session
