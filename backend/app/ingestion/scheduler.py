"""In-process ingestion scheduler.

Deliberately minimal: a single asyncio task that re-runs enabled data sources on an interval.
It is disabled by default (``INGESTION_SCHEDULE_SECONDS=0``) and is intended for local
development only - a production deployment should use an external scheduler feeding a task
queue so runs survive restarts and scale horizontally.
"""

from __future__ import annotations

import asyncio
import contextlib

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.ingestion.jobs import run_ingestion_job
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.metadata import IngestionRequest

logger = get_logger(__name__)


class IngestionScheduler:
    """Periodically re-ingests every enabled data source."""

    def __init__(self, interval_seconds: int | None = None) -> None:
        self.interval = interval_seconds or settings.ingestion_schedule_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self.interval > 0

    async def start(self) -> None:
        if not self.enabled:
            logger.info("ingestion_scheduler_disabled")
            return
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="ingestion-scheduler")
        logger.info("ingestion_scheduler_started", extra={"interval_seconds": self.interval})

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("ingestion_scheduler_stopped")

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval)
                return
            except TimeoutError:
                pass

            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001 - the loop must survive any failure
                logger.error("scheduled_ingestion_failed", extra={"error": str(exc)})

    async def run_once(self) -> int:
        """Run every enabled data source once. Returns the number of runs executed."""
        async with session_scope() as session:
            sources = [
                source
                for source in await MetadataRepository(session).list_data_sources()
                if source.enabled
            ]

        for source in sources:
            await run_ingestion_job(
                IngestionRequest(
                    connector=source.connector_type,
                    data_source_name=source.name,
                    config=source.config,
                ),
                principal="scheduler",
            )
        logger.info("scheduled_ingestion_completed", extra={"sources": len(sources)})
        return len(sources)


scheduler = IngestionScheduler()
