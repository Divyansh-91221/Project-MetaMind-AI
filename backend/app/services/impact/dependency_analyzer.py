"""Dependency analysis helpers used by impact analysis.

Pure functions over graph traversal results - no I/O - so they are cheap to unit test.
"""

from __future__ import annotations

from collections import defaultdict

from app.core.constants import ASSET_TYPES, EntityType
from app.graph.graph_models import GraphEdge, GraphNode, GraphTraversalResult

CRITICAL_TYPES = frozenset({EntityType.KPI, EntityType.DASHBOARD, EntityType.REPORT})


class DependencyAnalyzer:
    """Derives criticality, path confidence and single points of failure."""

    @staticmethod
    def index_edges_by_target(edges: list[GraphEdge]) -> dict[str, list[GraphEdge]]:
        index: dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in edges:
            index[edge.target_urn].append(edge)
        return index

    @classmethod
    def path_metrics(
        cls, result: GraphTraversalResult, node_urn: str
    ) -> tuple[float, bool]:
        """Weakest confidence and whether any AI-inferred edge is involved.

        Walks backwards from the node to the root so the answer reflects the *whole* chain,
        which is what a change-impact reviewer actually needs to trust.
        """
        by_target = cls.index_edges_by_target(result.edges)
        confidence = 1.0
        inferred = False
        visited: set[str] = set()
        frontier = [node_urn]

        while frontier:
            current = frontier.pop()
            if current in visited or current == result.root_urn:
                continue
            visited.add(current)
            incoming = by_target.get(current, [])
            if not incoming:
                continue
            best = max(incoming, key=lambda edge: edge.confidence)
            confidence = min(confidence, best.confidence)
            inferred = inferred or best.is_inferred
            frontier.append(best.source_urn)

        return round(confidence, 3), inferred

    @staticmethod
    def criticality(node: GraphNode, *, has_owner: bool) -> str:
        """Simple, explainable criticality heuristic.

        TODO: incorporate usage telemetry (dashboard views, query counts) and business
        criticality tags once those signals are ingested.
        """
        if node.entity_type in CRITICAL_TYPES:
            return "HIGH"
        if node.entity_type in ASSET_TYPES and not has_owner:
            return "MEDIUM"
        if node.entity_type is EntityType.COLUMN:
            return "LOW"
        return "MEDIUM"

    @staticmethod
    def single_points_of_failure(result: GraphTraversalResult) -> list[GraphNode]:
        """Upstream assets that every path depends on (fan-out > 1, fan-in == 0)."""
        out_degree: dict[str, int] = defaultdict(int)
        in_degree: dict[str, int] = defaultdict(int)
        for edge in result.edges:
            out_degree[edge.source_urn] += 1
            in_degree[edge.target_urn] += 1

        return [
            node
            for node in result.nodes
            if node.urn != result.root_urn
            and out_degree.get(node.urn, 0) > 1
            and in_degree.get(node.urn, 0) == 0
        ]

    @staticmethod
    def summarise(nodes: list[GraphNode]) -> tuple[dict[str, int], dict[str, int]]:
        by_type: dict[str, int] = defaultdict(int)
        by_platform: dict[str, int] = defaultdict(int)
        for node in nodes:
            by_type[node.entity_type.value] += 1
            by_platform[node.platform] += 1
        return dict(by_type), dict(by_platform)
