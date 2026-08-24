import { useState } from 'react';
import { useApi } from '@/hooks';
import { connectorsApi } from '@/services/connectorsApi';
import {
  AsyncBoundary,
  Badge,
  Card,
  ConfirmDialog,
  EmptyState,
  PageHeader,
} from '@/components/common';
import type { ConnectorDescriptor, DataSourceRead } from '@/types';
import { formatDate, formatNumber } from '@/utils/format';

type ConnectorState = 'Connected' | 'Ready' | 'Not configured' | 'Error';

function stateFor(connector: ConnectorDescriptor, sources: DataSourceRead[]): ConnectorState {
  const matching = sources.filter((source) => source.connector_type === connector.name);
  if (matching.some((source) => source.last_ingestion_status === 'SUCCESS')) return 'Connected';
  if (matching.some((source) => ['PARTIAL', 'FAILED'].includes(source.last_ingestion_status ?? '')))
    return 'Error';
  return connector.implemented ? 'Ready' : 'Not configured';
}

const STATE_TONE: Record<ConnectorState, 'ok' | 'accent' | 'default' | 'error'> = {
  Connected: 'ok',
  Ready: 'accent',
  'Not configured': 'default',
  Error: 'error',
};

const RUN_STATUS_TONE: Record<string, 'ok' | 'warn' | 'error' | 'default'> = {
  SUCCESS: 'ok',
  PARTIAL: 'warn',
  FAILED: 'error',
  RUNNING: 'default',
};

/** Connector inventory, ingestion run history and the demo reset utility. */
export function IngestionCenter() {
  const connectors = useApi(() => connectorsApi.list(), []);
  const sources = useApi(() => connectorsApi.sources(), []);
  const runs = useApi(() => connectorsApi.runs(20), []);
  const [resetMessage, setResetMessage] = useState<string | null>(null);

  const resetDemo = async () => {
    setResetMessage(null);
    const result = await connectorsApi.resetDemo();
    setResetMessage(
      `Reseeded ${result.entities_created + result.entities_updated} asset(s) and ` +
        `${result.lineage_edges_created + result.lineage_edges_updated} lineage edge(s).`,
    );
    sources.reload();
    runs.reload();
  };

  return (
    <>
      <PageHeader
        title="Ingestion Center"
        description="Connector inventory and ingestion run history. Only the demo and PostgreSQL connectors are fully implemented today; the rest are registered but not yet wired to a live source."
        actions={
          <ConfirmDialog
            title="Reset the demo environment?"
            description="This re-ingests the demo enterprise landscape, rebuilds the lineage graph and refreshes the search index. Safe to run repeatedly."
            confirmLabel="Reset demo data"
            tone="primary"
            onConfirm={resetDemo}
            trigger={(open) => (
              <button type="button" className="button primary" onClick={open}>
                Reset demo data
              </button>
            )}
          />
        }
      />

      {resetMessage && <div className="banner ok">{resetMessage}</div>}

      <Card title="Connectors">
        <AsyncBoundary {...connectors} onRetry={connectors.reload}>
          {(connectorList) => (
            <AsyncBoundary {...sources} onRetry={sources.reload}>
              {(sourceList) => (
                <div className="grid grid-3">
                  {connectorList.map((connector) => {
                    const state = stateFor(connector, sourceList);
                    return (
                      <Card key={connector.name} className="connector-card">
                        <div className="row" style={{ justifyContent: 'space-between' }}>
                          <strong>{connector.name}</strong>
                          <Badge tone={STATE_TONE[state]}>{state}</Badge>
                        </div>
                        <p className="muted small">{connector.description}</p>
                        <div className="row">
                          {connector.supports_lineage && <Badge>lineage</Badge>}
                          {connector.supports_column_lineage && <Badge>column lineage</Badge>}
                          {connector.supports_quality && <Badge>quality</Badge>}
                        </div>
                      </Card>
                    );
                  })}
                </div>
              )}
            </AsyncBoundary>
          )}
        </AsyncBoundary>
      </Card>

      <Card title="Ingestion runs">
        <AsyncBoundary {...runs} onRetry={runs.reload}>
          {(rows) =>
            rows.length === 0 ? (
              <EmptyState title="No ingestion runs recorded yet." hint="Run a connector or reset the demo data." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Connector</th>
                      <th>Status</th>
                      <th>Started</th>
                      <th>Completed</th>
                      <th>Assets</th>
                      <th>Lineage edges</th>
                      <th>Warnings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((run) => (
                      <tr key={run.run_id}>
                        <td className="mono">{run.connector}</td>
                        <td>
                          <Badge tone={RUN_STATUS_TONE[run.status] ?? 'default'}>{run.status}</Badge>
                        </td>
                        <td className="faint small">{formatDate(run.started_at)}</td>
                        <td className="faint small">{formatDate(run.completed_at)}</td>
                        <td>{formatNumber(run.assets_processed)}</td>
                        <td>{formatNumber(run.lineage_edges)}</td>
                        <td className="faint small">
                          {run.warnings.length > 0 ? `${run.warnings.length} warning(s)` : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </AsyncBoundary>
      </Card>
    </>
  );
}
