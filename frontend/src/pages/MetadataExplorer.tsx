import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Compass, Filter, Layers3, RefreshCw, Search, TableProperties } from 'lucide-react';
import { useApi, useDebounce } from '@/hooks';
import { metadataApi } from '@/services/metadataApi';
import { AsyncBoundary, Card, PageHeader } from '@/components/common';
import { Badge } from '@/components/common/Badge';
import { AssetList } from '@/components/metadata';
import type { EntityType } from '@/types';

const ENTITY_TYPES: EntityType[] = [
  'TABLE',
  'VIEW',
  'COLUMN',
  'DATASET',
  'DASHBOARD',
  'REPORT',
  'KPI',
  'PIPELINE',
  'DATA_SOURCE',
];

const PAGE_SIZE = 25;

/** Browse and filter the catalog. */
export function MetadataExplorer() {
  const location = useLocation();
  const isDiscovery = location.pathname === '/discovery';
  const [entityType, setEntityType] = useState<EntityType | ''>('TABLE');
  const [platform, setPlatform] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const debouncedSearch = useDebounce(search, 300);

  const result = useApi(
    () =>
      metadataApi.list({
        entity_type: entityType || undefined,
        platform: platform || undefined,
        search: debouncedSearch || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    [entityType, platform, debouncedSearch, page],
  );

  const clearFilters = () => {
    setEntityType('');
    setPlatform('');
    setSearch('');
    setPage(0);
  };

  const activeFilters = [
    entityType ? `Type: ${entityType}` : null,
    platform ? `Platform: ${platform}` : null,
    debouncedSearch ? `Query: ${debouncedSearch}` : null,
  ].filter(Boolean) as string[];

  return (
    <div className="catalog-workspace">
      <PageHeader
        title={isDiscovery ? 'Discovery Workspace' : 'Catalog Workspace'}
        description={
          isDiscovery
            ? 'Discover assets, datasets, dashboards and pipelines across enterprise domains with semantic and structural filters.'
            : 'Browse governed metadata assets across the enterprise with platform and entity-level precision.'
        }
        actions={
          <div className="row">
            <Link to="/lineage" className="button">Open Lineage</Link>
            <Link to="/governance" className="button">Open Governance</Link>
          </div>
        }
      />

      {isDiscovery ? (
        <Card title="Discovery lens" className="discovery-lens">
          <div className="row" style={{ justifyContent: 'space-between', gap: 16 }}>
            <span className="faint small">
              Start broad, then narrow results by entity type, platform, or search phrase.
            </span>
            <div className="row">
              <Badge tone="accent">Cross-domain</Badge>
              <Badge tone="accent">Semantic search</Badge>
              <Badge tone="accent">Relationship-ready</Badge>
            </div>
          </div>
        </Card>
      ) : null}

      <Card className="catalog-toolbar">
        <div className="catalog-toolbar-top">
          <div className="catalog-stat">
            <span className="metric-head"><Layers3 size={16} /> Entity Type</span>
            <select
              className="select"
              value={entityType}
              onChange={(event) => {
                setEntityType(event.target.value as EntityType | '');
                setPage(0);
              }}
              aria-label="Entity type"
            >
              <option value="">All types</option>
              {ENTITY_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>

          <div className="catalog-stat">
            <span className="metric-head"><Compass size={16} /> Platform</span>
            <select
              className="select"
              value={platform}
              onChange={(event) => {
                setPlatform(event.target.value);
                setPage(0);
              }}
              aria-label="Platform"
            >
              <option value="">All platforms</option>
              <option value="sap">SAP</option>
              <option value="databricks">Databricks</option>
              <option value="snowflake">Snowflake</option>
              <option value="powerbi">Power BI</option>
              <option value="postgres">PostgreSQL</option>
            </select>
          </div>

          <div className="catalog-search-wrap">
            <span className="metric-head"><Search size={16} /> Search Catalog</span>
            <input
              className="input"
              placeholder="Filter by name or description"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(0);
              }}
              aria-label="Filter assets"
            />
          </div>

          <button className="button" type="button" onClick={clearFilters}>
            <RefreshCw size={14} /> Clear
          </button>
        </div>

        <div className="row" style={{ marginTop: 10 }}>
          <span className="metric-head"><Filter size={14} /> Active filters</span>
          {activeFilters.length === 0 ? (
            <Badge>None</Badge>
          ) : (
            activeFilters.map((item) => <Badge key={item} tone="accent">{item}</Badge>)
          )}
        </div>
      </Card>

      <Card
        title={result.data ? `${result.data.total} asset(s)` : 'Assets'}
        actions={
          result.data && result.data.total > PAGE_SIZE ? (
            <div className="row">
              <button
                type="button"
                className="button"
                disabled={page === 0}
                onClick={() => setPage((value) => Math.max(0, value - 1))}
              >
                Previous
              </button>
              <span className="faint small">
                Page {page + 1} of {Math.ceil(result.data.total / PAGE_SIZE)}
              </span>
              <button
                type="button"
                className="button"
                disabled={(page + 1) * PAGE_SIZE >= result.data.total}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
              </button>
            </div>
          ) : null
        }
      >
        <div className="row" style={{ marginBottom: 10, justifyContent: 'space-between' }}>
          <span className="faint small">
            {isDiscovery
              ? 'Discovery mode favors broad exploration across domains.'
              : 'Catalog mode emphasizes governed metadata inventory visibility.'}
          </span>
          <span className="metric-head"><TableProperties size={14} /> Asset Inventory</span>
        </div>
        <AsyncBoundary {...result} onRetry={result.reload}>
          {(data) => <AssetList items={data.items} />}
        </AsyncBoundary>
      </Card>
    </div>
  );
}
