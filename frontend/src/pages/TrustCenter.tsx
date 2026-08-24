import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, ShieldAlert } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { AsyncBoundary, Badge, Card, EmptyState, PageHeader, SearchBar } from '@/components/common';
import { useApi } from '@/hooks';
import { trustApi } from '@/services/trustApi';
import type { AssetTrustSummary } from '@/types';
import { renderMaybePercent, trustToneFromStatus } from '@/utils/trust';

interface TrustCenterProps {
  focusSection?: 'sensitive';
}

export function TrustCenter({ focusSection }: TrustCenterProps) {
  const [params, setParams] = useSearchParams();
  const urn = params.get('urn');

  const trust = useApi(() => (urn ? trustApi.summary(urn) : Promise.resolve(null)), [urn]);

  if (!urn) {
    return (
      <>
        <PageHeader
          title={focusSection === 'sensitive' ? 'PII Detection' : 'Trust Center'}
          description="Can I trust this data asset, and what factors affect that trust?"
        />
        <Card>
          <SearchBar
            autoFocus
            placeholder="Select an asset to evaluate trust"
            onSelect={(hit) => setParams({ urn: hit.urn })}
          />
        </Card>
        <EmptyState
          title="Select an asset to see trust signals."
          hint="Trust Center summarizes quality, freshness, dependency risk, ownership and sensitive-data detections."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={focusSection === 'sensitive' ? 'PII Detection' : 'Trust Center'}
        description="Can I trust this data asset, and what factors affect that trust?"
        actions={
          <div className="row">
            <Link to={`/impact?urn=${encodeURIComponent(urn)}`} className="button">View Impact Analysis</Link>
            <Link to="/governance" className="button">Open Governance</Link>
          </div>
        }
      />

      <Card>
        <SearchBar onSelect={(hit) => setParams({ urn: hit.urn })} placeholder="Evaluate another asset..." />
      </Card>

      <AsyncBoundary {...trust} onRetry={trust.reload} emptyTitle="No trust summary available.">
        {(data) => <TrustCenterBody data={data} focusSection={focusSection} />}
      </AsyncBoundary>
    </>
  );
}

function TrustCenterBody({ data, focusSection }: { data: AssetTrustSummary; focusSection?: 'sensitive' }) {
  const sensitivePending = data.sensitive_data.filter((row) => row.review_status === 'PENDING_REVIEW').length;

  return (
    <div className="trust-center-layout">
      {data.fallback_mode && (
        <div className="banner" role="status" aria-live="polite">
          Trust summary is currently running in compatibility mode using existing metadata, quality,
          lineage, impact, and governance APIs because the dedicated trust endpoint is not available on
          this backend.
        </div>
      )}

      <section className="trust-header">
        <div>
          <h2>{data.asset_name}</h2>
          <p className="faint" style={{ marginTop: 0 }}>{data.description || data.entity_urn}</p>
          <div className="trust-meta-row">
            <Badge tone="default">{data.platform}</Badge>
            <Badge tone="default">{data.asset_type}</Badge>
            <span className="small faint">Owner: {data.owner || 'Unassigned'}</span>
            <span className="small faint">
              Last updated: {data.last_updated_at ? new Date(data.last_updated_at).toLocaleString() : 'Unknown'}
            </span>
          </div>
        </div>

        <div className="trust-score-panel">
          <div className="trust-score-value">{data.trust_score}</div>
          <div className="trust-score-label">Trust Score / 100</div>
          <Badge tone={data.trust_score >= 85 ? 'ok' : data.trust_score >= 65 ? 'warn' : 'error'}>
            {data.trust_status}
          </Badge>
        </div>
      </section>

      <Card title="Trust Score Breakdown" className="trust-section">
        <div className="trust-breakdown-grid">
          {data.dimensions.map((dimension) => (
            <details key={dimension.key} className="trust-dimension">
              <summary>
                <span>{dimension.label}</span>
                <strong>{dimension.score}</strong>
                <Badge tone={trustToneFromStatus(dimension.status)}>{dimension.status.replace('_', ' ')}</Badge>
              </summary>
              <p className="small faint" style={{ marginTop: 8 }}>{dimension.reason}</p>
              {dimension.evidence.length > 0 && (
                <ul className="small trust-evidence-list">
                  {dimension.evidence.map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              )}
            </details>
          ))}
        </div>
      </Card>

      <Card title="Reliability and Quality" className="trust-section">
        <div className="trust-kpi-grid">
          <div className="trust-kpi">
            <span className="trust-kpi-label"><Clock3 size={14} /> Freshness</span>
            <strong>{data.reliability.freshness_status}</strong>
            <span className="faint small">
              {data.reliability.freshness_age_hours != null
                ? `Updated ${Math.round(data.reliability.freshness_age_hours)}h ago`
                : 'Update time not available'}
            </span>
          </div>

          <div className="trust-kpi">
            <span className="trust-kpi-label"><CheckCircle2 size={14} /> Quality</span>
            <strong>{data.reliability.quality_score} / 100</strong>
            <span className="faint small">{data.reliability.quality_warning_count} active warning(s)</span>
          </div>

          <div className="trust-kpi">
            <span className="trust-kpi-label">Completeness</span>
            <strong>{renderMaybePercent(data.reliability.completeness)}</strong>
          </div>

          <div className="trust-kpi">
            <span className="trust-kpi-label">Validity</span>
            <strong>{renderMaybePercent(data.reliability.validity)}</strong>
          </div>

          <div className="trust-kpi">
            <span className="trust-kpi-label">Null-rate</span>
            <strong>{renderMaybePercent(data.reliability.null_rate)}</strong>
          </div>

          <div className="trust-kpi">
            <span className="trust-kpi-label">Anomaly count</span>
            <strong>{data.reliability.anomaly_count ?? 'N/A'}</strong>
          </div>
        </div>

        <div className="trust-actions-row">
          <Link to={`/assets?urn=${encodeURIComponent(data.entity_urn)}`} className="button">View Quality Details</Link>
        </div>
      </Card>

      <Card title="Lineage and Dependency Risk" className="trust-section">
        <div className="trust-kpi-grid">
          <div className="trust-kpi"><span className="trust-kpi-label">Upstream assets</span><strong>{data.dependency_risk.upstream_asset_count}</strong></div>
          <div className="trust-kpi"><span className="trust-kpi-label">Downstream assets</span><strong>{data.dependency_risk.downstream_asset_count}</strong></div>
          <div className="trust-kpi"><span className="trust-kpi-label">Critical consumers</span><strong>{data.dependency_risk.critical_downstream_consumers}</strong></div>
          <div className="trust-kpi"><span className="trust-kpi-label">Dashboards affected</span><strong>{data.dependency_risk.dashboards_affected}</strong></div>
          <div className="trust-kpi"><span className="trust-kpi-label">Reports affected</span><strong>{data.dependency_risk.reports_affected}</strong></div>
          <div className="trust-kpi">
            <span className="trust-kpi-label">Dependency risk</span>
            <strong>{data.dependency_risk.dependency_risk_level}</strong>
            <span className="faint small">{data.dependency_risk.reason}</span>
          </div>
        </div>
        <div className="trust-actions-row">
          <Link to={`/impact?urn=${encodeURIComponent(data.entity_urn)}`} className="button">View Impact Analysis</Link>
          <Link to={`/lineage?urn=${encodeURIComponent(data.entity_urn)}`} className="button">Open Lineage</Link>
        </div>
      </Card>

      <Card
        title="Sensitive Data Detection"
        className={`trust-section ${focusSection === 'sensitive' ? 'trust-section-focus' : ''}`}
      >
        {data.sensitive_data.length === 0 ? (
          <p className="faint small">No sensitive classifications detected for this asset and its columns.</p>
        ) : (
          <>
            <table className="table table-fixed governance-table">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Classification</th>
                  <th>Confidence</th>
                  <th>Detection source</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.sensitive_data.map((row) => (
                  <tr key={row.assignment_id}>
                    <td className="mono">{row.column_name || row.qualified_name}</td>
                    <td>{row.classification}</td>
                    <td>{row.confidence == null ? 'Evidence only' : `${Math.round(row.confidence * 100)}%`}</td>
                    <td>{row.detection_source || 'unknown'}</td>
                    <td>
                      <Badge tone={row.review_status === 'CONFIRMED' ? 'ok' : 'warn'}>
                        {row.review_status === 'CONFIRMED' ? 'Confirmed' : 'Pending Review'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="faint small" style={{ marginBottom: 0 }}>
              {sensitivePending} sensitive field(s) currently need review.
            </p>
          </>
        )}
        <div className="trust-actions-row">
          <Link to="/governance" className="button">Review in Governance</Link>
        </div>
      </Card>

      <Card title="Ownership" className="trust-section">
        <div className="trust-kpi-grid">
          <div className="trust-kpi"><span className="trust-kpi-label">Owner</span><strong>{data.ownership.owner || 'Unassigned'}</strong></div>
          <div className="trust-kpi"><span className="trust-kpi-label">Steward</span><strong>{data.ownership.steward || 'Unassigned'}</strong></div>
          <div className="trust-kpi"><span className="trust-kpi-label">Team</span><strong>{data.ownership.team || 'Unknown'}</strong></div>
          <div className="trust-kpi">
            <span className="trust-kpi-label">Status</span>
            <strong>{data.ownership.status === 'ASSIGNED' ? 'Assigned' : 'Unowned Asset'}</strong>
            {data.ownership.warning && <span className="faint small">{data.ownership.warning}</span>}
          </div>
        </div>
        <div className="trust-actions-row">
          <Link to="/governance" className="button">Manage Ownership</Link>
        </div>
      </Card>

      <Card title="Needs Attention" className="trust-section">
        {data.issues.length === 0 ? (
          <p className="faint small">No active trust issues.</p>
        ) : (
          <ul className="trust-issues-list">
            {data.issues.map((issue) => (
              <li key={issue.code}>
                <Link to={issue.target_url} className="trust-issue-link">
                  <span className="trust-issue-icon">
                    {issue.severity === 'CRITICAL' ? <ShieldAlert size={14} /> : <AlertTriangle size={14} />}
                  </span>
                  <span>
                    <strong>{issue.title}</strong>
                    <span className="faint small"> {issue.detail}</span>
                  </span>
                  <ArrowRight size={14} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={`Why is my Trust Score ${data.trust_score}?`} className="trust-section">
        <div className="grid grid-2">
          <div>
            <h4 className="small" style={{ marginTop: 0 }}>Score is higher because</h4>
            <ul style={{ marginTop: 0, paddingLeft: 18 }}>
              {data.explanation.positives.map((item) => (
                <li key={item} className="small">{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="small" style={{ marginTop: 0 }}>Score is reduced because</h4>
            <ul style={{ marginTop: 0, paddingLeft: 18 }}>
              {data.explanation.negatives.map((item) => (
                <li key={item} className="small">{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
}
