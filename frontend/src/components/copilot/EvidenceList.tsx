import { Link } from 'react-router-dom';
import type { EvidenceItem, ToolCallTrace } from '@/types';
import { Badge, ConfidenceBadge } from '@/components/common/Badge';

/**
 * Evidence panel.
 *
 * Every Copilot claim maps to an evidence item here, so an answer can be audited rather than
 * taken on trust. Inferred evidence is visually separated.
 */
export function EvidenceList({
  evidence,
  toolCalls,
}: {
  evidence: EvidenceItem[];
  toolCalls: ToolCallTrace[];
}) {
  if (evidence.length === 0) {
    return <p className="faint small">Ask a question to see the evidence behind the answer.</p>;
  }

  return (
    <div>
      {toolCalls.length > 0 && (
        <div className="row small" style={{ marginBottom: 10 }}>
          {toolCalls.map((call) => (
            <Badge key={`${call.tool}-${call.duration_ms}`} tone={call.succeeded ? 'default' : 'error'}>
              {call.tool} · {call.result_count} · {call.duration_ms.toFixed(0)}ms
            </Badge>
          ))}
        </div>
      )}

      {evidence.map((item, index) => (
        <div className="evidence-item" key={`${item.title}-${index}`}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span className="evidence-title">
              [{index + 1}] {item.title}
            </span>
            <ConfidenceBadge confidence={item.confidence} inferred={item.inferred} />
          </div>
          <div className="evidence-detail">{item.detail}</div>
          <div className="evidence-source">
            {item.kind} · {item.source}
            {item.urn && (
              <>
                {' · '}
                <Link to={`/assets?urn=${encodeURIComponent(item.urn)}`}>open asset</Link>
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
