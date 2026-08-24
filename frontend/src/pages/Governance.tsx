import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ShieldCheck, UserX, Workflow } from 'lucide-react';
import { useApi } from '@/hooks';
import { governanceApi } from '@/services/governanceApi';
import { lineageApi } from '@/services/lineageApi';
import { AsyncBoundary, Card, PageHeader } from '@/components/common';
import { Badge } from '@/components/common/Badge';

const SENSITIVITIES = ['PII', 'PCI', 'FINANCIAL', 'PHI'];

/**
 * Stewardship workspace: sensitive data inventory, ownership gaps and the lineage
 * verification queue.
 */
export function Governance() {
  const [sensitivity, setSensitivity] = useState('PII');
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const sensitive = useApi(() => governanceApi.sensitive(sensitivity, 100), [sensitivity]);
  const unowned = useApi(() => governanceApi.unowned(50), []);
  const review = useApi(() => lineageApi.reviewQueue(25), []);

  const sensitivityCount = sensitive.data?.length ?? 0;
  const unownedCount = unowned.data?.length ?? 0;
  const reviewCount = review.data?.length ?? 0;
  const confirmedCount = (sensitive.data ?? []).filter((row) => row.confirmed).length;

  const verify = async (edgeId: string, status: 'VERIFIED' | 'REJECTED') => {
    await lineageApi.verify(edgeId, status);
    review.reload();
  };

  const reviewClassification = async (assignmentId: string, status: 'CONFIRMED' | 'REJECTED') => {
    setReviewingId(assignmentId);
    try {
      await governanceApi.reviewClassification(assignmentId, status);
      sensitive.reload();
    } finally {
      setReviewingId(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Governance"
        description="Sensitivity classification, ownership accountability and human verification of inferred lineage."
      />

      <div className="governance-metrics-grid">
        <div className="metric-panel">
          <span className="metric-head"><ShieldCheck size={15} /> Sensitive Assets</span>
          <strong>{sensitivityCount}</strong>
          <span className="faint small">Current inventory for selected sensitivity level</span>
        </div>
        <div className="metric-panel">
          <span className="metric-head"><Workflow size={15} /> Review Queue</span>
          <strong>{reviewCount}</strong>
          <span className="faint small">Lineage edges waiting for verification</span>
        </div>
        <div className="metric-panel">
          <span className="metric-head"><UserX size={15} /> Unowned Assets</span>
          <strong>{unownedCount}</strong>
          <span className="faint small">Assets without accountable steward</span>
        </div>
        <div className="metric-panel">
          <span className="metric-head"><AlertTriangle size={15} /> Confirmed Labels</span>
          <strong>{confirmedCount}</strong>
          <span className="faint small">Classifications approved by data stewards</span>
        </div>
      </div>

      <Card
        title="Sensitive data inventory"
        className="governance-section-card"
        actions={
          <select
            className="select"
            style={{ width: 150 }}
            value={sensitivity}
            onChange={(event) => setSensitivity(event.target.value)}
            aria-label="Sensitivity"
          >
            {SENSITIVITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        }
      >
        <AsyncBoundary {...sensitive} onRetry={sensitive.reload}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="faint">No assets are classified as {sensitivity}.</p>
            ) : (
              <div className="table-wrap">
                <table className="table table-fixed governance-table">
                  <colgroup>
                    <col className="col-asset" />
                    <col className="col-type" />
                    <col className="col-platform" />
                    <col className="col-classification" />
                    <col className="col-level" />
                    <col className="col-status" />
                    <col className="col-regulation" />
                    <col className="col-actions" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Type</th>
                      <th>Platform</th>
                      <th>Classification</th>
                      <th>Level</th>
                      <th className="status-col-header">Status</th>
                      <th className="regulation-col-header">Regulation</th>
                      <th className="actions-col-header">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.assignment_id}>
                        <td className="mono asset-cell">
                          <Link to={`/assets?urn=${encodeURIComponent(row.urn)}`}>
                            <span className="asset-text" title={row.qualified_name}>
                              {row.qualified_name}
                            </span>
                          </Link>
                        </td>
                        <td>{row.entity_type}</td>
                        <td>{row.platform}</td>
                        <td className="classification-cell">
                          <Badge tone="warn">{row.classification}</Badge>
                        </td>
                        <td className="level-cell">{row.level}</td>
                        <td className="status-cell">
                          <Badge tone={row.confirmed ? 'default' : 'warn'}>
                            {row.confirmed ? 'Confirmed' : 'Awaiting review'}
                          </Badge>
                        </td>
                        <td className="faint regulation-cell">{row.regulation ?? '-'}</td>
                        <td className="governance-actions-cell">
                          <div className="governance-actions">
                            <button
                              type="button"
                              className="button success"
                              disabled={reviewingId === row.assignment_id}
                              onClick={() => reviewClassification(row.assignment_id, 'CONFIRMED')}
                            >
                              Confirm
                            </button>
                            <button
                              type="button"
                              className="button danger"
                              disabled={reviewingId === row.assignment_id}
                              onClick={() => reviewClassification(row.assignment_id, 'REJECTED')}
                            >
                              Reject
                            </button>
                          </div>
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

      <Card title="Lineage verification queue">
        <p className="muted small">
          AI-inferred and low-confidence relationships are never treated as fact until a steward
          confirms them. Decisions are written to the audit trail.
        </p>
        <AsyncBoundary {...review} onRetry={review.reload}>
          {(edges) =>
            edges.length === 0 ? (
              <p className="faint">Nothing is waiting for verification.</p>
            ) : (
              <div className="table-wrap">
                <table className="table table-fixed lineage-review-table">
                  <thead>
                    <tr>
                      <th>Relationship</th>
                      <th>Method</th>
                      <th>Confidence</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {edges.map((edge) => (
                      <tr key={edge.id ?? `${edge.source_urn}-${edge.target_urn}`}>
                        <td className="mono small asset-cell">
                          {edge.source_urn.split(':').slice(4).join(':')}
                          {' \u2192 '}
                          {edge.target_urn.split(':').slice(4).join(':')}
                        </td>
                        <td>
                          <Badge tone={edge.method === 'AI_INFERRED' ? 'inferred' : 'default'}>
                            {edge.method}
                          </Badge>
                        </td>
                        <td>{Math.round(edge.confidence * 100)}%</td>
                        <td className="governance-actions-cell">
                          <div className="governance-actions">
                            <button
                              type="button"
                              className="button success"
                              disabled={!edge.id}
                              onClick={() => edge.id && verify(edge.id, 'VERIFIED')}
                            >
                              Confirm
                            </button>
                            <button
                              type="button"
                              className="button danger"
                              disabled={!edge.id}
                              onClick={() => edge.id && verify(edge.id, 'REJECTED')}
                            >
                              Reject
                            </button>
                          </div>
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

      <Card title="Assets without an owner">
        <AsyncBoundary {...unowned} onRetry={unowned.reload}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="faint">Every catalogued asset has an accountable owner.</p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {rows.map((row) => (
                  <li key={row.urn}>
                    <Link to={`/assets?urn=${encodeURIComponent(row.urn)}`} className="mono">
                      {row.qualified_name}
                    </Link>
                    <span className="faint small"> · {row.entity_type}</span>
                  </li>
                ))}
              </ul>
            )
          }
        </AsyncBoundary>
      </Card>
    </>
  );
}
