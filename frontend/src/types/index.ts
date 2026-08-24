/**
 * Shared API types.
 *
 * These mirror the backend Pydantic contracts in `backend/app/schemas`. Keeping them explicit
 * (rather than generating them) is deliberate for the first version: the surface is small and
 * the types double as documentation. Generate from the OpenAPI schema once the API stabilises.
 */

export type EntityType =
  | 'DATA_SOURCE'
  | 'DATABASE'
  | 'SCHEMA'
  | 'TABLE'
  | 'VIEW'
  | 'COLUMN'
  | 'PIPELINE'
  | 'JOB'
  | 'DATASET'
  | 'DASHBOARD'
  | 'REPORT'
  | 'KPI';

export type LineageLevel = 'TABLE' | 'COLUMN' | 'DATASET';

export type LineageMethod =
  | 'SQL_PARSE'
  | 'CONNECTOR_DECLARED'
  | 'OPENLINEAGE'
  | 'PIPELINE_METADATA'
  | 'AI_INFERRED'
  | 'MANUAL';

export type VerificationStatus = 'UNVERIFIED' | 'VERIFIED' | 'REJECTED' | 'NEEDS_REVIEW';

export type Direction = 'UPSTREAM' | 'DOWNSTREAM' | 'BOTH';

export type QualityStatus = 'PASS' | 'WARN' | 'FAIL' | 'UNKNOWN';

export type SearchMode = 'keyword' | 'semantic' | 'hybrid';

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface MetadataEntity {
  id: string;
  urn: string;
  entity_type: EntityType;
  platform: string;
  name: string;
  qualified_name: string;
  display_name?: string | null;
  description?: string | null;
  data_type?: string | null;
  ordinal_position?: number | null;
  is_nullable?: boolean | null;
  is_primary_key?: boolean | null;
  row_count?: number | null;
  tags: string[];
  properties: Record<string, unknown>;
  is_deprecated: boolean;
  created_at: string;
  updated_at: string;
}

export interface ColumnSummary {
  urn: string;
  name: string;
  data_type?: string | null;
  ordinal_position?: number | null;
  is_nullable?: boolean | null;
  is_primary_key?: boolean | null;
  description?: string | null;
  classifications: string[];
}

export interface MetadataEntityDetail extends MetadataEntity {
  parent_urn?: string | null;
  columns: ColumnSummary[];
  owners: Array<{ name: string; role: string; email?: string | null }>;
  classifications: Array<{
    name: string;
    level: string;
    sensitivity: string;
    method: string;
    confirmed: boolean;
  }>;
  business_terms: Array<{ name: string; definition: string; is_kpi: boolean }>;
  quality: Record<string, unknown>;
  upstream_count: number;
  downstream_count: number;
}

export interface LineageNode {
  urn: string;
  name: string;
  qualified_name: string;
  entity_type: EntityType;
  platform: string;
  description?: string | null;
  depth: number;
  properties: Record<string, unknown>;
}

export interface LineageEdge {
  id?: string | null;
  source_urn: string;
  target_urn: string;
  relationship: string;
  transformation?: string | null;
  pipeline_urn?: string | null;
  level: LineageLevel;
  method: LineageMethod;
  confidence: number;
  verified: boolean;
  verification_status: VerificationStatus;
  observed_at?: string | null;
  evidence: Record<string, unknown>;
}

export interface LineageGraph {
  root_urn: string;
  direction: Direction;
  depth: number;
  nodes: LineageNode[];
  edges: LineageEdge[];
  truncated: boolean;
}

export interface ImpactedAsset {
  urn: string;
  name: string;
  qualified_name: string;
  entity_type: EntityType;
  platform: string;
  distance: number;
  path_confidence: number;
  contains_inferred_lineage: boolean;
  owners: string[];
  criticality: 'HIGH' | 'MEDIUM' | 'LOW';
  reason: string;
}

export interface ImpactAnalysisResult {
  root: LineageNode;
  summary: {
    total_impacted: number;
    by_entity_type: Record<string, number>;
    by_platform: Record<string, number>;
    critical_assets: number;
    dashboards_affected: number;
    kpis_affected: number;
    inferred_paths: number;
  };
  impacted_assets: ImpactedAsset[];
  owners_to_notify: Array<{ owner: string; assets: string[] }>;
  blast_radius_depth: number;
  truncated: boolean;
}

export interface SearchHit {
  urn: string;
  name: string;
  qualified_name: string;
  entity_type: EntityType;
  platform: string;
  description?: string | null;
  score: number;
  keyword_score: number;
  semantic_score: number;
  matched_on: string[];
  highlights: string[];
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  total: number;
  hits: SearchHit[];
  took_ms: number;
}

export interface RetrievalDocument {
  chunk_id: string;
  document_title: string;
  document_type: string;
  content: string;
  score: number;
  entity_urn?: string | null;
  source_uri?: string | null;
  metadata: Record<string, unknown>;
}

export interface RetrievalResponse {
  query: string;
  documents: RetrievalDocument[];
  entities: SearchHit[];
}

export interface SearchIndexReport {
  documents_indexed: number;
  chunks_indexed: number;
  skipped_unchanged: number;
}

export interface GovernanceProfile {
  entity_urn: string;
  entity_name: string;
  owners: Array<{ role: string; owner: { id: string; name: string; email?: string | null } }>;
  classifications: Array<{
    classification: { name: string; level: string; sensitivity: string; regulation?: string | null };
    method: string;
    confidence: number;
    confirmed: boolean;
  }>;
  highest_sensitivity: string;
  classification_level: string;
  applicable_policies: Array<{ name: string; policy_type: string; description?: string | null }>;
  contains_pii: boolean;
  unowned: boolean;
  compliance_notes: string[];
}

export interface BusinessTerm {
  id: string;
  name: string;
  domain: string;
  definition: string;
  short_description?: string | null;
  synonyms: string[];
  is_kpi: boolean;
  calculation?: string | null;
  unit?: string | null;
  status: string;
  steward?: string | null;
}

export interface BusinessTermDetail extends BusinessTerm {
  linked_assets: Array<{
    urn: string;
    name: string;
    qualified_name: string;
    entity_type: string;
    platform: string;
    method: string;
    confidence: number;
  }>;
}

export interface QualityProfile {
  entity_urn: string;
  entity_name: string;
  overall_status: QualityStatus;
  freshness?: {
    last_updated_at?: string | null;
    last_successful_run_at?: string | null;
    age_hours?: number | null;
    is_stale: boolean;
    status: QualityStatus;
    expected_interval_hours?: number | null;
    failure_reason?: string | null;
  } | null;
  metrics: Array<{
    dimension: string;
    metric_name: string;
    value?: number | null;
    unit?: string | null;
    status: QualityStatus;
    measured_at: string;
  }>;
  failing_dimensions: string[];
}

export interface EvidenceItem {
  kind:
    | 'entity'
    | 'lineage'
    | 'impact'
    | 'document'
    | 'glossary'
    | 'governance'
    | 'quality'
    | 'constraint';
  title: string;
  detail: string;
  urn?: string | null;
  source: string;
  confidence: number;
  inferred: boolean;
  constraint_type?: string | null;
  constraint_name?: string | null;
  constraint_columns?: string[];
  payload: Record<string, unknown>;
}

export interface ToolCallTrace {
  tool: string;
  arguments: Record<string, unknown>;
  succeeded: boolean;
  result_count: number;
  duration_ms: number;
  error?: string | null;
}

export interface CopilotResponse {
  conversation_id: string;
  answer: string;
  intent: string;
  resolved_entities: Array<{
    urn: string;
    name: string;
    qualified_name: string;
    entity_type: string;
    platform: string;
    score: number;
  }>;
  evidence: EvidenceItem[];
  tool_calls: ToolCallTrace[];
  suggested_followups: string[];
  warnings: string[];
  took_ms: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  evidence?: EvidenceItem[];
  warnings?: string[];
  followups?: string[];
  intent?: string;
  toolCalls?: ToolCallTrace[];
  resolvedEntities?: CopilotResponse['resolved_entities'];
  tookMs?: number;
}

export interface CatalogSummary {
  entities_by_type: Record<string, number>;
  entities_by_platform: Record<string, number>;
  lineage: {
    total_edges: number;
    verified_edges: number;
    by_method: Record<string, number>;
  };
  data_sources: number;
}

export interface ConnectorDescriptor {
  name: string;
  platform: string;
  description: string;
  supports_lineage: boolean;
  supports_column_lineage: boolean;
  supports_quality: boolean;
  implemented: boolean;
  required_config: string[];
}

export interface DataSourceRead {
  id: string;
  name: string;
  connector_type: string;
  platform: string;
  description?: string | null;
  enabled: boolean;
  last_ingested_at?: string | null;
  last_ingestion_status?: string | null;
  created_at: string;
}

export interface IngestionRun {
  run_id: string;
  connector: string;
  status: 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED';
  started_at?: string | null;
  completed_at?: string | null;
  assets_processed?: number | null;
  lineage_edges?: number | null;
  warnings: string[];
}

export interface DemoResetResult {
  success: boolean;
  entities_created: number;
  entities_updated: number;
  lineage_edges_created: number;
  lineage_edges_updated: number;
  graph: string;
  index: string;
}

export interface HealthScoreBreakdown {
  entity_urn: string;
  total: number;
  label: string;
  components: Record<string, number>;
  weights: Record<string, number>;
}

export type TrustStatusTone = 'HEALTHY' | 'WARNING' | 'CRITICAL' | 'PENDING_REVIEW' | 'UNKNOWN';

export interface TrustDimension {
  key: string;
  label: string;
  score: number;
  status: TrustStatusTone;
  reason: string;
  evidence: string[];
}

export interface TrustIssue {
  code: string;
  severity: 'WARNING' | 'CRITICAL';
  title: string;
  detail: string;
  target_page: 'quality' | 'impact' | 'governance' | 'lineage' | 'asset';
  target_url: string;
}

export interface SensitiveFieldDetection {
  assignment_id: string;
  entity_urn: string;
  qualified_name: string;
  column_name?: string | null;
  classification: string;
  confidence?: number | null;
  detection_source?: string | null;
  review_status: 'CONFIRMED' | 'PENDING_REVIEW';
  evidence: Record<string, unknown>;
}

export interface AssetTrustSummary {
  fallback_mode?: boolean;
  data_source?: 'trust_api' | 'fallback';
  entity_urn: string;
  asset_name: string;
  platform: string;
  asset_type: string;
  description?: string | null;
  owner?: string | null;
  last_updated_at?: string | null;
  trust_score: number;
  trust_status: string;
  dimensions: TrustDimension[];
  reliability: {
    freshness_status: string;
    freshness_last_updated_at?: string | null;
    freshness_age_hours?: number | null;
    freshness_expected_interval_hours?: number | null;
    is_stale: boolean;
    freshness_failure_reason?: string | null;
    quality_score: number;
    quality_warning_count: number;
    completeness?: number | null;
    validity?: number | null;
    null_rate?: number | null;
    anomaly_count?: number | null;
  };
  dependency_risk: {
    upstream_asset_count: number;
    downstream_asset_count: number;
    critical_downstream_consumers: number;
    dashboards_affected: number;
    reports_affected: number;
    dependency_risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    reason: string;
    unverified_dependency_count: number;
    inferred_path_count: number;
  };
  sensitive_data: SensitiveFieldDetection[];
  ownership: {
    owner?: string | null;
    steward?: string | null;
    status: 'ASSIGNED' | 'UNOWNED';
    team?: string | null;
    warning?: string | null;
  };
  issues: TrustIssue[];
  explanation: {
    positives: string[];
    negatives: string[];
  };
}

