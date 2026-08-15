"""Normalisation and de-duplication of raw lineage assertions.

Different extractors describe the same relationship in slightly different ways. Normalising
before persistence keeps the graph clean and lets the confidence scorer treat repeated
observations as corroboration rather than duplication.
"""

from __future__ import annotations

from collections import defaultdict

from app.connectors.base import RawLineage
from app.core.constants import LineageLevel, LineageMethod, RelationshipType
from app.core.logging import get_logger
from app.services.lineage.lineage_confidence import ConfidenceSignals, scorer
from app.utils.timestamps import utcnow

logger = get_logger(__name__)

EdgeKey = tuple[str, str, RelationshipType, LineageLevel]


class LineageNormalizer:
    """Cleans, de-duplicates and scores raw lineage before it reaches the repository."""

    def normalize(self, edges: list[RawLineage]) -> list[RawLineage]:
        """Merge duplicate assertions and assign a confidence score to each edge."""
        grouped: dict[EdgeKey, list[RawLineage]] = defaultdict(list)
        for edge in edges:
            cleaned = self._clean(edge)
            if cleaned is None:
                continue
            grouped[self._key(cleaned)].append(cleaned)

        merged: list[RawLineage] = []
        for group in grouped.values():
            merged.append(self._merge(group))
        return merged

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _key(edge: RawLineage) -> EdgeKey:
        return (edge.source_urn, edge.target_urn, edge.relationship, edge.level)

    def _clean(self, edge: RawLineage) -> RawLineage | None:
        if not edge.source_urn or not edge.target_urn:
            logger.debug("lineage_edge_dropped_missing_urn")
            return None
        if edge.source_urn == edge.target_urn:
            logger.debug("lineage_edge_dropped_self_reference", extra={"urn": edge.source_urn})
            return None
        if edge.transformation:
            edge.transformation = " ".join(edge.transformation.split())
        if edge.observed_at is None:
            edge.observed_at = utcnow()
        return edge

    def _merge(self, group: list[RawLineage]) -> RawLineage:
        """Collapse a group of identical edges into the best-supported single edge."""
        methods = {edge.method for edge in group}
        # Prefer the highest-trust method that observed this relationship.
        primary = max(group, key=lambda edge: _method_rank(edge.method))

        transformation = next((edge.transformation for edge in group if edge.transformation), None)
        pipeline_urn = next((edge.pipeline_urn for edge in group if edge.pipeline_urn), None)
        evidence: dict[str, object] = {}
        for edge in group:
            evidence.update(edge.evidence)
        if len(methods) > 1:
            evidence["corroborating_methods"] = sorted(method.value for method in methods)

        explicit = [edge.confidence for edge in group if edge.confidence is not None]
        if explicit and primary.method is LineageMethod.AI_INFERRED:
            # Never let an inferred edge inherit a high score from a corroborating claim.
            confidence = min(explicit)
        else:
            result = scorer.score(
                ConfidenceSignals(
                    method=primary.method,
                    has_transformation=bool(transformation),
                    has_pipeline_context=bool(pipeline_urn),
                    has_source_evidence=bool(evidence.get("sql") or evidence.get("source")),
                    corroborating_methods=len(methods),
                    observation_count=len(group),
                )
            )
            confidence = result.score
            evidence["confidence_explanation"] = result.explanation

        return RawLineage(
            source_urn=primary.source_urn,
            target_urn=primary.target_urn,
            relationship=primary.relationship,
            level=primary.level,
            method=primary.method,
            transformation=transformation,
            pipeline_urn=pipeline_urn,
            job_run_id=primary.job_run_id,
            confidence=confidence,
            observed_at=max(
                (edge.observed_at for edge in group if edge.observed_at), default=utcnow()
            ),
            evidence=evidence,
        )


def _method_rank(method: LineageMethod) -> int:
    order = {
        LineageMethod.MANUAL: 5,
        LineageMethod.OPENLINEAGE: 4,
        LineageMethod.SQL_PARSE: 3,
        LineageMethod.CONNECTOR_DECLARED: 2,
        LineageMethod.PIPELINE_METADATA: 1,
        LineageMethod.AI_INFERRED: 0,
    }
    return order.get(method, 0)


normalizer = LineageNormalizer()
