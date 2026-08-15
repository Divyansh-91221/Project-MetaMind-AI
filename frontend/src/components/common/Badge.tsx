import type { ReactNode } from 'react';

type Tone = 'default' | 'ok' | 'warn' | 'error' | 'accent' | 'inferred' | 'high' | 'medium' | 'low';

export function Badge({
  children,
  tone = 'default',
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  title?: string;
}) {
  return (
    <span className={`badge${tone === 'default' ? '' : ` ${tone}`}`} title={title}>
      {children}
    </span>
  );
}

/**
 * Confidence indicator for lineage and classification.
 * Inferred relationships are always rendered distinctly so a suggestion is never mistaken
 * for a verified fact.
 */
export function ConfidenceBadge({
  confidence,
  inferred = false,
  verified = false,
}: {
  confidence: number;
  inferred?: boolean;
  verified?: boolean;
}) {
  if (verified) return <Badge tone="ok" title="Verified by a human reviewer">Verified</Badge>;

  const tone: Tone = inferred ? 'inferred' : confidence >= 0.85 ? 'ok' : confidence >= 0.6 ? 'warn' : 'error';
  const label = `${Math.round(confidence * 100)}%`;

  return (
    <Badge tone={tone} title={inferred ? 'AI-inferred and awaiting human verification' : 'Extraction confidence'}>
      {inferred ? `AI-inferred ${label}` : label}
    </Badge>
  );
}
