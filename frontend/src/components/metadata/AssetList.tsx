import { Link } from 'react-router-dom';
import type { MetadataEntity } from '@/types';
import { Badge } from '@/components/common/Badge';
import { ENTITY_ICONS, formatNumber, truncate } from '@/utils/format';

/** Tabular list of catalog assets. */
export function AssetList({ items }: { items: MetadataEntity[] }) {
  if (items.length === 0) {
    return <div className="state">No assets match these filters.</div>;
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Asset</th>
          <th>Type</th>
          <th>Platform</th>
          <th>Description</th>
          <th className="nowrap">Rows</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.urn}>
            <td>
              <Link to={`/assets?urn=${encodeURIComponent(item.urn)}`} className="mono">
                <span aria-hidden style={{ marginRight: 6 }}>{ENTITY_ICONS[item.entity_type]}</span>
                {item.qualified_name}
              </Link>
              {item.tags.length > 0 && (
                <div className="row" style={{ marginTop: 4 }}>
                  {item.tags.slice(0, 3).map((tag) => (
                    <Badge key={tag}>{tag}</Badge>
                  ))}
                </div>
              )}
            </td>
            <td className="nowrap">{item.entity_type}</td>
            <td className="nowrap">{item.platform}</td>
            <td className="muted">
              {item.description ? truncate(item.description, 120) : <span className="faint">No description</span>}
            </td>
            <td className="nowrap">{formatNumber(item.row_count)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
