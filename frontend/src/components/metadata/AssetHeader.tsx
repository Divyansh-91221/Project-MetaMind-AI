import { Link } from 'react-router-dom';
import type { MetadataEntityDetail } from '@/types';
import { Badge } from '@/components/common/Badge';
import { ENTITY_ICONS, formatNumber } from '@/utils/format';

/** Title block for the asset details page: identity, ownership and quick actions. */
export function AssetHeader({ asset }: { asset: MetadataEntityDetail }) {
  const encoded = encodeURIComponent(asset.urn);

  return (
    <div className="page-header">
      <div>
        <h1>
          <span aria-hidden style={{ marginRight: 8 }}>{ENTITY_ICONS[asset.entity_type]}</span>
          {asset.display_name || asset.qualified_name}
        </h1>
        <div className="mono faint small">{asset.urn}</div>

        <p>{asset.description ?? 'No description has been curated for this asset yet.'}</p>

        <div className="row">
          <Badge tone="accent">{asset.entity_type}</Badge>
          <Badge>{asset.platform}</Badge>
          {asset.row_count ? <Badge>{formatNumber(asset.row_count)} rows</Badge> : null}
          {asset.is_deprecated && <Badge tone="error">Deprecated</Badge>}
          {asset.classifications.some((c) => c.sensitivity === 'PII') && <Badge tone="warn">PII</Badge>}
          <Badge>{asset.upstream_count} upstream</Badge>
          <Badge>{asset.downstream_count} downstream</Badge>
          {asset.tags.map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </div>
      </div>

      <div className="row">
        <Link className="button" to={`/lineage?urn=${encoded}`}>
          Lineage
        </Link>
        <Link className="button" to={`/impact?urn=${encoded}`}>
          Impact
        </Link>
        <Link className="button primary" to={`/copilot?urn=${encoded}`}>
          Ask Copilot
        </Link>
      </div>
    </div>
  );
}
