"""Impact analysis service.

Answers "what will break if this changes?" by walking the downstream closure, attaching
ownership, flagging inferred paths and ranking by criticality.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import EntityType
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.graph.base import GraphStore
from app.graph.lineage_traversal import get_impact, get_upstream
from app.graph.neo4j_client import get_graph_store
from app.repositories.governance_repository import GovernanceRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.impact import (
    DependencyReport,
    ImpactAnalysisResult,
    ImpactedAsset,
    ImpactSummary,
)
from app.services.impact.dependency_analyzer import DependencyAnalyzer
from app.services.lineage.lineage_service import entity_to_graph_node, graph_node_to_schema

logger = get_logger(__name__)

_CRITICALITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


class ImpactService:
    def __init__(self, session: AsyncSession, graph: GraphStore | None = None) -> None:
        self.session = session
        self.graph = graph or get_graph_store()
        self.metadata_repo = MetadataRepository(session)
        self.governance_repo = GovernanceRepository(session)
        self.analyzer = DependencyAnalyzer()

    async def analyze(
        self,
        urn: str,
        *,
        depth: int | None = None,
        min_confidence: float | None = None,
    ) -> ImpactAnalysisResult:
        entity = await self.metadata_repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")

        result = await get_impact(
            self.graph,
            urn,
            depth=depth or settings.lineage_max_depth,
            min_confidence=(
                min_confidence if min_confidence is not None else settings.lineage_min_confidence
            ),
        )

        impacted_nodes = [node for node in result.nodes if node.urn != urn]
        entities = await self.metadata_repo.get_many_by_urns([n.urn for n in impacted_nodes])
        entity_by_urn = {item.urn: item for item in entities}
        owners_by_id = await self.governance_repo.owners_for_entities(
            [item.id for item in entities]
        )

        impacted: list[ImpactedAsset] = []
        for node in impacted_nodes:
            row = entity_by_urn.get(node.urn)
            owners = owners_by_id.get(row.id, []) if row else []
            confidence, inferred = self.analyzer.path_metrics(result, node.urn)
            impacted.append(
                ImpactedAsset(
                    urn=node.urn,
                    name=node.name,
                    qualified_name=node.qualified_name,
                    entity_type=node.entity_type,
                    platform=node.platform,
                    distance=node.depth,
                    path_confidence=confidence,
                    contains_inferred_lineage=inferred,
                    owners=owners,
                    criticality=self.analyzer.criticality(node, has_owner=bool(owners)),
                    reason=(
                        f"{node.depth} hop(s) downstream of {entity.qualified_name}"
                        + (" via an AI-inferred edge" if inferred else "")
                    ),
                )
            )

        impacted.sort(
            key=lambda asset: (_CRITICALITY_ORDER.get(asset.criticality, 3), asset.distance)
        )

        by_type, by_platform = self.analyzer.summarise(impacted_nodes)
        summary = ImpactSummary(
            total_impacted=len(impacted),
            by_entity_type=by_type,
            by_platform=by_platform,
            critical_assets=sum(1 for a in impacted if a.criticality == "HIGH"),
            dashboards_affected=by_type.get(EntityType.DASHBOARD.value, 0),
            kpis_affected=by_type.get(EntityType.KPI.value, 0),
            inferred_paths=sum(1 for a in impacted if a.contains_inferred_lineage),
        )

        owners_to_notify = [
            {"owner": owner, "assets": sorted({a.qualified_name for a in impacted if owner in a.owners})}
            for owner in sorted({owner for asset in impacted for owner in asset.owners})
        ]

        logger.info(
            "impact_analysis_completed",
            extra={"urn": urn, "impacted": len(impacted), "critical": summary.critical_assets},
        )

        return ImpactAnalysisResult(
            root=graph_node_to_schema(entity_to_graph_node(entity)),
            summary=summary,
            impacted_assets=impacted,
            owners_to_notify=owners_to_notify,
            blast_radius_depth=max((asset.distance for asset in impacted), default=0),
            truncated=result.truncated,
        )

    async def dependencies(self, urn: str, *, depth: int | None = None) -> DependencyReport:
        """Upstream view - what this asset relies on."""
        entity = await self.metadata_repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")

        result = await get_upstream(self.graph, urn, depth=depth)
        direct = [node for node in result.nodes if node.depth == 1]
        transitive = [node for node in result.nodes if node.depth > 1]
        unverified = sum(1 for edge in result.edges if not edge.verified)

        return DependencyReport(
            root=graph_node_to_schema(entity_to_graph_node(entity)),
            direct_dependencies=[graph_node_to_schema(node) for node in direct],
            transitive_dependencies=[graph_node_to_schema(node) for node in transitive],
            single_points_of_failure=[
                graph_node_to_schema(node) for node in self.analyzer.single_points_of_failure(result)
            ],
            unverified_dependency_count=unverified,
        )
