import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { UploadCloud, FileText, Sparkles, Download, ExternalLink, X, RotateCcw, Copy } from 'lucide-react';
import { Badge, Card, ConfidenceBadge, PageHeader, Spinner } from '@/components/common';
import {
  enrichmentApi,
  type EnrichmentIssue,
  type EnrichmentMapping,
  type EnrichmentRun,
} from '@/services/enrichmentApi';

// Survives tab switches within the SPA: the run itself lives in Postgres, this just
// remembers which run to reload since the page component unmounts on navigation.
const ACTIVE_RUN_STORAGE_KEY = 'metamind.enrichment.activeRunId';

const STAGE_ORDER = [
  'UPLOADED',
  'INGESTING',
  'UNDERSTANDING',
  'MAPPING',
  'ENRICHING',
  'VALIDATING',
  'REVIEW',
  'INTEGRATED',
] as const;

const STAGE_LABEL: Record<string, string> = {
  UPLOADED: 'Ingest',
  INGESTING: 'Ingest',
  UNDERSTANDING: 'Understand',
  MAPPING: 'Map',
  ENRICHING: 'Enrich',
  VALIDATING: 'Validate',
  REVIEW: 'Review',
  INTEGRATED: 'Integrate',
  FAILED: 'Failed',
};

function statusTone(status: string): 'ok' | 'warn' | 'error' | 'accent' | 'default' {
  switch (status) {
    case 'APPROVED':
    case 'INTEGRATION_READY':
      return 'ok';
    case 'APPROVED_WITH_OPEN_ISSUE':
      return 'warn';
    case 'REJECTED':
      return 'error';
    case 'NEEDS_REVIEW':
      return 'warn';
    default:
      return 'accent';
  }
}

function severityTone(severity: string): 'error' | 'warn' | 'default' {
  if (severity === 'HIGH') return 'error';
  if (severity === 'MEDIUM') return 'warn';
  return 'default';
}

/**
 * Metadata Enrichment ("Upload & Enrich").
 *
 * Connects uploaded structured data + documentation to the existing MetaMind catalog,
 * glossary, governance and Copilot layers. This page only orchestrates the enrichment draft
 * workflow (upload -> map -> validate -> review -> integrate) - once integrated, an asset is
 * an ordinary catalog entity viewable everywhere else in the app.
 */
export function MetadataEnrichment() {
  const [datasetName, setDatasetName] = useState('');
  const [sourceSystem, setSourceSystem] = useState('');
  const [businessDomain, setBusinessDomain] = useState('');
  const [description, setDescription] = useState('');
  const [structuredFiles, setStructuredFiles] = useState<File[]>([]);
  const [documentationFiles, setDocumentationFiles] = useState<File[]>([]);

  const [run, setRun] = useState<EnrichmentRun | null>(null);
  const [mappings, setMappings] = useState<EnrichmentMapping[]>([]);
  const [issues, setIssues] = useState<EnrichmentIssue[]>([]);
  const [documentQuery, setDocumentQuery] = useState('');
  const [documentHits, setDocumentHits] = useState<
    Array<{ document: string; source: string; excerpt: string; confidence: number; chunk_index: number }>
  >([]);
  const [documentSearchActive, setDocumentSearchActive] = useState(false);
  const [copiedHitKey, setCopiedHitKey] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTerm, setEditTerm] = useState('');
  const [editDefinition, setEditDefinition] = useState('');

  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [integrationResult, setIntegrationResult] = useState<{
    integrated_count: number;
    entity_urns: string[];
  } | null>(null);

  const refreshMappingsAndIssues = async (runId: string) => {
    const [nextMappings, nextIssues] = await Promise.all([
      enrichmentApi.mappings(runId),
      enrichmentApi.issues(runId),
    ]);
    setMappings(nextMappings);
    setIssues(nextIssues);
    return nextMappings;
  };

  // Rehydrate the last active run (if any) so navigating away and back doesn't lose it.
  useEffect(() => {
    const storedRunId = localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    if (!storedRunId) {
      setRestoring(false);
      return;
    }
    (async () => {
      try {
        const restoredRun = await enrichmentApi.status(storedRunId);
        setRun(restoredRun);
        const restoredMappings = await refreshMappingsAndIssues(restoredRun.id);
        if (restoredRun.stage === 'INTEGRATED') {
          const entityUrns = restoredMappings
            .map((m) => m.entity_urn)
            .filter((urn): urn is string => Boolean(urn));
          if (entityUrns.length > 0) {
            setIntegrationResult({ integrated_count: entityUrns.length, entity_urns: entityUrns });
          }
        }
      } catch {
        localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
      } finally {
        setRestoring(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (run?.id) {
      localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, run.id);
    }
  }, [run?.id]);

  const resetEnrichment = () => {
    localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    setRun(null);
    setMappings([]);
    setIssues([]);
    setExpandedId(null);
    setEditingId(null);
    setIntegrationResult(null);
    setError(null);
    setDatasetName('');
    setSourceSystem('');
    setBusinessDomain('');
    setDescription('');
    setStructuredFiles([]);
    setDocumentationFiles([]);
  };

  const startEnrichment = async () => {
    if (!datasetName.trim()) {
      setError('Dataset name is required.');
      return;
    }
    if (structuredFiles.length === 0 && documentationFiles.length === 0) {
      setError('Upload at least one structured data file or documentation file.');
      return;
    }
    setBusy(true);
    setError(null);
    setIntegrationResult(null);
    try {
      const uploaded = await enrichmentApi.upload({
        datasetName,
        sourceSystem: sourceSystem || undefined,
        businessDomain: businessDomain || undefined,
        description: description || undefined,
        structuredFiles,
        documentationFiles,
      });
      setRun(uploaded);
      const processed = await enrichmentApi.process(uploaded.id);
      setRun(processed);
      await refreshMappingsAndIssues(processed.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Enrichment failed.');
    } finally {
      setBusy(false);
    }
  };

  const review = async (mappingId: string, action: 'approve' | 'reject' | 'edit') => {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      if (action === 'edit') {
        await enrichmentApi.review(run.id, {
          mapping_id: mappingId,
          action: 'edit',
          edited_term: editTerm || undefined,
          edited_definition: editDefinition || undefined,
        });
        setEditingId(null);
      } else {
        await enrichmentApi.review(run.id, { mapping_id: mappingId, action });
      }
      const updatedRun = await enrichmentApi.status(run.id);
      setRun(updatedRun);
      await refreshMappingsAndIssues(run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review action failed.');
    } finally {
      setBusy(false);
    }
  };

  const integrate = async () => {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      const result = await enrichmentApi.integrate(run.id);
      setIntegrationResult(result);
      const updatedRun = await enrichmentApi.status(run.id);
      setRun(updatedRun);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Integration failed.');
    } finally {
      setBusy(false);
    }
  };

  const resolveIssue = async (issueId: string) => {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      await enrichmentApi.resolveIssue(run.id, issueId);
      await refreshMappingsAndIssues(run.id);
      const updatedRun = await enrichmentApi.status(run.id);
      setRun(updatedRun);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Issue resolution failed.');
    } finally {
      setBusy(false);
    }
  };

  const issuesForMapping = (mappingId: string) => issues.filter((i) => i.mapping_id === mappingId);
  const expandedMapping = mappings.find((m) => m.id === expandedId) ?? null;
  const searchSuggestions = Array.from(
    new Set(
      mappings.flatMap((mapping) => [
        `${mapping.dataset_name}.${mapping.column_name}`,
        mapping.column_name,
        mapping.business_term ?? '',
        mapping.document_title ?? '',
      ]),
    ),
  )
    .filter(Boolean)
    .slice(0, 30);

  const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  const highlightMatch = (text: string, query: string) => {
    if (!query.trim()) return text;
    const pattern = new RegExp(`(${escapeRegExp(query.trim())})`, 'ig');
    return text.split(pattern).map((part, index) =>
      part && pattern.test(part) ? (
        <mark
          key={`${part}-${index}`}
          style={{
            background: 'rgba(96, 165, 250, 0.28)',
            color: '#f8fafc',
            borderRadius: 4,
            padding: '0 3px',
            boxShadow: 'inset 0 0 0 1px rgba(96, 165, 250, 0.45)',
          }}
        >
          {part}
        </mark>
      ) : (
        <span key={`${part}-${index}`}>{part}</span>
      ),
    );
  };

  const copyExcerpt = async (hit: { excerpt: string; document: string; source: string; chunk_index: number }) => {
    const key = `${hit.document}:${hit.source}:${hit.chunk_index}`;
    try {
      await navigator.clipboard.writeText(hit.excerpt);
      setCopiedHitKey(key);
      window.setTimeout(() => setCopiedHitKey((current) => (current === key ? null : current)), 1200);
    } catch {
      setCopiedHitKey(null);
    }
  };

  useEffect(() => {
    if (!run || !documentQuery.trim()) {
      setDocumentHits([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const hits = await enrichmentApi.searchDocuments(run.id, documentQuery.trim(), 5);
          setDocumentHits(hits);
        } catch {
          setDocumentHits([]);
        }
      })();
    }, 250);

    return () => window.clearTimeout(timer);
  }, [run?.id, documentQuery]);

  return (
    <>
      <PageHeader
        title="Metadata Enrichment"
        description="Connect enterprise data with the knowledge that explains it."
        actions={
          run && (
            <button type="button" className="button ghost" disabled={busy} onClick={resetEnrichment}>
              <RotateCcw size={14} /> Reset / Start New Upload
            </button>
          )
        }
      />

      {restoring && <Spinner label="Restoring your last enrichment run..." />}

      <Card title="1. Upload" className="dashboard-section-card">
        <div className="row" style={{ gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 260px' }}>
            <label className="small faint">Dataset Name *</label>
            <input
              className="input"
              value={datasetName}
              onChange={(e) => setDatasetName(e.target.value)}
              placeholder="customer_360"
              disabled={busy}
            />
          </div>
          <div style={{ flex: '1 1 200px' }}>
            <label className="small faint">Source System</label>
            <input
              className="input"
              value={sourceSystem}
              onChange={(e) => setSourceSystem(e.target.value)}
              placeholder="crm"
              disabled={busy}
            />
          </div>
          <div style={{ flex: '1 1 200px' }}>
            <label className="small faint">Business Domain</label>
            <input
              className="input"
              value={businessDomain}
              onChange={(e) => setBusinessDomain(e.target.value)}
              placeholder="sales"
              disabled={busy}
            />
          </div>
          <div style={{ flex: '1 1 100%' }}>
            <label className="small faint">Description</label>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is this dataset?"
              disabled={busy}
            />
          </div>
        </div>

        <div className="row" style={{ gap: 16, marginTop: 16, flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 260px' }}>
            <div style={{ marginBottom: 6, fontWeight: 700, color: '#ffffff' }}>
              <UploadCloud size={14} /> Enterprise Metadata Workbook (CSV / XLSX / PDF / DOCX / TXT)
            </div>
            <input
              type="file"
              accept=".csv,.xlsx,.xlsm,.pdf,.docx,.txt"
              multiple
              disabled={busy}
              onChange={(e) => setStructuredFiles(Array.from(e.target.files ?? []))}
            />
            {structuredFiles.map((f) => (
              <div key={f.name} className="faint small">
                {f.name}
              </div>
            ))}
          </div>
          <div style={{ flex: '1 1 260px' }}>
            <div style={{ marginBottom: 6, fontWeight: 700, color: '#ffffff' }}>
              <FileText size={14} /> Documentation (PDF / DOCX / TXT / MD)
            </div>
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md,.markdown"
              multiple
              disabled={busy}
              onChange={(e) => setDocumentationFiles(Array.from(e.target.files ?? []))}
            />
            {documentationFiles.map((f) => (
              <div key={f.name} className="faint small">
                {f.name}
              </div>
            ))}
          </div>
        </div>

        {error && (
          <p className="error" role="alert" style={{ marginTop: 12 }}>
            {error}
          </p>
        )}

        <button
          type="button"
          className="button"
          style={{ marginTop: 16 }}
          disabled={busy}
          onClick={() => void startEnrichment()}
        >
          <Sparkles size={14} /> {busy ? 'Working...' : 'Start AI Enrichment'}
        </button>
      </Card>

      {run && (
        <Card title="2. Processing" className="dashboard-section-card enrichment-section">
          <ol className="stepper">
            {STAGE_ORDER.map((stage, index) => {
              const currentIndex = STAGE_ORDER.indexOf(run.stage as (typeof STAGE_ORDER)[number]);
              const state = index < currentIndex ? 'done' : index === currentIndex ? 'active' : 'pending';
              return (
                <li key={stage} className={`stepper-item ${state}`}>
                  <span className="stepper-marker" aria-hidden>
                    {state === 'pending' ? index + 1 : '\u2713'}
                  </span>
                  <div className="stepper-label">{STAGE_LABEL[stage]}</div>
                </li>
              );
            })}
          </ol>
          <div className="row" style={{ gap: 24, marginTop: 12 }}>
            <span className="small faint">Mappings: {run.mapping_count}</span>
            <span className="small faint">Issues: {run.issue_count}</span>
            <span className="small faint">Open: {run.open_issue_count}</span>
          </div>
        </Card>
      )}

      {run && (
        <Card title="3. Search Uploaded Documentation & Columns" className="dashboard-section-card enrichment-section">
          <div className="row" style={{ gap: 12, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              className="input"
              list="enrichment-search-suggestions"
              value={documentQuery}
              onChange={(e) => {
                setDocumentQuery(e.target.value);
                setDocumentSearchActive(Boolean(e.target.value.trim()));
              }}
              placeholder="Search docs, columns, values, or mapped terms"
              style={{ flex: '1 1 280px' }}
            />
            <datalist id="enrichment-search-suggestions">
              {searchSuggestions.map((suggestion) => (
                <option key={suggestion} value={suggestion} />
              ))}
            </datalist>
            <button
              type="button"
              className="button ghost small"
              onClick={() => setDocumentSearchActive((prev) => !prev)}
            >
              {documentSearchActive ? 'Hide results' : 'Search run evidence'}
            </button>
          </div>

          {(documentSearchActive || documentQuery.trim()) && documentHits.length === 0 ? (
            <div className="small faint">No matching evidence found in this run's uploaded documents or discovered columns.</div>
          ) : (
            <ul className="dashboard-list-clean">
              {documentHits.map((hit) => {
                const hitKey = `${hit.document}:${hit.source}:${hit.chunk_index}`;
                return (
                  <li
                    key={hitKey}
                    style={{
                      padding: '10px 12px',
                      border: '1px solid rgba(148, 163, 184, 0.22)',
                      borderRadius: 10,
                      background: 'rgba(15, 23, 42, 0.52)',
                      marginBottom: 8,
                    }}
                  >
                    <div
                      className="row"
                      style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}
                    >
                      <div className="small" style={{ fontWeight: 700, color: '#ffffff' }}>{hit.document}</div>
                      <div className="row" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                        <span
                          className="small"
                          style={{
                            background: 'rgba(59, 130, 246, 0.12)',
                            border: '1px solid rgba(96, 165, 250, 0.35)',
                            borderRadius: 999,
                            padding: '3px 8px',
                            color: '#dbeafe',
                          }}
                        >
                          {Math.round(hit.confidence * 100)}% match
                        </span>
                        <button
                          type="button"
                          className="button ghost small"
                          title="Copy excerpt to clipboard"
                          onClick={() => void copyExcerpt(hit)}
                        >
                          <Copy size={12} /> {copiedHitKey === hitKey ? 'Copied' : 'Copy excerpt'}
                        </button>
                      </div>
                    </div>
                    <div className="small faint mono" style={{ marginTop: 6 }}>{hit.source}</div>
                    <div
                      className="small"
                      style={{ marginTop: 8, lineHeight: 1.55 }}
                      title={hit.excerpt}
                    >
                      {highlightMatch(hit.excerpt, documentQuery)}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      )}

      {run && mappings.length > 0 && (
        <Card title="4. Mappings" className="dashboard-section-card enrichment-section">
          <table className="table">
            <thead>
              <tr>
                <th>Column</th>
                <th>Business Term</th>
                <th>Documentation</th>
                <th>Confidence</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {mappings.map((mapping) => (
                <tr key={mapping.id}>
                  <td className="mono">
                    {mapping.dataset_name}.{mapping.column_name}
                  </td>
                  <td>{mapping.business_term ?? <span className="faint">—</span>}</td>
                  <td>{mapping.document_title ?? <span className="faint">—</span>}</td>
                  <td>
                    <ConfidenceBadge confidence={mapping.confidence} inferred={mapping.method !== 'HUMAN_EDITED'} />
                  </td>
                  <td>
                    <Badge tone={statusTone(mapping.status)}>{mapping.status}</Badge>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="button ghost small"
                      onClick={() => {
                        setEditingId(null);
                        setExpandedId(mapping.id);
                      }}
                    >
                      Evidence
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {run && issues.length > 0 && (
        <Card title="5. Quality Issues" className="dashboard-section-card enrichment-section">
          <ul className="dashboard-list-clean">
            {issues.map((issue) => (
              <li key={issue.id} className="row" style={{ justifyContent: 'space-between', padding: '8px 0' }}>
                <div>
                  <Badge tone={severityTone(issue.severity)}>{issue.severity}</Badge>{' '}
                  <strong className="small">{issue.issue_type}</strong>{' '}
                  <span className="faint small">
                    {issue.dataset_name}
                    {issue.column_name ? `.${issue.column_name}` : ''}
                  </span>
                  <p className="small muted" style={{ margin: '4px 0 0' }}>
                    {issue.explanation}
                  </p>
                </div>
                <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                  <Badge tone={issue.status === 'OPEN' ? 'warn' : 'ok'}>{issue.status}</Badge>
                  {issue.status === 'OPEN' && (
                    <button
                      type="button"
                      className="button ghost small"
                      disabled={busy}
                      onClick={() => void resolveIssue(issue.id)}
                    >
                      Resolve
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {run && (
        <Card title="6. Integrate" className="dashboard-section-card enrichment-section">
          <p className="small muted">
            Integration is only allowed once every mapping has been reviewed and no high-severity
            issues remain open.
          </p>
          <div className="row" style={{ gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
            <button type="button" className="button" disabled={busy} onClick={() => void integrate()}>
              Add to Catalog
            </button>
            <a className="button ghost" href={enrichmentApi.exportUrl(run.id, 'json')} target="_blank" rel="noreferrer">
              <Download size={14} /> Export JSON
            </a>
            <a className="button ghost" href={enrichmentApi.exportUrl(run.id, 'yaml')} target="_blank" rel="noreferrer">
              <Download size={14} /> Export YAML
            </a>
          </div>

          {integrationResult && (
            <div style={{ marginTop: 16 }}>
              <p className="small">
                Integrated {integrationResult.integrated_count} asset(s) into the catalog.
              </p>
              <ul className="dashboard-list-clean">
                {integrationResult.entity_urns.map((urn) => (
                  <li key={urn}>
                    <Link to={`/assets?urn=${encodeURIComponent(urn)}`} className="mono small">
                      {urn} <ExternalLink size={12} />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {busy && !run && <Spinner label="Uploading" />}

      {expandedMapping && (
        <div className="evidence-drawer-backdrop" role="presentation" onClick={() => setExpandedId(null)}>
          <aside
            className="evidence-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Mapping evidence"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="evidence-drawer-header">
              <div>
                <div className="small faint">Evidence</div>
                <div className="mono" style={{ fontSize: 15, fontWeight: 600 }}>
                  {expandedMapping.dataset_name}.{expandedMapping.column_name}
                </div>
              </div>
              <button
                type="button"
                className="evidence-close"
                aria-label="Close evidence panel"
                onClick={() => setExpandedId(null)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="evidence-drawer-body">
              <section className="evidence-section">
                <p className="evidence-section-title">Technical Asset</p>
                <div className="evidence-field">
                  <span className="evidence-field-label">Dataset</span>
                  <span className="evidence-field-value mono">{expandedMapping.dataset_name}</span>
                </div>
                <div className="evidence-field">
                  <span className="evidence-field-label">Column</span>
                  <span className="evidence-field-value mono">{expandedMapping.column_name}</span>
                </div>
              </section>

              <section className="evidence-section">
                <p className="evidence-section-title">Business Context</p>
                <div className="evidence-field">
                  <span className="evidence-field-label">Business Term</span>
                  <span className="evidence-field-value">
                    {expandedMapping.business_term ?? <span className="faint">Not mapped</span>}
                  </span>
                </div>
                <div className="evidence-field">
                  <span className="evidence-field-label">Definition</span>
                  <span className="evidence-field-value">
                    {expandedMapping.business_definition ?? <span className="faint">None available</span>}
                  </span>
                </div>
              </section>

              <section className="evidence-section">
                <p className="evidence-section-title">Source Evidence</p>
                <div className="evidence-field">
                  <span className="evidence-field-label">Document</span>
                  <span className="evidence-field-value">
                    {expandedMapping.document_title ?? <span className="faint">None available</span>}
                  </span>
                </div>
                {expandedMapping.document_source && (
                  <div className="evidence-field">
                    <span className="evidence-field-label">Source</span>
                    <span className="evidence-field-value faint">{expandedMapping.document_source}</span>
                  </div>
                )}
                <div className="evidence-excerpt">
                  {expandedMapping.evidence_excerpt ??
                    expandedMapping.candidates.find((c) => c.excerpt)?.excerpt ??
                    'No supporting excerpt available.'}
                </div>
                {!expandedMapping.evidence_excerpt && expandedMapping.candidates.some((c) => c.excerpt) && (
                  <p className="small faint" style={{ marginTop: 6 }}>
                    Below the confidence threshold - shown for reference only, not applied as confirmed evidence.
                  </p>
                )}
              </section>

              <section className="evidence-section">
                <p className="evidence-section-title">AI Mapping</p>
                <div className="evidence-field">
                  <span className="evidence-field-label">Confidence</span>
                  <span className="evidence-field-value">
                    <ConfidenceBadge
                      confidence={expandedMapping.confidence}
                      inferred={expandedMapping.method !== 'HUMAN_EDITED'}
                    />
                  </span>
                </div>
                <div className="evidence-field">
                  <span className="evidence-field-label">Method</span>
                  <span className="evidence-field-value mono small">{expandedMapping.method}</span>
                </div>
                {expandedMapping.candidates.length > 0 && (
                  <div className="evidence-field">
                    <span className="evidence-field-label">Candidates</span>
                    <span className="evidence-field-value">
                      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                        {expandedMapping.candidates.map((c) => (
                          <Badge key={c.term} title={c.excerpt ? `${c.source}: ${c.excerpt}` : c.source}>
                            {c.term} · {Math.round(c.confidence * 100)}%
                          </Badge>
                        ))}
                      </div>
                    </span>
                  </div>
                )}
              </section>

              <section className="evidence-section">
                <p className="evidence-section-title">Validation Issues</p>
                {issuesForMapping(expandedMapping.id).length === 0 ? (
                  <p className="small faint">No open issues.</p>
                ) : (
                  <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                    {issuesForMapping(expandedMapping.id).map((issue) => (
                      <Badge key={issue.id} tone={severityTone(issue.severity)} title={issue.explanation}>
                        {issue.issue_type}
                      </Badge>
                    ))}
                  </div>
                )}
              </section>

              <section className="evidence-section">
                <p className="evidence-section-title">Review</p>
                <div className="evidence-field">
                  <span className="evidence-field-label">Status</span>
                  <span className="evidence-field-value">
                    <Badge tone={statusTone(expandedMapping.status)}>{expandedMapping.status}</Badge>
                  </span>
                </div>

                {editingId === expandedMapping.id ? (
                  <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                    <input
                      className="input"
                      placeholder="Business term"
                      value={editTerm}
                      onChange={(e) => setEditTerm(e.target.value)}
                    />
                    <input
                      className="input"
                      placeholder="Definition"
                      value={editDefinition}
                      onChange={(e) => setEditDefinition(e.target.value)}
                    />
                    <button
                      type="button"
                      className="button success"
                      onClick={() => void review(expandedMapping.id, 'edit')}
                    >
                      Save
                    </button>
                    <button type="button" className="button ghost" onClick={() => setEditingId(null)}>
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="row" style={{ gap: 8, marginTop: 12 }}>
                    <button
                      type="button"
                      className="button success"
                      disabled={
                        busy ||
                        expandedMapping.status === 'APPROVED' ||
                        expandedMapping.status === 'APPROVED_WITH_OPEN_ISSUE'
                      }
                      onClick={() => void review(expandedMapping.id, 'approve')}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="button danger"
                      disabled={busy || expandedMapping.status === 'REJECTED'}
                      onClick={() => void review(expandedMapping.id, 'reject')}
                    >
                      Reject
                    </button>
                    <button
                      type="button"
                      className="button ghost"
                      disabled={busy}
                      onClick={() => {
                        setEditingId(expandedMapping.id);
                        setEditTerm(expandedMapping.business_term ?? '');
                        setEditDefinition(expandedMapping.business_definition ?? '');
                      }}
                    >
                      Edit
                    </button>
                  </div>
                )}
              </section>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
