import { describe, expect, it } from 'vitest';
import { renderMaybePercent, trustToneFromStatus } from '@/utils/trust';

describe('trust utilities', () => {
  it('renders percentage values from both fractional and percent inputs', () => {
    expect(renderMaybePercent(0.91)).toBe('91%');
    expect(renderMaybePercent(91)).toBe('91%');
    expect(renderMaybePercent(null)).toBe('N/A');
  });

  it('maps trust status to badge tones', () => {
    expect(trustToneFromStatus('HEALTHY')).toBe('ok');
    expect(trustToneFromStatus('PENDING_REVIEW')).toBe('warn');
    expect(trustToneFromStatus('CRITICAL')).toBe('error');
    expect(trustToneFromStatus('UNKNOWN')).toBe('default');
  });
});
