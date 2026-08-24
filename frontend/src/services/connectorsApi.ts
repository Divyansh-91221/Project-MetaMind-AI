import { api, encodeUrn } from './api';
import type {
  ConnectorDescriptor,
  DataSourceRead,
  DemoResetResult,
  HealthScoreBreakdown,
  IngestionRun,
} from '@/types';

/** Connector registry, registered data sources, ingestion run history and demo reset. */
export const connectorsApi = {
  list: () => api.get<ConnectorDescriptor[]>('/connectors'),

  sources: () => api.get<DataSourceRead[]>('/connectors/sources'),

  runs: (limit = 20) => api.get<IngestionRun[]>('/connectors/runs', { limit }),

  resetDemo: () => api.post<DemoResetResult>('/connectors/demo/reset'),
};

export const healthApi = {
  score: (urn: string) => api.get<HealthScoreBreakdown>(`/metadata/${encodeUrn(urn)}/health`),
};
