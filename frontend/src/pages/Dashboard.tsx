import { Link } from 'react-router-dom';
import { useApi } from '@/hooks';
import { metadataApi } from '@/services/metadataApi';
import { lineageApi } from '@/services/lineageApi';
import { governanceApi, qualityApi } from '@/services/governanceApi';
import { AsyncBoundary, Card, PageHeader, SearchBar, Stat } from '@/components/common';
import { Badge } from '@/components/common/Badge';
import { formatNumber } from '@/utils/format';

/** Landing page: catalog health, lineage trust and the current governance gaps. */
export function Dashboard() {
  const summary = useApi(() => metadataApi.summary(), []);
  const review = useApi(() => lineageApi.reviewQueue(5), []);
  const unowned = useApi(() => governanceApi.unowned(5), []);
  const stale = useApi(() => qualityApi.stale(5), []);

  return (
    <>
      <PageHeader
        title="Enterprise Metadata Copilot"
        description="Discover, understand, trace and govern enterprise data across SAP, Databricks, Snowflake and Power BI."
      />

      <Card>
        <SearchBar />
      </Card>

      <AsyncBoundary {...summary} onRetry={summary.reload}>
        {(data) => {
          const totalEntities = Object.values(data.entities_by_type).reduce((a, b) => a + b, 0);
          const verifiedShare = data.lineage.total_edges
            ? Math.round((data.lineage.verified_edges / data.lineage.total_edges) * 100)
            : 0;

          return (
            <>
              <div className="grid grid-4" style={{ marginTop: 16 }}>
                <Stat label="Catalog assets" value={formatNumber(totalEntities)} />
                <Stat label="Lineage edges" value={formatNumber(data.lineage.total_edges)} />
                <Stat
                  label="Verified lineage"
                  value={`${verifiedShare}%`}
                  hint={`${data.lineage.verified_edges} of ${data.lineage.total_edges} edges`}
                />
                <Stat label="Data sources" value={formatNumber(data.data_sources)} />
              </div>

              <div className="grid grid-2" style={{ marginTop: 16 }}>
                <Card title="Assets by type">
                  <div className="row">
                    {Object.entries(data.entities_by_type)
                      .sort((a, b) => b[1] - a[1])
                      .map(([type, count]) => (
                        <Badge key={type}>
                          {type} · {count}
                        </Badge>
                      ))}
                  </div>
                </Card>

                <Card title="Lineage by extraction method">
                  <div className="row">
                    {Object.entries(data.lineage.by_method).map(([method, count]) => (
                      <Badge key={method} tone={method === 'AI_INFERRED' ? 'inferred' : 'default'}>
                        {method} · {count}
                      </Badge>
                    ))}
                  </div>
                  <p className="faint small" style={{ marginBottom: 0 }}>
                    AI-inferred relationships are suggestions only and must be verified by a
                    steward before they are treated as fact.
                  </p>
                </Card>
              </div>
            </>
          );
        }}
      </AsyncBoundary>

      <div className="grid grid-3" style={{ marginTop: 16 }}>
        <Card title="Lineage awaiting review">
          {review.data && review.data.length > 0 ? (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {review.data.map((edge) => (
                <li key={edge.id ?? `${edge.source_urn}-${edge.target_urn}`} className="small">
                  <span className="mono">{edge.source_urn.split(':').slice(4).join(':')}</span>
                  {' \u2192 '}
                  <span className="mono">{edge.target_urn.split(':').slice(4).join(':')}</span>
                  <Badge tone="inferred">{Math.round(edge.confidence * 100)}%</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="faint small">Nothing is waiting for verification.</p>
          )}
        </Card>

        <Card title="Assets without an owner">
          {unowned.data && unowned.data.length > 0 ? (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {unowned.data.map((asset) => (
                <li key={asset.urn} className="small">
                  <Link to={`/assets?urn=${encodeURIComponent(asset.urn)}`} className="mono">
                    {asset.qualified_name}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="faint small">Every catalogued asset has an owner.</p>
          )}
        </Card>

        <Card title="Stale assets">
          {stale.data && stale.data.length > 0 ? (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {stale.data.map((asset) => (
                <li key={String(asset.urn)} className="small">
                  <Link to={`/assets?urn=${encodeURIComponent(String(asset.urn))}`} className="mono">
                    {String(asset.qualified_name)}
                  </Link>{' '}
                  <Badge tone="warn">{String(asset.status)}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="faint small">All tracked assets are within their freshness SLA.</p>
          )}
        </Card>
      </div>
    </>
  );
}
