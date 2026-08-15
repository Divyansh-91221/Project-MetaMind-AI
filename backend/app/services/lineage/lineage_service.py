"""Lineage service - the first-class lineage capability.

Responsibilities:

* persist normalised lineage into PostgreSQL (the source of truth),
* project it into the graph store for traversal,
* answer upstream/downstream/path queries as API-ready contracts,
* run the SQL lineage parser,
* delegate human verification to :mod:`app.services.lineage.lineage_validation`.

The service never lets an LLM write lineage: every edge arrives from a connector, a parser or
an explicit human action, and always carries a method, a confidence score and evidence.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import RawLineage, SqlArtifact
from app.core.config import settings
from app.core.constants import (
    AuditAction,
    Direction,
    LineageLevel,
    LineageMethod,
    RelationshipType,
    VerificationStatus,
)
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.graph.base import GraphStore
from app.graph.graph_models import GraphEdge, GraphNode
from app.graph.lineage_traversal import (
    get_downstream,
    get_lineage_path,
    get_related_assets,
    get_upstream,
)
from app.graph.neo4j_client import get_graph_store
from app.models.lineage import LineageEdge
from app.models.metadata import MetadataEntity
from app.repositories.audit_repository import AuditRepository
from app.repositories.lineage_repository import LineageRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.lineage import (
    LineageEdgeCreate,
    LineageEdgeRead,
    LineageGraph,
    LineageNode,
    LineagePath,
    LineageQuery,
    SqlLineageRequest,
    SqlLineageResult,
)
from app.services.lineage.lineage_normalizer import normalizer
from app.services.lineage.lineage_validation import LineageValidationService
from app.services.lineage.sql_lineage_parser import SqlLineageParser
from app.utils.identifiers import parse_urn
from app.utils.timestamps import utcnow

logger = get_logger(__name__)


def entity_to_graph_node(entity: MetadataEntity, depth: int = 0) -> GraphNode:
    """Project a catalog row onto a graph vertex."""
    return GraphNode(
        urn=entity.urn,
        entity_type=entity.entity_type,
        name=entity.name,
        qualified_name=entity.qualified_name,
        platform=entity.platform,
        description=entity.description,
        depth=depth,
        properties={"display_name": entity.display_name or entity.name},
    )


def edge_to_graph_edge(edge: LineageEdge) -> GraphEdge:
    """Project a persisted lineage row onto a graph relationship."""
    return GraphEdge(
        source_urn=edge.source.urn,
        target_urn=edge.target.urn,
        relationship=edge.relationship_type,
        level=edge.level,
        method=edge.method,
        confidence=edge.confidence,
        verified=edge.verified,
        transformation=edge.transformation,
        pipeline_urn=edge.pipeline.urn if edge.pipeline else None,
        observed_at=edge.observed_at,
        edge_id=str(edge.id),
    )


def graph_node_to_schema(node: GraphNode) -> LineageNode:
    return LineageNode(
        urn=node.urn,
        name=node.name,
        qualified_name=node.qualified_name,
        entity_type=node.entity_type,
        platform=node.platform,
        description=node.description,
        depth=node.depth,
        properties=node.properties,
    )


def graph_edge_to_schema(edge: GraphEdge) -> LineageEdgeRead:
    return LineageEdgeRead(
        id=uuid.UUID(edge.edge_id) if edge.edge_id else None,
        source_urn=edge.source_urn,
        target_urn=edge.target_urn,
        relationship=edge.relationship,
        transformation=edge.transformation,
        pipeline_urn=edge.pipeline_urn,
        level=edge.level,
        method=edge.method,
        confidence=edge.confidence,
        verified=edge.verified,
        verification_status=(
            VerificationStatus.VERIFIED if edge.verified else VerificationStatus.UNVERIFIED
        ),
        observed_at=edge.observed_at,
    )


class LineageService:
    """Application service for all lineage operations."""

    def __init__(self, session: AsyncSession, graph: GraphStore | None = None) -> None:
        self.session = session
        self.graph = graph or get_graph_store()
        self.lineage_repo = LineageRepository(session)
        self.metadata_repo = MetadataRepository(session)
        self.audit_repo = AuditRepository(session)
        self.validation = LineageValidationService(session)
        self.parser = SqlLineageParser()

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #
    async def persist_edges(
        self,
        raw_edges: list[RawLineage],
        *,
        principal: str = "system",
        create_missing_entities: bool = True,
    ) -> tuple[int, int]:
        """Normalise, persist and project lineage. Returns ``(created, updated)``."""
        if not raw_edges:
            return 0, 0

        edges = normalizer.normalize(raw_edges)
        urns = {urn for edge in edges for urn in (edge.source_urn, edge.target_urn)}
        urns |= {edge.pipeline_urn for edge in edges if edge.pipeline_urn}

        id_by_urn = await self.lineage_repo.resolve_entity_ids(sorted(urns))
        missing = sorted(urns - set(id_by_urn))
        if missing and create_missing_entities:
            id_by_urn |= await self._create_placeholders(missing)

        created = updated = 0
        persisted: list[LineageEdge] = []
        for edge in edges:
            source_id = id_by_urn.get(edge.source_urn)
            target_id = id_by_urn.get(edge.target_urn)
            if source_id is None or target_id is None:
                logger.warning(
                    "lineage_edge_skipped_unknown_entity",
                    extra={"source": edge.source_urn, "target": edge.target_urn},
                )
                continue

            row, was_created = await self.lineage_repo.upsert_edge(
                source_id=source_id,
                target_id=target_id,
                relationship=edge.relationship,
                level=edge.level,
                method=edge.method,
                confidence=edge.confidence if edge.confidence is not None else 0.5,
                observed_at=edge.observed_at or utcnow(),
                transformation=edge.transformation,
                pipeline_id=id_by_urn.get(edge.pipeline_urn) if edge.pipeline_urn else None,
                job_run_id=edge.job_run_id,
                evidence=edge.evidence,
            )
            persisted.append(row)
            created += int(was_created)
            updated += int(not was_created)

        await self._project(persisted)
        await self.audit_repo.record(
            AuditAction.LINEAGE_CREATED if created else AuditAction.LINEAGE_UPDATED,
            principal=principal,
            resource_type="lineage",
            summary=f"Persisted {created} new and {updated} existing lineage edges.",
            payload={"created": created, "updated": updated},
        )
        return created, updated

    async def _create_placeholders(self, urns: list[str]) -> dict[str, uuid.UUID]:
        """Create minimal catalog rows for lineage endpoints not yet ingested.

        Placeholders keep the graph connected when a downstream system references an asset the
        catalog has not scanned yet. They are flagged so a later ingestion enriches them.
        """
        created: dict[str, uuid.UUID] = {}
        for urn in urns:
            try:
                entity_type, platform, qualified_name = parse_urn(urn)
            except ValueError:
                logger.warning("placeholder_skipped_bad_urn", extra={"urn": urn})
                continue
            entity, _ = await self.metadata_repo.upsert(
                {
                    "urn": urn,
                    "entity_type": entity_type,
                    "platform": platform,
                    "name": qualified_name.split(".")[-1],
                    "qualified_name": qualified_name,
                    "properties": {"placeholder": True, "created_by": "lineage"},
                }
            )
            created[urn] = entity.id
        logger.info("lineage_placeholders_created", extra={"count": len(created)})
        return created

    async def _project(self, edges: list[LineageEdge]) -> None:
        """Mirror persisted edges (and their endpoints) into the graph store."""
        if not edges:
            return
        nodes: dict[str, GraphNode] = {}
        for edge in edges:
            for entity in (edge.source, edge.target):
                nodes.setdefault(entity.urn, entity_to_graph_node(entity))
        try:
            await self.graph.upsert_nodes(list(nodes.values()))
            await self.graph.upsert_edges([edge_to_graph_edge(edge) for edge in edges])
        except Exception as exc:  # noqa: BLE001 - the catalog write must still succeed
            logger.error("graph_projection_failed", extra={"error": str(exc)})

    async def rebuild_graph(self, *, principal: str = "system") -> dict[str, int]:
        """Rebuild the whole graph projection from PostgreSQL.

        Safe to run at any time - PostgreSQL remains the source of truth.
        """
        await self.graph.clear()
        entities, _ = await self.metadata_repo.list_entities(limit=100_000)
        await self.graph.upsert_nodes([entity_to_graph_node(entity) for entity in entities])

        edges = await self.lineage_repo.list_all()
        await self.graph.upsert_edges([edge_to_graph_edge(edge) for edge in edges])

        # Structural containment (table -> column) makes column drill-down possible.
        containment = [
            GraphEdge(
                source_urn=entity.parent.urn,
                target_urn=entity.urn,
                relationship=RelationshipType.CONTAINS,
                level=LineageLevel.TABLE,
                method=LineageMethod.CONNECTOR_DECLARED,
                confidence=1.0,
                verified=True,
            )
            for entity in entities
            if entity.parent_id is not None and entity.parent is not None
        ]
        await self.graph.upsert_edges(containment)

        await self.audit_repo.record(
            AuditAction.GRAPH_REBUILT,
            principal=principal,
            resource_type="graph",
            summary="Graph projection rebuilt from PostgreSQL.",
            payload={"nodes": len(entities), "edges": len(edges) + len(containment)},
        )
        return {"nodes": len(entities), "edges": len(edges), "containment_edges": len(containment)}

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    async def _require_entity(self, urn: str) -> MetadataEntity:
        entity = await self.metadata_repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")
        return entity

    async def get_lineage(
        self, urn: str, *, direction: Direction, query: LineageQuery
    ) -> LineageGraph:
        """Return a lineage subgraph ready for the UI canvas."""
        await self._require_entity(urn)

        if direction is Direction.UPSTREAM:
            result = await get_upstream(
                self.graph,
                urn,
                depth=query.depth,
                level=query.level,
                min_confidence=query.min_confidence,
                include_inferred=query.include_inferred,
            )
        elif direction is Direction.DOWNSTREAM:
            result = await get_downstream(
                self.graph,
                urn,
                depth=query.depth,
                level=query.level,
                min_confidence=query.min_confidence,
                include_inferred=query.include_inferred,
            )
        else:
            upstream = await get_upstream(
                self.graph,
                urn,
                depth=query.depth,
                level=query.level,
                min_confidence=query.min_confidence,
                include_inferred=query.include_inferred,
            )
            downstream = await get_downstream(
                self.graph,
                urn,
                depth=query.depth,
                level=query.level,
                min_confidence=query.min_confidence,
                include_inferred=query.include_inferred,
            )
            nodes = {node.urn: node for node in upstream.nodes}
            nodes.update({node.urn: node for node in downstream.nodes})
            upstream.nodes = list(nodes.values())
            upstream.edges = upstream.edges + downstream.edges
            upstream.truncated = upstream.truncated or downstream.truncated
            result = upstream

        edges = [graph_edge_to_schema(edge) for edge in result.edges]
        if not query.include_unverified:
            edges = [edge for edge in edges if edge.verified]

        return LineageGraph(
            root_urn=urn,
            direction=direction,
            depth=query.depth,
            nodes=[graph_node_to_schema(node) for node in result.nodes],
            edges=edges,
            truncated=result.truncated,
        )

    async def get_direct_edges(self, urn: str) -> list[LineageEdgeRead]:
        """One-hop edges straight from PostgreSQL - used when the graph is unavailable."""
        entity = await self._require_entity(urn)
        rows = await self.lineage_repo.list_for_entity(entity.id)
        return [
            LineageEdgeRead(
                id=row.id,
                source_urn=row.source.urn,
                target_urn=row.target.urn,
                relationship=row.relationship_type,
                transformation=row.transformation,
                pipeline_urn=row.pipeline.urn if row.pipeline else None,
                level=row.level,
                method=row.method,
                confidence=row.confidence,
                verified=row.verified,
                verification_status=row.verification_status,
                observed_at=row.observed_at,
                evidence=row.evidence,
            )
            for row in rows
        ]

    async def get_paths(
        self, source_urn: str, target_urn: str, *, max_depth: int | None = None
    ) -> list[LineagePath]:
        paths = await get_lineage_path(
            self.graph, source_urn, target_urn, max_depth=max_depth or settings.lineage_max_depth
        )
        return [
            LineagePath(
                source_urn=source_urn,
                target_urn=target_urn,
                hops=path.hops,
                nodes=[graph_node_to_schema(node) for node in path.nodes],
                edges=[graph_edge_to_schema(edge) for edge in path.edges],
                min_confidence=path.min_confidence,
            )
            for path in paths
        ]

    async def get_related(self, urn: str, *, depth: int = 2) -> LineageGraph:
        result = await get_related_assets(self.graph, urn, depth=depth)
        return LineageGraph(
            root_urn=urn,
            direction=Direction.BOTH,
            depth=depth,
            nodes=[graph_node_to_schema(node) for node in result.nodes],
            edges=[graph_edge_to_schema(edge) for edge in result.edges],
            truncated=result.truncated,
        )

    # ------------------------------------------------------------------ #
    # SQL parsing
    # ------------------------------------------------------------------ #
    async def parse_sql(
        self, request: SqlLineageRequest, *, principal: str = "system"
    ) -> SqlLineageResult:
        """Parse SQL into lineage, optionally persisting the result."""
        artifact = SqlArtifact(
            sql=request.sql,
            platform=request.default_platform,
            dialect=request.dialect,
            default_database=request.default_database,
            default_schema=request.default_schema,
            source="api",
        )
        output = self.parser.parse(artifact)

        if request.persist:
            await self.persist_edges(output.all_edges, principal=principal)

        return SqlLineageResult(
            statements_parsed=output.statements_parsed,
            table_edges=[_to_create_schema(edge) for edge in output.table_edges],
            column_edges=[_to_create_schema(edge) for edge in output.column_edges],
            warnings=output.warnings,
        )

    # ------------------------------------------------------------------ #
    # Manual assertions and verification
    # ------------------------------------------------------------------ #
    async def add_manual_edge(
        self, payload: LineageEdgeCreate, *, principal: str
    ) -> tuple[int, int]:
        raw = RawLineage(
            source_urn=payload.source_urn,
            target_urn=payload.target_urn,
            relationship=payload.relationship,
            level=payload.level,
            method=payload.method,
            transformation=payload.transformation,
            pipeline_urn=payload.pipeline_urn,
            job_run_id=payload.job_run_id,
            confidence=payload.confidence,
            observed_at=payload.observed_at or utcnow(),
            evidence={**payload.evidence, "source": f"manual:{principal}"},
        )
        return await self.persist_edges([raw], principal=principal)

    async def verify_edge(
        self,
        edge_id: uuid.UUID,
        *,
        status: VerificationStatus,
        principal: str,
        note: str | None = None,
    ) -> LineageEdgeRead:
        edge = await self.validation.verify(edge_id, status=status, principal=principal, note=note)
        await self._project([edge])
        return LineageEdgeRead(
            id=edge.id,
            source_urn=edge.source.urn,
            target_urn=edge.target.urn,
            relationship=edge.relationship_type,
            transformation=edge.transformation,
            level=edge.level,
            method=edge.method,
            confidence=edge.confidence,
            verified=edge.verified,
            verification_status=edge.verification_status,
            observed_at=edge.observed_at,
            evidence=edge.evidence,
        )

    async def review_queue(self, *, limit: int = 50) -> list[LineageEdgeRead]:
        rows = await self.validation.review_queue(limit=limit)
        return [
            LineageEdgeRead(
                id=row.id,
                source_urn=row.source.urn,
                target_urn=row.target.urn,
                relationship=row.relationship_type,
                transformation=row.transformation,
                level=row.level,
                method=row.method,
                confidence=row.confidence,
                verified=row.verified,
                verification_status=row.verification_status,
                observed_at=row.observed_at,
                evidence=row.evidence,
            )
            for row in rows
        ]

    async def stats(self) -> dict[str, object]:
        return await self.lineage_repo.stats()

    async def neighbour_counts(self, entity_urn: str) -> tuple[int, int]:
        entity = await self.metadata_repo.get_by_urn(entity_urn)
        if entity is None:
            return 0, 0
        return await self.lineage_repo.count_neighbours(entity.id)


def _to_create_schema(edge: RawLineage) -> LineageEdgeCreate:
    return LineageEdgeCreate(
        source_urn=edge.source_urn,
        target_urn=edge.target_urn,
        relationship=edge.relationship,
        level=edge.level,
        method=edge.method,
        transformation=edge.transformation,
        pipeline_urn=edge.pipeline_urn,
        job_run_id=edge.job_run_id,
        confidence=edge.confidence,
        observed_at=edge.observed_at,
        evidence=edge.evidence,
    )


__all__ = [
    "LineageService",
    "edge_to_graph_edge",
    "entity_to_graph_node",
    "graph_edge_to_schema",
    "graph_node_to_schema",
]
