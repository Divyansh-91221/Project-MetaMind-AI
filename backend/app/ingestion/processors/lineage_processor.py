"""Lineage ingestion processor.

Gathers lineage from three independent sources and hands the combined set to the lineage
service, which normalises, scores and persists it:

1. connector-declared relationships,
2. SQL parsed with SQLGlot from the connector's ``extract_sql`` stream,
3. (later) AI-inferred candidates - always marked and never auto-verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import MetadataConnector, RawLineage
from app.core.logging import get_logger
from app.services.lineage.lineage_service import LineageService
from app.services.lineage.sql_lineage_parser import SqlLineageParser

logger = get_logger(__name__)


@dataclass(slots=True)
class LineageProcessingResult:
    created: int = 0
    updated: int = 0
    statements_parsed: int = 0
    warnings: list[str] = field(default_factory=list)


class LineageProcessor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.lineage = LineageService(session)
        self.parser = SqlLineageParser()

    async def process(
        self, connector: MetadataConnector, *, principal: str = "system"
    ) -> LineageProcessingResult:
        result = LineageProcessingResult()
        edges: list[RawLineage] = []

        async for raw in connector.extract_lineage():
            edges.append(raw)

        async for artifact in connector.extract_sql():
            output = self.parser.parse(artifact)
            result.statements_parsed += output.statements_parsed
            result.warnings.extend(output.warnings)
            edges.extend(output.all_edges)

        if not edges:
            logger.info("no_lineage_extracted", extra={"connector": connector.name})
            return result

        created, updated = await self.lineage.persist_edges(edges, principal=principal)
        result.created = created
        result.updated = updated
        logger.info(
            "lineage_processing_completed",
            extra={
                "connector": connector.name,
                "created": created,
                "updated": updated,
                "warnings": len(result.warnings),
            },
        )
        return result
