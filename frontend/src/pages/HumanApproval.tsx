import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApi } from '@/hooks';
import { governanceApi } from '@/services/governanceApi';
import { AsyncBoundary, Badge, Card, ConfirmDialog, EmptyState, PageHeader } from '@/components/common';

const SENSITIVITIES = ['PII', 'PCI', 'FINANCIAL', 'PHI'] as const;

function reasonFor(method: string, confidence: number): string {
  const pct = Math.round(confidence * 100);
  if (method === 'CONNECTOR_DECLARED') {
    return `The source system declared this classification during ingestion (${pct}% confidence).`;
  }
  if (method === 'RULE') {
    return `A rule-based classifier matched this field's name or pattern (${pct}% confidence).`;
  }
  return `Suggested by the "${method}" classification method (${pct}% confidence).`;
}

/**
 * AI recommendation -> human decision -> governance action.
 *
 * Reuses the same classification-review API as the Governance page; this page is purely a
 * more deliberate, one-decision-at-a-time presentation of the same queue, suited to a live
 * walkthrough.
 */
export function HumanApproval() {
  const [sensitivity, setSensitivity] = useState<(typeof SENSITIVITIES)[number]>('PCI');
  const [decided, setDecided] = useState<Record<string, 'CONFIRMED' | 'REJECTED'>>({});
  const queue = useApi(() => governanceApi.sensitive(sensitivity, 100), [sensitivity]);

  const decide = async (assignmentId: string, status: 'CONFIRMED' | 'REJECTED') => {
    await governanceApi.reviewClassification(assignmentId, status);
    setDecided((current) => ({ ...current, [assignmentId]: status }));
    queue.reload();
  };

  return (
    <>
      <PageHeader
        title="Human Approval"
        description="AI-suggested classifications wait here until a steward confirms or rejects them. Every decision is written to the audit trail."
        actions={
          <select
            className="select"
            style={{ width: 160 }}
            value={sensitivity}
            onChange={(event) => setSensitivity(event.target.value as (typeof SENSITIVITIES)[number])}
            aria-label="Sensitivity"
          >
            {SENSITIVITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        }
      />

      <AsyncBoundary {...queue} onRetry={queue.reload}>
        {(rows) => {
          const pending = rows.filter((row) => !row.confirmed);
          if (pending.length === 0) {
            return (
              <Card>
                <EmptyState
                  title={`No ${sensitivity} classifications are waiting for review.`}
                  hint="Every suggestion in this category has already been confirmed."
                />
              </Card>
            );
          }
          return (
            <div className="approval-list">
              {pending.map((row) => {
                const justDecided = decided[row.assignment_id];
                return (
                  <Card key={row.assignment_id} className="approval-card">
                    <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <div className="row" style={{ marginBottom: 6 }}>
                          <Badge tone="warn">{row.classification}</Badge>
                          <Badge>{row.level}</Badge>
                          {row.regulation && <Badge tone="accent">{row.regulation}</Badge>}
                        </div>
                        <Link to={`/assets?urn=${encodeURIComponent(row.urn)}`} className="mono">
                          {row.qualified_name}
                        </Link>
                        <div className="faint small" style={{ marginTop: 2 }}>
                          {row.entity_type} on {row.platform}
                        </div>
                        <p className="muted small" style={{ maxWidth: '60ch', marginTop: 8 }}>
                          {reasonFor(row.method, row.confidence)}
                        </p>
                      </div>

                      <div className="row" style={{ flexShrink: 0 }}>
                        {justDecided ? (
                          <Badge tone={justDecided === 'CONFIRMED' ? 'ok' : 'error'}>
                            {justDecided === 'CONFIRMED' ? 'Approved' : 'Rejected'}
                          </Badge>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="button success"
                              onClick={() => void decide(row.assignment_id, 'CONFIRMED')}
                            >
                              Approve
                            </button>
                            <ConfirmDialog
                              title="Reject this classification?"
                              description={
                                <>
                                  This removes <strong>{row.classification}</strong> from{' '}
                                  <span className="mono">{row.qualified_name}</span>. The decision is
                                  recorded in the audit trail.
                                </>
                              }
                              confirmLabel="Reject"
                              onConfirm={() => decide(row.assignment_id, 'REJECTED')}
                              trigger={(open) => (
                                <button type="button" className="button danger" onClick={open}>
                                  Reject
                                </button>
                              )}
                            />
                          </>
                        )}
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          );
        }}
      </AsyncBoundary>
    </>
  );
}
