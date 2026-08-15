import { Link } from 'react-router-dom';
import type { BusinessTerm, BusinessTermDetail } from '@/types';
import { Badge } from '@/components/common/Badge';

export function TermCard({
  term,
  onSelect,
  active = false,
}: {
  term: BusinessTerm;
  onSelect?: (term: BusinessTerm) => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      className="card"
      style={{
        textAlign: 'left',
        width: '100%',
        cursor: 'pointer',
        borderColor: active ? 'var(--accent)' : undefined,
      }}
      onClick={() => onSelect?.(term)}
    >
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <strong>{term.name}</strong>
        {term.is_kpi && <Badge tone="accent">KPI</Badge>}
      </div>
      <div className="faint small">{term.domain}</div>
      <p className="muted" style={{ margin: '8px 0 0' }}>
        {term.short_description ?? term.definition}
      </p>
    </button>
  );
}

/** Full term view including the technical assets that implement it. */
export function TermDetail({ term }: { term: BusinessTermDetail }) {
  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2>{term.name}</h2>
        <div className="row">
          {term.is_kpi && <Badge tone="accent">KPI</Badge>}
          <Badge>{term.status}</Badge>
          <Badge>{term.domain}</Badge>
        </div>
      </div>

      <p>{term.definition}</p>

      {term.calculation && (
        <>
          <h3>Calculation</h3>
          <pre className="card mono" style={{ whiteSpace: 'pre-wrap' }}>{term.calculation}</pre>
        </>
      )}

      <div className="row">
        {term.unit && <Badge>Unit: {term.unit}</Badge>}
        {term.steward && <Badge>Steward: {term.steward}</Badge>}
        {term.synonyms.map((synonym) => (
          <Badge key={synonym}>{synonym}</Badge>
        ))}
      </div>

      <h3 style={{ marginTop: 20 }}>Implemented by</h3>
      {term.linked_assets.length === 0 ? (
        <p className="faint">This term is not yet linked to any technical asset.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Asset</th>
              <th>Type</th>
              <th>Platform</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {term.linked_assets.map((asset) => (
              <tr key={asset.urn}>
                <td className="mono">
                  <Link to={`/assets?urn=${encodeURIComponent(asset.urn)}`}>{asset.qualified_name}</Link>
                </td>
                <td>{asset.entity_type}</td>
                <td>{asset.platform}</td>
                <td className="faint small">
                  {asset.method} · {Math.round(asset.confidence * 100)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
