import { describe, expect, it } from 'vitest';
import { confidenceTone, formatConfidence, methodLabel, urnToName } from '@/utils/format';

describe('format utilities', () => {
  it('extracts the qualified name from a URN', () => {
    expect(urnToName('urn:emc:table:snowflake:snowflake.sales')).toBe('snowflake.sales');
    expect(urnToName('urn:emc:column:sap:sap.orders.amount')).toBe('sap.orders.amount');
  });

  it('renders confidence as a percentage', () => {
    expect(formatConfidence(0.97)).toBe('97%');
    expect(formatConfidence(0.42)).toBe('42%');
  });

  it('maps confidence onto a trust tone', () => {
    expect(confidenceTone(0.95)).toBe('high');
    expect(confidenceTone(0.7)).toBe('medium');
    expect(confidenceTone(0.42)).toBe('low');
  });

  it('humanises extraction methods', () => {
    expect(methodLabel('SQL_PARSE')).toBe('Sql Parse');
    expect(methodLabel('AI_INFERRED')).toBe('Ai Inferred');
  });
});
