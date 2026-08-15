import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApi } from '@/hooks';
import { metadataApi } from '@/services/metadataApi';
import { governanceApi, qualityApi } from '@/services/governanceApi';
import { AsyncBoundary, Card, EmptyState, PageHeader, SearchBar } from '@/components/common';
import { Badge } from '@/components/common/Badge';
import { AssetHeader, ColumnTable } from '@/components/metadata';
import { GovernancePanel } from '@/components/governance';
import { useAppContext } from '@/app/providers';
import { formatAgeHours, formatDate } from '@/utils/format';

/** Full asset view: technical metadata, business context, governance and quality. */
export function AssetDetails() {
  const [params] = useSearchParams();
  const urn = params.get('urn');
  const { setActiveUrn } = useAppContext();

  useEffect(() => {
    setActiveUrn(urn);
  }, [urn, setActiveUrn]);

  const asset = useApi(() => (urn ? metadataApi.get(urn) : Promise.resolve(null)), [urn]);
  const governance = useApi(
    () => (urn ? governanceApi.profile(urn) : Promise.resolve(null)),
    [urn],
  );
  const quality = useApi(() => (urn ? qualityApi.profile(urn) : Promise.resolve(null)), [urn]);

  if (!urn) {
    return (
      <>
        <PageHeader title="Asset details" description="Search for an asset to inspect it." />
        <Card>
          <SearchBar autoFocus />
        </Card>
        <EmptyState title="No asset selected." hint="Use the search box above to pick one." />
      </>
    );
  }

  return (
    <AsyncBoundary {...asset} onRetry={asset.reload} emptyTitle="Asset not found.">
      {(data) =>
        data && (
          <>
            <AssetHeader asset={data} />

            <div className="grid grid-2">
              <Card title="Business context">
                {data.business_terms.length === 0 ? (
                  <p className="faint">No business terms are linked to this asset.</p>
                ) : (
                  data.business_terms.map((term) => (
                    <div key={term.name} style={{ marginBottom: 12 }}>
                      <strong>{term.name}</strong> {term.is_kpi && <Badge tone="accent">KPI</Badge>}
                      <div className="muted small">{term.definition}</div>
                    </div>
                  ))
                )}
              </Card>

              <Card title="Data quality">
                <AsyncBoundary {...quality} onRetry={quality.reload} emptyTitle="No quality data.">
                  {(profile) =>
                    profile && (
                      <div>
                        <div className="row">
                          <Badge
                            tone={
                              profile.overall_status === 'PASS'
                                ? 'ok'
                                : profile.overall_status === 'FAIL'
                                  ? 'error'
                                  : 'warn'
                            }
                          >
                            {profile.overall_status}
                          </Badge>
                          {profile.freshness && (
                            <span className="muted small">
                              Updated {formatAgeHours(profile.freshness.age_hours)}
                              {profile.freshness.expected_interval_hours
                                ? ` (SLA ${profile.freshness.expected_interval_hours}h)`
                                : ''}
                            </span>
                          )}
                        </div>
                        {profile.freshness?.failure_reason && (
                          <div className="banner" style={{ marginTop: 10 }}>
                            {profile.freshness.failure_reason}
                          </div>
                        )}
                        {profile.metrics.length > 0 && (
                          <table className="table" style={{ marginTop: 12 }}>
                            <thead>
                              <tr>
                                <th>Metric</th>
                                <th>Value</th>
                                <th>Status</th>
                                <th>Measured</th>
                              </tr>
                            </thead>
                            <tbody>
                              {profile.metrics.slice(0, 6).map((metric) => (
                                <tr key={`${metric.metric_name}-${metric.measured_at}`}>
                                  <td>{metric.metric_name}</td>
                                  <td>
                                    {metric.value ?? '-'} {metric.unit ?? ''}
                                  </td>
                                  <td>{metric.status}</td>
                                  <td className="faint small">{formatDate(metric.measured_at)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    )
                  }
                </AsyncBoundary>
              </Card>
            </div>

            <Card title={`Columns (${data.columns.length})`}>
              <ColumnTable columns={data.columns} />
            </Card>

            <Card title="Governance">
              <AsyncBoundary
                {...governance}
                onRetry={governance.reload}
                emptyTitle="No governance information."
              >
                {(profile) => profile && <GovernancePanel profile={profile} />}
              </AsyncBoundary>
            </Card>
          </>
        )
      }
    </AsyncBoundary>
  );
}
