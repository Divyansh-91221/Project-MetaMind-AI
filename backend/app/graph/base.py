"""``GraphStore`` abstraction plus an in-memory implementation.

Rule 9 of the architecture: graph storage must be replaceable. Services depend on this
protocol, never on the Neo4j driver. The in-memory store keeps unit tests fast and lets the
API run with ``GRAPH_STORE=memory`` when no graph database is available.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Protocol, runtime_checkable

from app.core.constants import Direction, LineageLevel, RelationshipType
from app.graph.graph_models import GraphEdge, GraphNode, GraphPath, GraphTraversalResult

MAX_RESULT_NODES = 2000


@runtime_checkable
class GraphStore(Protocol):
    """Storage-agnostic contract for the lineage graph."""

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def health_check(self) -> bool: ...

    async def upsert_nodes(self, nodes: list[GraphNode]) -> int: ...

    async def upsert_edges(self, edges: list[GraphEdge]) -> int: ...

    async def get_node(self, urn: str) -> GraphNode | None: ...

    async def traverse(
        self,
        urn: str,
        *,
        direction: Direction,
        depth: int,
        relationships: frozenset[RelationshipType] | None = None,
        level: LineageLevel | None = None,
        min_confidence: float = 0.0,
        include_inferred: bool = True,
    ) -> GraphTraversalResult: ...

    async def find_paths(
        self, source_urn: str, target_urn: str, *, max_depth: int = 10
    ) -> list[GraphPath]: ...

    async def related_assets(self, urn: str, *, depth: int = 2) -> GraphTraversalResult: ...

    async def clear(self) -> None: ...


class InMemoryGraphStore:
    """Dictionary-backed :class:`GraphStore`.

    Not intended for production volumes - it exists for tests and for degraded local runs.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._out: dict[str, list[GraphEdge]] = defaultdict(list)
        self._in: dict[str, list[GraphEdge]] = defaultdict(list)

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True

    async def upsert_nodes(self, nodes: list[GraphNode]) -> int:
        for node in nodes:
            self._nodes[node.urn] = node
        return len(nodes)

    async def upsert_edges(self, edges: list[GraphEdge]) -> int:
        for edge in edges:
            key = (edge.source_urn, edge.target_urn, edge.relationship, edge.level)
            self._out[edge.source_urn] = [
                e
                for e in self._out[edge.source_urn]
                if (e.source_urn, e.target_urn, e.relationship, e.level) != key
            ]
            self._in[edge.target_urn] = [
                e
                for e in self._in[edge.target_urn]
                if (e.source_urn, e.target_urn, e.relationship, e.level) != key
            ]
            self._out[edge.source_urn].append(edge)
            self._in[edge.target_urn].append(edge)
        return len(edges)

    async def get_node(self, urn: str) -> GraphNode | None:
        return self._nodes.get(urn)

    def _keep(
        self,
        edge: GraphEdge,
        relationships: frozenset[RelationshipType] | None,
        level: LineageLevel | None,
        min_confidence: float,
        include_inferred: bool,
    ) -> bool:
        if relationships is not None and edge.relationship not in relationships:
            return False
        if level is not None and edge.level is not level:
            return False
        if edge.confidence < min_confidence:
            return False
        return not (edge.is_inferred and not include_inferred)

    async def traverse(
        self,
        urn: str,
        *,
        direction: Direction,
        depth: int,
        relationships: frozenset[RelationshipType] | None = None,
        level: LineageLevel | None = None,
        min_confidence: float = 0.0,
        include_inferred: bool = True,
    ) -> GraphTraversalResult:
        result = GraphTraversalResult(root_urn=urn)
        root = self._nodes.get(urn)
        if root is None:
            return result

        seen: dict[str, int] = {urn: 0}
        result.nodes.append(_at_depth(root, 0))
        queue: deque[tuple[str, int]] = deque([(urn, 0)])

        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                result.truncated = True
                continue

            neighbours: list[tuple[GraphEdge, str]] = []
            if direction in (Direction.UPSTREAM, Direction.BOTH):
                neighbours += [(e, e.source_urn) for e in self._in.get(current, [])]
            if direction in (Direction.DOWNSTREAM, Direction.BOTH):
                neighbours += [(e, e.target_urn) for e in self._out.get(current, [])]

            for edge, neighbour_urn in neighbours:
                if not self._keep(edge, relationships, level, min_confidence, include_inferred):
                    continue
                result.edges.append(edge)
                if neighbour_urn in seen:
                    continue
                node = self._nodes.get(neighbour_urn)
                if node is None:
                    continue
                if len(result.nodes) >= MAX_RESULT_NODES:
                    result.truncated = True
                    break
                seen[neighbour_urn] = current_depth + 1
                result.nodes.append(_at_depth(node, current_depth + 1))
                queue.append((neighbour_urn, current_depth + 1))

        result.edges = _dedupe_edges(result.edges)
        return result

    async def find_paths(
        self, source_urn: str, target_urn: str, *, max_depth: int = 10
    ) -> list[GraphPath]:
        paths: list[GraphPath] = []
        stack: list[tuple[str, list[GraphEdge], set[str]]] = [(source_urn, [], {source_urn})]
        while stack:
            current, edges, visited = stack.pop()
            if current == target_urn and edges:
                nodes = [self._nodes[e.source_urn] for e in edges if e.source_urn in self._nodes]
                if target_urn in self._nodes:
                    nodes.append(self._nodes[target_urn])
                paths.append(GraphPath(nodes=nodes, edges=list(edges)))
                continue
            if len(edges) >= max_depth:
                continue
            for edge in self._out.get(current, []):
                if edge.target_urn in visited:
                    continue
                stack.append((edge.target_urn, [*edges, edge], visited | {edge.target_urn}))
        return paths

    async def related_assets(self, urn: str, *, depth: int = 2) -> GraphTraversalResult:
        return await self.traverse(urn, direction=Direction.BOTH, depth=depth)

    async def clear(self) -> None:
        self._nodes.clear()
        self._out.clear()
        self._in.clear()


def _at_depth(node: GraphNode, depth: int) -> GraphNode:
    return GraphNode(
        urn=node.urn,
        entity_type=node.entity_type,
        name=node.name,
        qualified_name=node.qualified_name,
        platform=node.platform,
        description=node.description,
        depth=depth,
        properties=dict(node.properties),
    )


def _dedupe_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[GraphEdge] = []
    for edge in edges:
        key = (edge.source_urn, edge.target_urn, edge.relationship.value, edge.level.value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(edge)
    return unique
