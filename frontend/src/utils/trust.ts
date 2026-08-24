import type { TrustStatusTone } from '@/types';

export function renderMaybePercent(value: number | null | undefined): string {
  if (value == null) return 'N/A';
  const normalized = value > 1 ? value : value * 100;
  return `${Math.round(normalized)}%`;
}

export function trustToneFromStatus(status: TrustStatusTone): 'ok' | 'warn' | 'error' | 'default' {
  if (status === 'HEALTHY') return 'ok';
  if (status === 'WARNING' || status === 'PENDING_REVIEW') return 'warn';
  if (status === 'CRITICAL') return 'error';
  return 'default';
}
