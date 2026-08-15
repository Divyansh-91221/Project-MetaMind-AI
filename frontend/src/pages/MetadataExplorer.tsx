import { useState } from 'react';
import { useApi, useDebounce } from '@/hooks';
import { metadataApi } from '@/services/metadataApi';
import { AsyncBoundary, Card, PageHeader } from '@/components/common';
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

  return (
    <>
      <PageHeader
        title="Metadata Explorer"
        description="Every catalogued asset across the enterprise landscape, with its technical metadata and business context."
      />

      <Card>
        <div className="row">
          <input
            className="input"
            style={{ flex: 2, minWidth: 220 }}
            placeholder="Filter by name or description"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
            aria-label="Filter assets"
          />
          <select
            className="select"
            style={{ width: 170 }}
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
          <select
            className="select"
            style={{ width: 160 }}
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
        <AsyncBoundary {...result} onRetry={result.reload}>
          {(data) => <AssetList items={data.items} />}
        </AsyncBoundary>
      </Card>
    </>
  );
}
