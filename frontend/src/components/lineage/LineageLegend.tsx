import { Badge } from '@/components/common/Badge';

/** Explains how to read the lineage view - especially the inferred/verified distinction. */
export function LineageLegend() {
  return (
    <div className="row small muted">
      <Badge tone="ok">Verified</Badge>
      <span>human-confirmed</span>
      <Badge tone="ok">85%+</Badge>
      <span>SQL parsed or OpenLineage</span>
      <Badge tone="warn">60-85%</Badge>
      <span>connector declared</span>
      <Badge tone="inferred">AI-inferred</Badge>
      <span>suggestion only, must be reviewed before it is trusted</span>
    </div>
  );
}
