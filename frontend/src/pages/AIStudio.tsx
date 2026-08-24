import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ShieldCheck, Sparkles } from 'lucide-react';
import { useApi } from '@/hooks';
import { governanceApi, qualityApi } from '@/services/governanceApi';
import { impactApi } from '@/services/impactApi';
import { Badge, Card, PageHeader, Stepper } from '@/components/common';
import type { StepperStep } from '@/components/common';

type WorkflowName = 'sensitive-review' | 'quality-investigation';

/**
 * Predefined, evidence-backed workflows over the existing services.
 *
 * There is no generic workflow engine here on purpose: each workflow is a fixed sequence of
 * real API calls, and every step's "detail" is the actual response, not a canned string.
 */
export function AIStudio() {
  const [active, setActive] = useState<WorkflowName>('sensitive-review');

  return (
    <>
      <PageHeader
        title="AI Studio"
        description="Predefined investigation workflows that chain the catalog, lineage, impact and governance APIs into a single guided run."
      />

      <div className="studio-switcher" style={{ marginBottom: 16 }}>
        <button
          type="button"
          className={`studio-tab ${active === 'sensitive-review' ? 'active' : ''}`}
          onClick={() => setActive('sensitive-review')}
        >
          <ShieldCheck size={14} />
          Sensitive Data Review
        </button>
        <button
          type="button"
          className={`studio-tab ${active === 'quality-investigation' ? 'active' : ''}`}
          onClick={() => setActive('quality-investigation')}
        >
          <AlertTriangle size={14} />
          Data Quality Investigation
        </button>
      </div>

      {active === 'sensitive-review' ? <SensitiveDataReview /> : <DataQualityInvestigation />}
    </>
  );
}

function SensitiveDataReview() {
  const candidates = useApi(() => governanceApi.sensitive('PCI', 20), []);
  const [urn, setUrn] = useState<string>('');
  const [steps, setSteps] = useState<StepperStep[]>([]);
  const [running, setRunning] = useState(false);
  const [approved, setApproved] = useState(false);

  const run = async () => {
    if (!urn) return;
    setRunning(true);
    setApproved(false);
    const trail: StepperStep[] = [];
    setSteps([{ label: 'Classify asset', state: 'active' }]);

    const candidate = candidates.data?.find((row) => row.urn === urn);
    trail.push({
      label: 'Classify asset',
      detail: candidate
        ? `${candidate.classification} (${candidate.level}), ${Math.round(candidate.confidence * 100)}% confidence via ${candidate.method}.`
        : 'No classification found for this asset.',
    });
    setSteps([...trail, { label: 'Find owner', state: 'active' }]);

    const profile = await governanceApi.profile(urn);
    const ownerNames = profile.owners.map((o) => o.owner.name).join(', ') || 'no accountable owner';
    trail.push({ label: 'Find owner', detail: ownerNames });
    setSteps([...trail, { label: 'Check downstream impact', state: 'active' }]);

    const impact = await impactApi.analyze(urn, 8);
    trail.push({
      label: 'Check downstream impact',
      detail: `${impact.summary.total_impacted} downstream asset(s), including ${impact.summary.dashboards_affected} dashboard(s).`,
    });
    setSteps([...trail, { label: 'Generate risk summary', state: 'active' }]);

    const summary = candidate
      ? `${candidate.qualified_name} carries ${candidate.classification} data owned by ${
          ownerNames === 'no accountable owner' ? 'nobody currently' : ownerNames
        }. A change here would reach ${impact.summary.total_impacted} downstream asset(s)` +
        `${impact.summary.dashboards_affected > 0 ? `, including ${impact.summary.dashboards_affected} dashboard(s)` : ''}.` +
        `${!candidate.confirmed ? ' The classification is still awaiting steward confirmation.' : ''}`
      : 'No risk summary could be generated.';
    trail.push({ label: 'Generate risk summary', detail: summary });
    setSteps([...trail, { label: 'Request human approval', state: 'pending' }]);
    setRunning(false);
  };

  const approve = async () => {
    const candidate = candidates.data?.find((row) => row.urn === urn);
    if (!candidate) return;
    await governanceApi.reviewClassification(candidate.assignment_id, 'CONFIRMED');
    setApproved(true);
    setSteps((current) =>
      current.map((step) =>
        step.label === 'Request human approval'
          ? { label: 'Governance action created', detail: `${candidate.classification} confirmed.`, state: 'done' }
          : step,
      ),
    );
    candidates.reload();
  };

  return (
    <Card title="Sensitive Data Review" className="studio-card">
      <p className="muted small">
        New sensitive asset detected &rarr; classify &rarr; find owner &rarr; check downstream
        impact &rarr; generate risk summary &rarr; request human approval &rarr; create
        governance action.
      </p>
      {candidates.loading && <p className="faint small">Loading candidate assets...</p>}
      {candidates.data && (
        <div className="row" style={{ marginBottom: 16 }}>
          <select className="select" style={{ width: 360 }} value={urn} onChange={(e) => setUrn(e.target.value)}>
            <option value="">Select a PCI asset...</option>
            {candidates.data.map((row) => (
              <option key={row.assignment_id} value={row.urn}>
                {row.qualified_name} {row.confirmed ? '' : '(unconfirmed)'}
              </option>
            ))}
          </select>
          <button type="button" className="button primary" disabled={!urn || running} onClick={() => void run()}>
            {running ? 'Running...' : 'Run workflow'}
          </button>
        </div>
      )}

      {steps.length > 0 && (
        <>
          <Stepper steps={steps} />
          {steps.some((s) => s.label === 'Request human approval' && s.state === 'pending') && (
            <div className="row" style={{ marginTop: 12 }}>
              <button type="button" className="button success" onClick={() => void approve()}>
                Approve and create governance action
              </button>
              <Link to="/approvals" className="button">
                Review in Human Approval
              </Link>
            </div>
          )}
          {approved && <Badge tone="ok"><Sparkles size={12} /> Governance action recorded</Badge>}
        </>
      )}
    </Card>
  );
}

function DataQualityInvestigation() {
  const staleAssets = useApi(() => qualityApi.stale(20), []);
  const [urn, setUrn] = useState<string>('');
  const [steps, setSteps] = useState<StepperStep[]>([]);
  const [running, setRunning] = useState(false);

  const run = async () => {
    if (!urn) return;
    setRunning(true);
    const trail: StepperStep[] = [];
    setSteps([{ label: 'Find upstream root cause', state: 'active' }]);

    const explanation = await qualityApi.staleness(urn);
    const cause =
      explanation.likely_causes.length > 0
        ? explanation.likely_causes.join('; ')
        : 'No upstream cause could be identified from the lineage graph.';
    trail.push({ label: 'Find upstream root cause', detail: cause });
    setSteps([...trail, { label: 'Find downstream impact', state: 'active' }]);

    const impact = await impactApi.analyze(urn, 8);
    trail.push({
      label: 'Find downstream impact',
      detail: `${impact.summary.total_impacted} downstream asset(s) are potentially affected while this asset is stale.`,
    });
    setSteps([...trail, { label: 'Identify owner', state: 'active' }]);

    const profile = await governanceApi.profile(urn);
    const ownerNames = profile.owners.map((o) => o.owner.name).join(', ') || 'no accountable owner';
    trail.push({ label: 'Identify owner', detail: ownerNames });
    setSteps([...trail, { label: 'Generate investigation summary', state: 'active' }]);

    const summary =
      `${profile.entity_name} is stale` +
      `${explanation.age_hours ? ` (${explanation.age_hours.toFixed(1)}h since last update)` : ''}. ` +
      `${cause} ${impact.summary.total_impacted} downstream asset(s) may be affected. ` +
      `Owner: ${ownerNames}.`;
    trail.push({ label: 'Generate investigation summary', detail: summary });
    setSteps(trail);
    setRunning(false);
  };

  return (
    <Card title="Data Quality Investigation" className="studio-card">
      <p className="muted small">
        Freshness issue &rarr; find upstream root cause &rarr; find downstream impact &rarr;
        identify owner &rarr; generate investigation summary.
      </p>
      {staleAssets.loading && <p className="faint small">Loading stale assets...</p>}
      {staleAssets.data && (
        <div className="row" style={{ marginBottom: 16 }}>
          <select className="select" style={{ width: 360 }} value={urn} onChange={(e) => setUrn(e.target.value)}>
            <option value="">Select a stale asset...</option>
            {staleAssets.data.map((row) => (
              <option key={String(row.urn)} value={String(row.urn)}>
                {String(row.qualified_name)}
              </option>
            ))}
          </select>
          <button type="button" className="button primary" disabled={!urn || running} onClick={() => void run()}>
            {running ? 'Running...' : 'Run investigation'}
          </button>
        </div>
      )}
      {staleAssets.data && staleAssets.data.length === 0 && (
        <p className="faint small">No stale assets right now - nothing to investigate.</p>
      )}
      {steps.length > 0 && <Stepper steps={steps} />}
    </Card>
  );
}
