import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApi } from '@/hooks';
import { metadataApi } from '@/services/metadataApi';
import { governanceApi, qualityApi } from '@/services/governanceApi';
import { healthApi } from '@/services/connectorsApi';
import { AsyncBoundary, Card, EmptyState, HealthScoreGauge, PageHeader, SearchBar } from '@/components/common';
import { Badge } from '@/components/common/Badge';
import { AssetHeader, ColumnTable } from '@/components/metadata';
import { GovernancePanel } from '@/components/governance';
import { useAppContext } from '@/app/appContext';
import { formatAgeHours, formatDate } from '@/utils/format';
import { buildAssetEvidence } from '@/utils/explainability';

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
  const health = useApi(() => (urn ? healthApi.score(urn) : Promise.resolve(null)), [urn]);

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

            {health.data && (
              <Card className="health-card">
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <div>
                    <h3 style={{ marginBottom: 4 }}>Health score</h3>
                    <p className="faint small" style={{ marginBottom: 0 }}>
                      {health.data.label} - freshness, quality, ownership, governance and lineage,
                      weighted.
                    </p>
                  </div>
                  <HealthScoreGauge total={health.data.total} label={health.data.label} />
                </div>
                <div className="row" style={{ marginTop: 10 }}>
                  {Object.entries(health.data.components).map(([key, value]) => (
                    <Badge key={key} title={`${Math.round((health.data!.weights[key] ?? 0) * 100)}% weight`}>
                      {key} · {value}
                    </Badge>
                  ))}
                </div>
              </Card>
            )}

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

            <Card title="Why MetaMind knows this">
              <p className="faint small">
                Every claim below cites the exact catalog, lineage, governance or quality record
                behind it.
              </p>
              {buildAssetEvidence(data, governance.data ?? null, quality.data ?? null).map(
                (item, index) => (
                  <div className="evidence-item" key={`${item.title}-${index}`}>
                    <div className="row" style={{ justifyContent: 'space-between' }}>
                      <span className="evidence-title">{item.title}</span>
                      {item.inferred && <Badge tone="warn">Awaiting review</Badge>}
                    </div>
                    <div className="evidence-detail">{item.detail}</div>
                    <div className="evidence-source">
                      {item.kind} · {item.source}
                    </div>
                  </div>
                ),
              )}
            </Card>
          </>
        )
      }
    </AsyncBoundary>
  );
}
