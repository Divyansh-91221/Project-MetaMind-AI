"""Data access for lineage edges and observations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.constants import (
    LineageLevel,
    LineageMethod,
    RelationshipType,
    VerificationStatus,
)
from app.models.lineage import LineageEdge, LineageObservation
from app.models.metadata import MetadataEntity
from app.utils.timestamps import utcnow


class LineageRepository:
    """Persistence for the lineage source of truth."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def get_by_id(self, edge_id: uuid.UUID) -> LineageEdge | None:
        return await self.session.get(LineageEdge, edge_id)

    async def find_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relationship: RelationshipType,
        level: LineageLevel,
    ) -> LineageEdge | None:
        stmt = select(LineageEdge).where(
            LineageEdge.source_id == source_id,
            LineageEdge.target_id == target_id,
            LineageEdge.relationship_type == relationship,
            LineageEdge.level == level,
        )
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()

    async def list_for_entity(
        self,
        entity_id: uuid.UUID,
        *,
        direction: str = "both",
        level: LineageLevel | None = None,
        min_confidence: float = 0.0,
        include_inferred: bool = True,
    ) -> list[LineageEdge]:
        """Direct (one hop) edges touching the entity."""
        clauses = []
        if direction in ("both", "downstream"):
            clauses.append(LineageEdge.source_id == entity_id)
        if direction in ("both", "upstream"):
            clauses.append(LineageEdge.target_id == entity_id)

        stmt = select(LineageEdge).where(or_(*clauses))
        if level is not None:
            stmt = stmt.where(LineageEdge.level == level)
        if min_confidence > 0:
            stmt = stmt.where(LineageEdge.confidence >= min_confidence)
        if not include_inferred:
            stmt = stmt.where(LineageEdge.method != LineageMethod.AI_INFERRED)

        stmt = stmt.options(
            joinedload(LineageEdge.source), joinedload(LineageEdge.target)
        ).order_by(LineageEdge.confidence.desc())
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[LineageEdge]:
        """Full edge list - used to rebuild the graph projection."""
        stmt = (
            select(LineageEdge)
            .options(joinedload(LineageEdge.source), joinedload(LineageEdge.target))
            .order_by(LineageEdge.created_at)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def list_pending_verification(
        self, *, limit: int = 50, max_confidence: float = 1.0
    ) -> list[LineageEdge]:
        """AI-inferred and low-confidence edges awaiting a human decision."""
        stmt = (
            select(LineageEdge)
            .where(
                LineageEdge.verification_status == VerificationStatus.UNVERIFIED,
                LineageEdge.confidence <= max_confidence,
                or_(
                    LineageEdge.method == LineageMethod.AI_INFERRED,
                    LineageEdge.confidence < 0.7,
                ),
            )
            .options(joinedload(LineageEdge.source), joinedload(LineageEdge.target))
            .order_by(LineageEdge.confidence.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def count_neighbours(self, entity_id: uuid.UUID) -> tuple[int, int]:
        upstream = select(func.count()).where(LineageEdge.target_id == entity_id)
        downstream = select(func.count()).where(LineageEdge.source_id == entity_id)
        up = int((await self.session.execute(upstream)).scalar_one())
        down = int((await self.session.execute(downstream)).scalar_one())
        return up, down

    async def stats(self) -> dict[str, Any]:
        total = int(
            (await self.session.execute(select(func.count()).select_from(LineageEdge))).scalar_one()
        )
        by_method_rows = (
            await self.session.execute(
                select(LineageEdge.method, func.count()).group_by(LineageEdge.method)
            )
        ).all()
        verified = int(
            (
                await self.session.execute(
                    select(func.count()).where(LineageEdge.verified.is_(True))
                )
            ).scalar_one()
        )
        return {
            "total_edges": total,
            "verified_edges": verified,
            "by_method": {row[0].value: int(row[1]) for row in by_method_rows},
        }

    async def resolve_entity_ids(self, urns: list[str]) -> dict[str, uuid.UUID]:
        """Map URNs to primary keys in one round trip."""
        if not urns:
            return {}
        stmt = select(MetadataEntity.urn, MetadataEntity.id).where(MetadataEntity.urn.in_(urns))
        return {row[0]: row[1] for row in (await self.session.execute(stmt)).all()}

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    async def upsert_edge(
        self,
        *,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relationship: RelationshipType,
        level: LineageLevel,
        method: LineageMethod,
        confidence: float,
        observed_at: Any,
        transformation: str | None = None,
        pipeline_id: uuid.UUID | None = None,
        job_run_id: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> tuple[LineageEdge, bool]:
        """Create or refresh an edge and always append an observation.

        The observation trail is what makes lineage auditable: even when the edge already
        exists we record that it was seen again, by which method and with what evidence.
        """
        existing = await self.find_edge(source_id, target_id, relationship, level)
        created = existing is None

        if existing is None:
            existing = LineageEdge(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship,
                level=level,
                method=method,
                confidence=confidence,
                transformation=transformation,
                pipeline_id=pipeline_id,
                job_run_id=job_run_id,
                observed_at=observed_at,
                last_observed_at=observed_at,
                observation_count=1,
                evidence=evidence or {},
            )
            self.session.add(existing)
        else:
            existing.last_observed_at = observed_at
            existing.observation_count += 1
            if transformation:
                existing.transformation = transformation
            if pipeline_id:
                existing.pipeline_id = pipeline_id
            # A stronger extraction method supersedes a weaker one.
            if confidence > existing.confidence:
                existing.confidence = confidence
                existing.method = method
            if evidence:
                existing.evidence = {**existing.evidence, **evidence}

        await self.session.flush()

        self.session.add(
            LineageObservation(
                edge_id=existing.id,
                method=method,
                confidence=confidence,
                observed_at=observed_at,
                extractor=method.value,
                run_id=job_run_id,
                source_evidence=(evidence or {}).get("sql") or (evidence or {}).get("source"),
                evidence=evidence or {},
            )
        )
        await self.session.flush()
        return existing, created

    async def set_verification(
        self,
        edge: LineageEdge,
        *,
        status: VerificationStatus,
        principal: str,
        note: str | None = None,
    ) -> LineageEdge:
        edge.verification_status = status
        edge.verified = status is VerificationStatus.VERIFIED
        edge.verified_by = principal
        edge.verified_at = utcnow()
        edge.verification_note = note
        if status is VerificationStatus.VERIFIED:
            edge.confidence = 1.0
        await self.session.flush()
        return edge

    async def observations_for_edge(
        self, edge_id: uuid.UUID, *, limit: int = 50
    ) -> list[LineageObservation]:
        stmt = (
            select(LineageObservation)
            .where(LineageObservation.edge_id == edge_id)
            .order_by(LineageObservation.observed_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_edges_for_source(self, extractor: str) -> int:
        """Remove edges produced by one extractor - used by full-refresh ingestion.

        TODO: replace with a watermark/soft-delete strategy so history is preserved.
        """
        stmt = select(LineageEdge).where(
            and_(LineageEdge.method == LineageMethod(extractor))
            if extractor in set(LineageMethod)
            else False
        )
        edges = list((await self.session.execute(stmt)).unique().scalars().all())
        for edge in edges:
            await self.session.delete(edge)
        await self.session.flush()
        return len(edges)
