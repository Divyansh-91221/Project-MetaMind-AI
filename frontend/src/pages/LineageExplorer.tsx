import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftRight, Bot, Gauge, GitBranch, SearchCheck, ShieldCheck } from 'lucide-react';
import { useApi } from '@/hooks';
import { lineageApi } from '@/services/lineageApi';
import { AsyncBoundary, Badge, Card, EmptyState, PageHeader, SearchBar } from '@/components/common';
import { LineageGraphView, LineageLegend } from '@/components/lineage';
import type { Direction, LineageLevel } from '@/types';

/** Interactive lineage exploration with direction, depth and level controls. */
export function LineageExplorer() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const urn = params.get('urn');

  const [direction, setDirection] = useState<Direction>('BOTH');
  const [depth, setDepth] = useState(4);
  const [level, setLevel] = useState<LineageLevel | ''>('');
  const [includeInferred, setIncludeInferred] = useState(true);

  const graph = useApi(() => {
    if (!urn) return Promise.resolve(null);
    const options = {
      depth,
      level: level || undefined,
      include_inferred: includeInferred,
    };
    if (direction === 'UPSTREAM') return lineageApi.upstream(urn, options);
    if (direction === 'DOWNSTREAM') return lineageApi.downstream(urn, options);
    return lineageApi.both(urn, options);
  }, [urn, direction, depth, level, includeInferred]);

  const summary = useMemo(() => {
    if (!graph.data) {
      return {
        nodes: 0,
        edges: 0,
        inferred: 0,
        verified: 0,
      };
    }
    const inferred = graph.data.edges.filter((edge) => edge.method === 'AI_INFERRED').length;
    const verified = graph.data.edges.filter((edge) => edge.verified).length;
    return {
      nodes: graph.data.nodes.length,
      edges: graph.data.edges.length,
      inferred,
      verified,
    };
  }, [graph.data]);

  if (!urn) {
    return (
      <>
        <PageHeader
          title="Lineage Explorer"
          description="Trace where data comes from and where it goes, at table and column level."
        />
        <Card>
          <SearchBar autoFocus onSelect={(hit) => setParams({ urn: hit.urn })} />
        </Card>
        <EmptyState
          title="Select an asset to trace."
          hint="Try snowflake.sales, sap.customer or the Monthly Revenue KPI."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Lineage Explorer"
        description={`Trace path for ${urn}`}
        actions={
          <div className="row">
            <button
              type="button"
              className="button"
              onClick={() => navigate(`/impact?urn=${encodeURIComponent(urn)}`)}
            >
              Run impact analysis
            </button>
            <button
              type="button"
              className="button primary"
              onClick={() => navigate(`/copilot?urn=${encodeURIComponent(urn)}`)}
            >
              <Bot size={14} /> Ask Copilot
            </button>
          </div>
        }
      />

      <div className="lineage-metrics-grid">
        <div className="metric-panel">
          <span className="metric-head"><SearchCheck size={15} /> Nodes</span>
          <strong>{summary.nodes}</strong>
          <span className="faint small">Distinct assets in traversal scope</span>
        </div>
        <div className="metric-panel">
          <span className="metric-head"><GitBranch size={15} /> Relationships</span>
          <strong>{summary.edges}</strong>
          <span className="faint small">Resolved lineage edges for current query</span>
        </div>
        <div className="metric-panel">
          <span className="metric-head"><Gauge size={15} /> Verified</span>
          <strong>{summary.verified}</strong>
          <span className="faint small">Human-confirmed lineage relations</span>
        </div>
        <div className="metric-panel">
          <span className="metric-head"><ShieldCheck size={15} /> AI-inferred</span>
          <strong>{summary.inferred}</strong>
          <span className="faint small">Requires stewardship review</span>
        </div>
      </div>

      <Card className="lineage-controls-card">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span className="metric-head"><ArrowLeftRight size={14} /> Search and traversal controls</span>
          <Badge tone={includeInferred ? 'inferred' : 'ok'}>
            {includeInferred ? 'Includes inferred' : 'Verified only'}
          </Badge>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <SearchBar onSelect={(hit) => setParams({ urn: hit.urn })} placeholder="Trace another asset..." />
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <select
            className="select"
            style={{ width: 150 }}
            value={direction}
            onChange={(event) => setDirection(event.target.value as Direction)}
            aria-label="Direction"
          >
            <option value="BOTH">Both directions</option>
            <option value="UPSTREAM">Upstream</option>
            <option value="DOWNSTREAM">Downstream</option>
          </select>
          <select
            className="select"
            style={{ width: 130 }}
            value={depth}
            onChange={(event) => setDepth(Number(event.target.value))}
            aria-label="Depth"
          >
            {[1, 2, 3, 4, 6, 8, 10].map((value) => (
              <option key={value} value={value}>
                Depth {value}
              </option>
            ))}
          </select>
          <select
            className="select"
            style={{ width: 150 }}
            value={level}
            onChange={(event) => setLevel(event.target.value as LineageLevel | '')}
            aria-label="Lineage level"
          >
            <option value="">All levels</option>
            <option value="TABLE">Table level</option>
            <option value="COLUMN">Column level</option>
          </select>
          <label className="row small muted" style={{ gap: 6 }}>
            <input
              type="checkbox"
              checked={includeInferred}
              onChange={(event) => setIncludeInferred(event.target.checked)}
            />
            Include AI-inferred
          </label>
        </div>
        <div style={{ marginTop: 12 }}>
          <LineageLegend />
        </div>
      </Card>

      <Card title="Lineage graph" className="lineage-graph-card">
        <AsyncBoundary {...graph} onRetry={graph.reload} emptyTitle="No lineage found.">
          {(data) =>
            data && (
              <LineageGraphView
                graph={data}
                selectedUrn={urn}
                onSelect={(node) => setParams({ urn: node.urn })}
              />
            )
          }
        </AsyncBoundary>
      </Card>
    </>
  );
}
