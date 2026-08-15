import { useMemo } from 'react';
import type { LineageEdge, LineageGraph, LineageNode } from '@/types';
import { Badge, ConfidenceBadge } from '@/components/common/Badge';
import { ENTITY_ICONS, methodLabel } from '@/utils/format';

/**
 * Layered lineage view.
 *
 * Nodes are grouped by traversal depth into columns, which communicates flow direction and
 * hop distance without pulling in a graph-rendering library. Edges are listed beneath with
 * their transformation, method and confidence - the details a data engineer actually needs.
 *
 * TODO: replace with an interactive canvas (React Flow / Cytoscape) with column-level
 * expansion once graphs grow beyond a few dozen nodes.
 */
export function LineageGraphView({
  graph,
  selectedUrn,
  onSelect,
}: {
  graph: LineageGraph;
  selectedUrn?: string | null;
  onSelect?: (node: LineageNode) => void;
}) {
  const columns = useMemo(() => {
    const byDepth = new Map<number, LineageNode[]>();
    for (const node of graph.nodes) {
      const bucket = byDepth.get(node.depth) ?? [];
      bucket.push(node);
      byDepth.set(node.depth, bucket);
    }
    return [...byDepth.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([depth, nodes]) => ({
        depth,
        nodes: nodes.sort((a, b) => a.qualified_name.localeCompare(b.qualified_name)),
      }));
  }, [graph.nodes]);

  if (graph.nodes.length === 0) {
    return <div className="state">No lineage has been registered for this asset yet.</div>;
  }

  const label = (depth: number) => {
    if (depth === 0) return 'Selected asset';
    return graph.direction === 'UPSTREAM'
      ? `${depth} hop${depth > 1 ? 's' : ''} upstream`
      : `${depth} hop${depth > 1 ? 's' : ''} downstream`;
  };

  return (
    <div>
      <div className="lineage-canvas">
        {columns.map((column) => (
          <div className="lineage-column" key={column.depth}>
            <div className="lineage-column-label">{label(column.depth)}</div>
            {column.nodes.map((node) => (
              <button
                key={node.urn}
                type="button"
                className={[
                  'lineage-node',
                  node.depth === 0 ? 'root' : '',
                  selectedUrn === node.urn ? 'selected' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => onSelect?.(node)}
              >
                <div className="lineage-node-name">
                  <span aria-hidden style={{ marginRight: 6 }}>{ENTITY_ICONS[node.entity_type]}</span>
                  {node.qualified_name}
                </div>
                <div className="lineage-node-meta">
                  {node.entity_type} · {node.platform}
                </div>
              </button>
            ))}
          </div>
        ))}
      </div>

      {graph.truncated && (
        <div className="banner" style={{ marginBottom: 12 }}>
          Traversal was truncated at the depth limit. Increase the depth to see more.
        </div>
      )}

      <EdgeList edges={graph.edges} nodes={graph.nodes} />
    </div>
  );
}

function EdgeList({ edges, nodes }: { edges: LineageEdge[]; nodes: LineageNode[] }) {
  const names = useMemo(
    () => new Map(nodes.map((node) => [node.urn, node.qualified_name])),
    [nodes],
  );

  if (edges.length === 0) return null;

  return (
    <div className="edge-list">
      <h3 style={{ marginTop: 20 }}>Relationships ({edges.length})</h3>
      {edges
        .slice()
        .sort((a, b) => b.confidence - a.confidence)
        .map((edge, index) => (
          <div
            key={edge.id ?? `${edge.source_urn}-${edge.target_urn}-${index}`}
            className={`edge-row${edge.method === 'AI_INFERRED' ? ' inferred' : ''}`}
          >
            <div>
              <div className="mono small">
                {names.get(edge.source_urn) ?? edge.source_urn}
                {' \u2192 '}
                {names.get(edge.target_urn) ?? edge.target_urn}
              </div>
              <div className="faint small">
                {edge.relationship} · {edge.level.toLowerCase()} level · {methodLabel(edge.method)}
                {edge.transformation ? (
                  <>
                    {' · '}
                    <code>{edge.transformation}</code>
                  </>
                ) : null}
              </div>
            </div>
            <div className="row nowrap">
              {edge.method === 'AI_INFERRED' && <Badge tone="inferred">Needs review</Badge>}
              <ConfidenceBadge
                confidence={edge.confidence}
                inferred={edge.method === 'AI_INFERRED'}
                verified={edge.verified}
              />
            </div>
          </div>
        ))}
    </div>
  );
}
