"""Ingestion jobs.

Thin wrappers that own their own database session so they can be triggered from the API
background tasks, the scheduler, or a CLI script.

TODO: move execution onto a real task queue (Celery/Arq) with retries, concurrency limits and
a dead-letter queue before running against production sources.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.db.session import session_scope
from app.ingestion.pipeline import IngestionPipeline
from app.schemas.metadata import IngestionRequest, IngestionResult
from app.services.lineage.lineage_service import LineageService

logger = get_logger(__name__)


@dataclass(slots=True)
class JobResult:
    name: str
    success: bool
    detail: str = ""


async def run_ingestion_job(
    request: IngestionRequest, *, principal: str = "system"
) -> IngestionResult:
    """Execute one ingestion run in its own transaction."""
    async with session_scope() as session:
        pipeline = IngestionPipeline(session)
        return await pipeline.run(request, principal=principal)


async def rebuild_graph_job(*, principal: str = "system") -> JobResult:
    """Rebuild the graph projection from PostgreSQL."""
    async with session_scope() as session:
        service = LineageService(session)
        stats = await service.rebuild_graph(principal=principal)
    return JobResult(name="rebuild_graph", success=True, detail=str(stats))


async def reindex_job(*, principal: str = "system") -> JobResult:
    """Refresh the semantic index for the whole catalog and glossary."""
    from app.schemas.search import IndexRequest
    from app.services.search.hybrid_search import SearchService

    async with session_scope() as session:
        totals = await SearchService(session).reindex(IndexRequest(rebuild=False))
    logger.info("reindex_job_completed", extra=totals)
    return JobResult(name="reindex", success=True, detail=str(totals))
