import type { GovernanceProfile } from '@/types';
import { Badge } from '@/components/common/Badge';

export function GovernancePanel({ profile }: { profile: GovernanceProfile }) {
  return (
    <div>
      <h3>Ownership</h3>
      {profile.owners.length === 0 ? (
        <div className="banner">
          No accountable owner is assigned. Unowned assets are a governance gap.
        </div>
      ) : (
        <ul style={{ margin: '0 0 16px', paddingLeft: 18 }}>
          {profile.owners.map((item) => (
            <li key={`${item.owner.name}-${item.role}`}>
              <strong>{item.owner.name}</strong>{' '}
              <span className="faint small">{item.role.replace('_', ' ').toLowerCase()}</span>
              {item.owner.email && <span className="faint small"> · {item.owner.email}</span>}
            </li>
          ))}
        </ul>
      )}

      <h3>Classification</h3>
      {profile.classifications.length === 0 ? (
        <p className="faint">No classifications have been applied.</p>
      ) : (
        <div className="row" style={{ marginBottom: 16 }}>
          {profile.classifications.map((item) => (
            <Badge
              key={item.classification.name}
              tone={item.confirmed ? 'warn' : 'default'}
              title={`${item.method} · confidence ${Math.round(item.confidence * 100)}%${
                item.confirmed ? ' · confirmed' : ' · awaiting steward confirmation'
              }`}
            >
              {item.classification.name}
              {!item.confirmed && ' (suggested)'}
            </Badge>
          ))}
        </div>
      )}

      <h3>Applicable policies</h3>
      {profile.applicable_policies.length === 0 ? (
        <p className="faint">No policies currently apply to this asset.</p>
      ) : (
        <ul style={{ margin: '0 0 16px', paddingLeft: 18 }}>
          {profile.applicable_policies.map((policy) => (
            <li key={policy.name}>
              <strong>{policy.name}</strong> <span className="faint small">{policy.policy_type}</span>
              <div className="muted small">{policy.description}</div>
            </li>
          ))}
        </ul>
      )}

      {profile.compliance_notes.length > 0 && (
        <div className="banner">
          {profile.compliance_notes.map((note) => (
            <div key={note}>{note}</div>
          ))}
        </div>
      )}
    </div>
  );
}
