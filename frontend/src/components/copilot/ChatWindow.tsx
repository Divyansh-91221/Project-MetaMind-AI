import { useEffect, useRef, useState } from 'react';
import { copilotApi } from '@/services/copilotApi';
import type { ChatMessage, EvidenceItem, ToolCallTrace } from '@/types';
import { MessageBubble } from './MessageBubble';
import { EvidenceList } from './EvidenceList';
import { Card } from '@/components/common/Card';

const FALLBACK_EXAMPLES = [
  'What is customer_id?',
  'Where does customer_id come from?',
  'What will break if customer_id changes?',
  'Which datasets contain PII?',
  'Why is the revenue dashboard stale?',
];

/**
 * Copilot chat.
 *
 * `contextUrn` is the asset the user navigated from; sending it lets the agent resolve
 * "this table" without guessing.
 */
export function ChatWindow({ contextUrn }: { contextUrn?: string | null }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCallTrace[]>([]);
  const [examples, setExamples] = useState<string[]>(FALLBACK_EXAMPLES);
  const [followups, setFollowups] = useState<string[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    copilotApi.examples().then(setExamples).catch(() => setExamples(FALLBACK_EXAMPLES));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || sending) return;

    const history = messages;
    setMessages([...history, { role: 'user', content: question }]);
    setInput('');
    setSending(true);
    setFollowups([]);

    try {
      const response = await copilotApi.chat(question, {
        conversationId,
        history,
        entityUrn: contextUrn ?? undefined,
      });
      setConversationId(response.conversation_id);
      setEvidence(response.evidence);
      setToolCalls(response.tool_calls);
      setFollowups(response.suggested_followups);
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: response.answer,
          evidence: response.evidence,
          warnings: response.warnings,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: `The Copilot could not answer: ${
            error instanceof Error ? error.message : 'unknown error'
          }`,
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  const suggestions = followups.length > 0 ? followups : examples.slice(0, 5);

  return (
    <div className="chat-layout">
      <Card className="chat-panel" title="Ask about your enterprise data">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="muted">
              Ask about definitions, lineage, impact, ownership, sensitivity or freshness. Answers
              are built from the catalog and lineage graph, and every claim is backed by evidence.
            </div>
          )}
          {messages.map((message, index) => (
            <MessageBubble key={index} message={message} />
          ))}
          {sending && <div className="message assistant muted">Gathering evidence...</div>}
          <div ref={endRef} />
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              className="suggestion"
              onClick={() => send(suggestion)}
              disabled={sending}
            >
              {suggestion}
            </button>
          ))}
        </div>

        <form
          className="chat-input"
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
        >
          <input
            className="input"
            value={input}
            placeholder="Ask the Metadata Copilot..."
            onChange={(event) => setInput(event.target.value)}
            disabled={sending}
            aria-label="Question"
          />
          <button type="submit" className="button primary" disabled={sending || !input.trim()}>
            Ask
          </button>
        </form>
      </Card>

      <Card className="evidence-panel" title="Evidence">
        <EvidenceList evidence={evidence} toolCalls={toolCalls} />
      </Card>
    </div>
  );
}
