import { useSearchParams } from 'react-router-dom';
import { Link } from 'react-router-dom';
import { Bot, ClipboardList, Workflow } from 'lucide-react';
import { Badge } from '@/components/common';
import { ChatWindow } from '@/components/copilot';
import { PageHeader } from '@/components/common';

/** Copilot chat page. An optional `urn` query parameter provides page context to the agent. */
export function Copilot() {
  const [params] = useSearchParams();
  const contextUrn = params.get('urn');
  const initialPrompt = params.get('prompt');

  return (
    <>
      <PageHeader
        title="AI Copilot"
        description={
          contextUrn
            ? `Answering in the context of ${contextUrn}`
            : 'Ask about definitions, lineage, impact, ownership, sensitivity and freshness. Every answer is backed by evidence from the catalog and lineage graph.'
        }
        actions={
          <div className="row">
            <Link to="/studio" className="button">
              <Workflow size={14} /> Open AI Studio
            </Link>
            <Link to="/approvals" className="button">
              <ClipboardList size={14} /> Human Approvals
            </Link>
          </div>
        }
      />
      <div className="row" style={{ marginBottom: 14 }}>
        <Badge tone="accent"><Bot size={12} /> Evidence-backed mode</Badge>
        {contextUrn ? <Badge tone="ok">Asset context attached</Badge> : <Badge>Global context</Badge>}
      </div>
      <ChatWindow contextUrn={contextUrn} initialPrompt={initialPrompt} />
    </>
  );
}
