import { Link } from 'react-router-dom';
import type { ColumnSummary } from '@/types';
import { Badge } from '@/components/common/Badge';

/**
 * Column-level technical metadata.
 * Classifications are shown inline because sensitivity is a column-level concern.
 */
export function ColumnTable({ columns }: { columns: ColumnSummary[] }) {
  if (columns.length === 0) {
    return <div className="state">No columns have been ingested for this asset.</div>;
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>#</th>
          <th>Column</th>
          <th>Type</th>
          <th>Nullable</th>
          <th>Description</th>
          <th>Classification</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {columns.map((column) => (
          <tr key={column.urn}>
            <td className="faint">{column.ordinal_position ?? '-'}</td>
            <td className="mono">
              {column.name}
              {column.is_primary_key && (
                <Badge tone="accent" title="Primary key">
                  PK
                </Badge>
              )}
            </td>
            <td className="nowrap muted">{column.data_type ?? '-'}</td>
            <td className="nowrap muted">{column.is_nullable === null ? '-' : column.is_nullable ? 'yes' : 'no'}</td>
            <td className="muted">{column.description ?? <span className="faint">-</span>}</td>
            <td>
              <div className="row">
                {column.classifications.map((name) => (
                  <Badge key={name} tone={name.startsWith('PII') || name.startsWith('PCI') ? 'warn' : 'default'}>
                    {name}
                  </Badge>
                ))}
              </div>
            </td>
            <td className="nowrap">
              <Link className="small" to={`/lineage?urn=${encodeURIComponent(column.urn)}`}>
                Lineage
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
