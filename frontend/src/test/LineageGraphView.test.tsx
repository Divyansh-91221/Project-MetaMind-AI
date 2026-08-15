import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LineageGraphView } from '@/components/lineage/LineageGraphView';
import type { LineageGraph } from '@/types';

const graph: LineageGraph = {
  root_urn: 'urn:emc:column:snowflake:snowflake.sales.total_revenue',
  direction: 'UPSTREAM',
  depth: 3,
  nodes: [
    {
      urn: 'urn:emc:column:snowflake:snowflake.sales.total_revenue',
      name: 'total_revenue',
      qualified_name: 'snowflake.sales.total_revenue',
      entity_type: 'COLUMN',
      platform: 'snowflake',
      depth: 0,
      properties: {},
    },
    {
      urn: 'urn:emc:column:sap:sap.orders.amount',
      name: 'amount',
      qualified_name: 'sap.orders.amount',
      entity_type: 'COLUMN',
      platform: 'sap',
      depth: 1,
      properties: {},
    },
  ],
  edges: [
    {
      source_urn: 'urn:emc:column:sap:sap.orders.amount',
      target_urn: 'urn:emc:column:snowflake:snowflake.sales.total_revenue',
      relationship: 'DERIVED_FROM',
      transformation: 'SUM(amount)',
      level: 'COLUMN',
      method: 'SQL_PARSE',
      confidence: 0.94,
      verified: false,
      verification_status: 'UNVERIFIED',
      evidence: {},
    },
    {
      source_urn: 'urn:emc:column:sap:sap.customer.country',
      target_urn: 'urn:emc:column:snowflake:snowflake.sales.total_revenue',
      relationship: 'DERIVED_FROM',
      level: 'COLUMN',
      method: 'AI_INFERRED',
      confidence: 0.42,
      verified: false,
      verification_status: 'UNVERIFIED',
      evidence: {},
    },
  ],
  truncated: false,
};

describe('LineageGraphView', () => {
  it('renders nodes grouped by hop distance', () => {
    render(
      <MemoryRouter>
        <LineageGraphView graph={graph} />
      </MemoryRouter>,
    );

    expect(screen.getByText('Selected asset')).toBeInTheDocument();
    expect(screen.getByText('1 hop upstream')).toBeInTheDocument();
    expect(screen.getByText(/snowflake.sales.total_revenue/)).toBeInTheDocument();
  });

  it('flags AI-inferred relationships so they are never mistaken for facts', () => {
    render(
      <MemoryRouter>
        <LineageGraphView graph={graph} />
      </MemoryRouter>,
    );

    expect(screen.getByText('Needs review')).toBeInTheDocument();
    expect(screen.getByText(/AI-inferred 42%/)).toBeInTheDocument();
  });

  it('shows the transformation expression for parsed lineage', () => {
    render(
      <MemoryRouter>
        <LineageGraphView graph={graph} />
      </MemoryRouter>,
    );

    expect(screen.getByText('SUM(amount)')).toBeInTheDocument();
  });
});
