import { Link, useSearchParams } from 'react-router-dom';
import { useApi } from '@/hooks';
import { impactApi } from '@/services/impactApi';
import { AsyncBoundary, Card, EmptyState, PageHeader, SearchBar, Stat } from '@/components/common';
import { Badge } from '@/components/common/Badge';
import { formatConfidence } from '@/utils/format';

/** "What breaks if this changes?" - blast radius with owners to notify. */
export function ImpactAnalysis() {
  const [params, setParams] = useSearchParams();
  const urn = params.get('urn');

  const result = useApi(() => (urn ? impactApi.analyze(urn, 8) : Promise.resolve(null)), [urn]);

  if (!urn) {
    return (
      <>
        <PageHeader
          title="Impact Analysis"
          description="See every downstream asset a change would affect, and who needs to be told."
        />
        <Card>
          <SearchBar autoFocus onSelect={(hit) => setParams({ urn: hit.urn })} />
        </Card>
        <EmptyState title="Select an asset to analyse." />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Impact Analysis" description={urn} />

      <Card>
        <SearchBar onSelect={(hit) => setParams({ urn: hit.urn })} placeholder="Analyse another asset..." />
      </Card>

      <AsyncBoundary {...result} onRetry={result.reload} emptyTitle="No impact data.">
        {(data) =>
          data && (
            <>
              <div className="grid grid-4" style={{ marginTop: 16 }}>
                <Stat label="Impacted assets" value={data.summary.total_impacted} />
                <Stat label="High criticality" value={data.summary.critical_assets} />
                <Stat
                  label="Dashboards / KPIs"
                  value={`${data.summary.dashboards_affected} / ${data.summary.kpis_affected}`}
                />
                <Stat
                  label="Inferred paths"
                  value={data.summary.inferred_paths}
                  hint="Reached only through unverified lineage"
                />
              </div>

              {data.summary.inferred_paths > 0 && (
                <div className="banner" style={{ marginTop: 16 }}>
                  {data.summary.inferred_paths} impacted asset(s) are reached only through
                  AI-inferred lineage. Verify those relationships before acting on this analysis.
                </div>
              )}

              <Card title={`Impacted assets (${data.impacted_assets.length})`}>
                {data.impacted_assets.length === 0 ? (
                  <p className="faint">Nothing downstream depends on this asset.</p>
                ) : (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Asset</th>
                        <th>Type</th>
                        <th>Hops</th>
                        <th>Criticality</th>
                        <th>Path confidence</th>
                        <th>Owners</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.impacted_assets.map((asset) => (
                        <tr key={asset.urn}>
                          <td className="mono">
                            <Link to={`/assets?urn=${encodeURIComponent(asset.urn)}`}>
                              {asset.qualified_name}
                            </Link>
                          </td>
                          <td className="nowrap">{asset.entity_type}</td>
                          <td>{asset.distance}</td>
                          <td>
                            <Badge tone={asset.criticality.toLowerCase() as 'high' | 'medium' | 'low'}>
                              {asset.criticality}
                            </Badge>
                          </td>
                          <td>
                            {formatConfidence(asset.path_confidence)}
                            {asset.contains_inferred_lineage && <Badge tone="inferred">inferred</Badge>}
                          </td>
                          <td className="muted small">{asset.owners.join(', ') || 'unowned'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>

              <Card title="Owners to notify">
                {data.owners_to_notify.length === 0 ? (
                  <p className="faint">No owners are registered for the impacted assets.</p>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {data.owners_to_notify.map((entry) => (
                      <li key={entry.owner}>
                        <strong>{entry.owner}</strong>
                        <span className="faint small"> — {entry.assets.join(', ')}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </>
          )
        }
      </AsyncBoundary>
    </>
  );
}
