import { api, encodeUrn } from './api';
import type {
  CatalogSummary,
  ConnectorDescriptor,
  EntityType,
  MetadataEntity,
  MetadataEntityDetail,
  Page,
  SearchResponse,
} from '@/types';

export interface MetadataListParams {
  entity_type?: EntityType;
  platform?: string;
  parent_urn?: string;
  search?: string;
  tag?: string;
  limit?: number;
  offset?: number;
}

export const metadataApi = {
  list: (params: MetadataListParams = {}) =>
    api.get<Page<MetadataEntity>>('/metadata', { ...params }),

  get: (urn: string) => api.get<MetadataEntityDetail>(`/metadata/${encodeUrn(urn)}`),

  columns: (urn: string) => api.get<MetadataEntity[]>(`/metadata/${encodeUrn(urn)}/columns`),

  summary: () => api.get<CatalogSummary>('/metadata/summary'),

  update: (urn: string, changes: Partial<Pick<MetadataEntity, 'description' | 'tags'>>) =>
    api.patch<MetadataEntity>(`/metadata/${encodeUrn(urn)}`, changes),

  ingest: (connector: string, dataSourceName?: string) =>
    api.post<{ run_id: string; entities_created: number; lineage_edges_created: number }>(
      '/metadata/ingest',
      { connector, data_source_name: dataSourceName, extract_lineage: true },
    ),

  search: (q: string, mode: 'keyword' | 'semantic' | 'hybrid' = 'hybrid', limit = 20) =>
    api.get<SearchResponse>('/search', { q, mode, limit }),

  connectors: () => api.get<ConnectorDescriptor[]>('/connectors'),
};
