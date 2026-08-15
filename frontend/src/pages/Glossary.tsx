import { useState } from 'react';
import { useApi } from '@/hooks';
import { glossaryApi } from '@/services/governanceApi';
import { AsyncBoundary, Card, EmptyState, PageHeader } from '@/components/common';
import { TermCard, TermDetail } from '@/components/glossary';

/** Business glossary: definitions, KPIs and the assets that implement them. */
export function Glossary() {
  const [selected, setSelected] = useState<string | null>(null);
  const [kpiOnly, setKpiOnly] = useState(false);

  const terms = useApi(() => glossaryApi.list(kpiOnly, 100), [kpiOnly]);
  const detail = useApi(
    () => (selected ? glossaryApi.get(selected) : Promise.resolve(null)),
    [selected],
  );

  return (
    <>
      <PageHeader
        title="Business Glossary"
        description="Governed business definitions, linked to the technical assets that implement them."
        actions={
          <label className="row small muted" style={{ gap: 6 }}>
            <input type="checkbox" checked={kpiOnly} onChange={(e) => setKpiOnly(e.target.checked)} />
            KPIs only
          </label>
        }
      />

      <div className="grid grid-2">
        <div>
          <AsyncBoundary {...terms} onRetry={terms.reload}>
            {(page) =>
              page.items.length === 0 ? (
                <EmptyState title="The glossary is empty." hint="Run scripts/seed_demo_data.py to load demo terms." />
              ) : (
                <div className="grid" style={{ gap: 12 }}>
                  {page.items.map((term) => (
                    <TermCard
                      key={term.id}
                      term={term}
                      active={selected === term.name}
                      onSelect={(value) => setSelected(value.name)}
                    />
                  ))}
                </div>
              )
            }
          </AsyncBoundary>
        </div>

        <Card>
          {!selected ? (
            <EmptyState title="Select a term." hint="Definitions include the calculation and the assets behind them." />
          ) : (
            <AsyncBoundary {...detail} onRetry={detail.reload} emptyTitle="Term not found.">
              {(data) => data && <TermDetail term={data} />}
            </AsyncBoundary>
          )}
        </Card>
      </div>
    </>
  );
}
