import { useSearchParams } from 'react-router-dom';
import { ChatWindow } from '@/components/copilot';
import { PageHeader } from '@/components/common';

/** Copilot chat page. An optional `urn` query parameter provides page context to the agent. */
export function Copilot() {
  const [params] = useSearchParams();
  const contextUrn = params.get('urn');

  return (
    <>
      <PageHeader
        title="Metadata Copilot"
        description={
          contextUrn
            ? `Answering in the context of ${contextUrn}`
            : 'Ask about definitions, lineage, impact, ownership, sensitivity and freshness. Every answer is backed by evidence from the catalog and lineage graph.'
        }
      />
      <ChatWindow contextUrn={contextUrn} />
    </>
  );
}
