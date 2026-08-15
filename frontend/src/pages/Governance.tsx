import { useState } from 'react';
import { Link } from 'react-router-dom';
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
  const sensitive = useApi(() => governanceApi.sensitive(sensitivity, 100), [sensitivity]);
  const unowned = useApi(() => governanceApi.unowned(50), []);
  const review = useApi(() => lineageApi.reviewQueue(25), []);

  const verify = async (edgeId: string, status: 'VERIFIED' | 'REJECTED') => {
    await lineageApi.verify(edgeId, status);
    review.reload();
  };

  return (
    <>
      <PageHeader
        title="Governance"
        description="Sensitivity classification, ownership accountability and human verification of inferred lineage."
      />

      <Card
        title="Sensitive data inventory"
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
              <table className="table">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Type</th>
                    <th>Platform</th>
                    <th>Classification</th>
                    <th>Level</th>
                    <th>Regulation</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={`${row.urn}-${row.classification}`}>
                      <td className="mono">
                        <Link to={`/assets?urn=${encodeURIComponent(row.urn)}`}>{row.qualified_name}</Link>
                      </td>
                      <td>{row.entity_type}</td>
                      <td>{row.platform}</td>
                      <td>
                        <Badge tone="warn">{row.classification}</Badge>
                      </td>
                      <td>{row.level}</td>
                      <td className="faint">{row.regulation ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
              <table className="table">
                <thead>
                  <tr>
                    <th>Relationship</th>
                    <th>Method</th>
                    <th>Confidence</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {edges.map((edge) => (
                    <tr key={edge.id ?? `${edge.source_urn}-${edge.target_urn}`}>
                      <td className="mono small">
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
                      <td className="row nowrap">
                        <button
                          type="button"
                          className="button"
                          disabled={!edge.id}
                          onClick={() => edge.id && verify(edge.id, 'VERIFIED')}
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          className="button"
                          disabled={!edge.id}
                          onClick={() => edge.id && verify(edge.id, 'REJECTED')}
                        >
                          Reject
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
