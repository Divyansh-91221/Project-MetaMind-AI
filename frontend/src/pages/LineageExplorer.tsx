import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useApi } from '@/hooks';
import { lineageApi } from '@/services/lineageApi';
import { AsyncBoundary, Card, EmptyState, PageHeader, SearchBar } from '@/components/common';
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
        description={urn}
        actions={
          <button
            type="button"
            className="button"
            onClick={() => navigate(`/impact?urn=${encodeURIComponent(urn)}`)}
          >
            Run impact analysis
          </button>
        }
      />

      <Card>
        <div className="row">
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

      <Card title="Lineage graph">
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
